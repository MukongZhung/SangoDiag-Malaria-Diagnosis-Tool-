// SangoDiag encrypted store.
//
// Everything about patients stays on the phone, encrypted with a key made from the
// nurse's PIN (PBKDF2-SHA256, 210 000 rounds, then AES-GCM 256). Without the PIN the
// data on the phone, and in a backup file, cannot be read. Nobody, including Biotek-Nexus,
// can recover a forgotten PIN: the only way out is to erase the data (or restore a backup
// with its own PIN).
//
// After unlocking, records are decrypted into memory; every change is encrypted and
// written straight back. Lock() forgets the key and the decrypted copy.

const DB_NAME = "sangodiag-v2";
const ITERATIONS = 210000;
const enc = new TextEncoder();
const dec = new TextDecoder();

const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      db.createObjectStore("meta", { keyPath: "key" });
      db.createObjectStore("records", { keyPath: "k" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
let dbp = null;
const db = () => (dbp ||= openDb());

function run(storeNames, mode, fn) {
  return db().then((d) => new Promise((resolve, reject) => {
    const t = d.transaction(storeNames, mode);
    const out = fn(t);
    t.oncomplete = () => resolve(out instanceof IDBRequest ? out.result : out);
    t.onerror = () => reject(t.error);
    t.onabort = () => reject(t.error);
  }));
}

async function metaGet(key) {
  const r = await run(["meta"], "readonly", (t) => t.objectStore("meta").get(key));
  return r ? r.value ?? null : null;
}
async function metaSet(key, value) {
  await run(["meta"], "readwrite", (t) => { t.objectStore("meta").put({ key, value }); });
}

async function deriveKey(pin, saltB64) {
  const base = await crypto.subtle.importKey("raw", enc.encode(pin), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey({ name: "PBKDF2", salt: unb64(saltB64), iterations: ITERATIONS, hash: "SHA-256" },
    base, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
}

async function seal(key, obj) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, enc.encode(JSON.stringify(obj)));
  return { iv: b64(iv), ct: b64(ct) };
}
async function open(key, box) {
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64(box.iv) }, key, unb64(box.ct));
  return JSON.parse(dec.decode(pt));
}

const VERIFIER = { app: "sangodiag", check: "pin-ok" };

let KEY = null;
const cache = new Map(); // kind -> Map(id -> object)
const bucket = (kind) => { if (!cache.has(kind)) cache.set(kind, new Map()); return cache.get(kind); };

export const isUnlocked = () => KEY !== null;
export async function isSetUp() { return !!(await metaGet("verifier")); }

/** Plain (not secret) settings such as the language, readable before unlocking. */
export const getPlain = metaGet;
export const setPlain = metaSet;

export async function createVault(pin) {
  const salt = b64(crypto.getRandomValues(new Uint8Array(16)));
  const key = await deriveKey(pin, salt);
  await metaSet("salt", salt);
  await metaSet("verifier", await seal(key, VERIFIER));
  KEY = key;
  cache.clear();
}

export async function unlock(pin) {
  const salt = await metaGet("salt");
  const verifier = await metaGet("verifier");
  if (!salt || !verifier) return false;
  const key = await deriveKey(pin, salt);
  try {
    const v = await open(key, verifier);
    if (v.check !== VERIFIER.check) return false;
  } catch { return false; }
  const rows = await run(["records"], "readonly", (t) => t.objectStore("records").getAll());
  cache.clear();
  for (const r of rows) {
    try { bucket(r.kind).set(r.id, await open(key, r)); } catch { /* skip a damaged record */ }
  }
  KEY = key;
  return true;
}

export function lock() { KEY = null; cache.clear(); }

function need() { if (!KEY) throw new Error("SangoDiag is locked"); }

export function all(kind) { need(); return [...bucket(kind).values()]; }
export function get(kind, id) { need(); return bucket(kind).get(id) || null; }

export async function put(kind, obj) {
  need();
  if (!obj.id) throw new Error("record needs an id");
  const box = await seal(KEY, obj);
  await run(["records"], "readwrite", (t) => { t.objectStore("records").put({ k: `${kind}:${obj.id}`, kind, id: obj.id, ...box }); });
  bucket(kind).set(obj.id, obj);
  return obj;
}

export async function remove(kind, id) {
  need();
  await run(["records"], "readwrite", (t) => { t.objectStore("records").delete(`${kind}:${id}`); });
  bucket(kind).delete(id);
}

export async function changePin(oldPin, newPin) {
  if (!(await unlock(oldPin))) return false;
  const salt = b64(crypto.getRandomValues(new Uint8Array(16)));
  const key = await deriveKey(newPin, salt);
  const boxes = [];
  for (const [kind, m] of cache) for (const [id, obj] of m) boxes.push({ k: `${kind}:${id}`, kind, id, ...(await seal(key, obj)) });
  const verifier = await seal(key, VERIFIER);
  await run(["records", "meta"], "readwrite", (t) => {
    const s = t.objectStore("records");
    s.clear();
    for (const b of boxes) s.put(b);
    t.objectStore("meta").put({ key: "salt", value: salt });
    t.objectStore("meta").put({ key: "verifier", value: verifier });
  });
  KEY = key;
  return true;
}

/** Erase everything on this phone (used for "Forgot PIN" and "Erase all data"). */
export async function eraseAll() {
  KEY = null;
  cache.clear();
  await run(["records", "meta"], "readwrite", (t) => {
    t.objectStore("records").clear();
    t.objectStore("meta").clear();
  });
}

/** A backup file holds the encrypted records exactly as stored: it opens only with the PIN in use when it was made. */
export async function backup(info) {
  need();
  const rows = await run(["records"], "readonly", (t) => t.objectStore("records").getAll());
  return { format: "sangodiag-backup", version: 1, created: new Date().toISOString(), info: info || {},
    salt: await metaGet("salt"), verifier: await metaGet("verifier"), records: rows };
}

/** Check a backup's PIN, then replace this phone's data with it. */
export async function restore(file, pin) {
  if (!file || file.format !== "sangodiag-backup" || !Array.isArray(file.records)) throw new Error("not a SangoDiag backup");
  const key = await deriveKey(pin, file.salt);
  try { await open(key, file.verifier); } catch { return false; }
  await run(["records", "meta"], "readwrite", (t) => {
    const s = t.objectStore("records");
    s.clear();
    for (const r of file.records) s.put(r);
    t.objectStore("meta").put({ key: "salt", value: file.salt });
    t.objectStore("meta").put({ key: "verifier", value: file.verifier });
  });
  return unlock(pin);
}

/** Ask the browser not to clear SangoDiag's data when the phone is low on space. */
export async function askPersistent() {
  try { return navigator.storage && navigator.storage.persist ? await navigator.storage.persist() : false; } catch { return false; }
}

export const newId = (prefix = "") =>
  prefix + (crypto.randomUUID ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`);
