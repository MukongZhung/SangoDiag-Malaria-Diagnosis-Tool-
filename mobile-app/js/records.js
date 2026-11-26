// SangoDiag records: the health post's own patient register, villages, visits and
// patient memory, all kept in the encrypted store (store.js).
//
// Kinds in the store:
//   post      the health post (one record, id "post")
//   village   villages served, with endemic zone and active cases this week
//   patient   the patient register
//   visit     one record per "Check this patient": intake, decision, feedback
//   memory    H-MEM-style records (observation 0.9, recommendation 0.6, rec:<ACTION> tag)
//   ledger    append-only log of every memory write and feedback
//   outbox    visits waiting to be sent to a SangoDiag server
import * as store from "./store.js";
import { BUNDLE } from "./data.js";

export const FEEDBACK_DELTAS = { helpful: 0.05, not_helpful: -0.03, wrong: -0.2 };
const YEAR_MS = 365.25 * 24 * 3600 * 1000;
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const round2 = (x) => Math.round(x * 100) / 100;

/* ---------- health post ---------- */

export const getPost = () => store.get("post", "post");
export const savePost = (p) => store.put("post", { ...getPost(), ...p, id: "post" });

/* ---------- villages ---------- */

export const ZONES = ["high", "medium", "low"];
export const villages = () => store.all("village").sort((a, b) => a.name.localeCompare(b.name));
export const village = (id) => store.get("village", id);
export const villageByName = (name) => villages().find((v) => v.name.toLowerCase() === String(name || "").toLowerCase()) || null;

export async function saveVillage({ id, name, zone, cases, demo }) {
  const v = {
    id: id || store.newId("v-"), name: String(name).trim(), zone: ZONES.includes(zone) ? zone : null,
    cases: cases === "" || cases === null || cases === undefined ? null : Math.max(0, Math.trunc(Number(cases))),
    updatedAt: Date.now(), demo: !!demo,
  };
  return store.put("village", v);
}

/* ---------- patients ---------- */

const ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
export function patientCode() {
  const b = crypto.getRandomValues(new Uint8Array(6));
  return "SD-" + [...b].map((x) => ALPHABET[x % ALPHABET.length]).join("");
}

export const patients = () => store.all("patient");
export const patient = (id) => store.get("patient", id);

/** Age today, from the age the nurse entered and when she entered it. */
export function ageNow(p, now = Date.now()) {
  if (p.ageYears === null || p.ageYears === undefined) return null;
  const a = p.ageYears + (now - (p.ageRecordedAt || now)) / YEAR_MS;
  return a < 2 ? Math.round(a * 12) / 12 : Math.floor(a);
}

export async function savePatient(input) {
  const old = input.id ? patient(input.id) : null;
  const ageChanged = !old || old.ageYears !== input.ageYears;
  const p = {
    id: input.id || patientCode(),
    name: String(input.name || "").trim(),
    sex: input.sex === "F" || input.sex === "M" ? input.sex : null,
    ageYears: input.ageYears === null || input.ageYears === undefined || input.ageYears === "" ? null : Number(input.ageYears),
    ageRecordedAt: ageChanged ? Date.now() : old.ageRecordedAt,
    villageId: input.villageId || null,
    phone: String(input.phone || "").trim(),
    familyHistory: !!input.familyHistory,
    createdAt: old ? old.createdAt : Date.now(),
    updatedAt: Date.now(),
    demo: !!input.demo,
  };
  return store.put("patient", p);
}

function norm(s) {
  return String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

export function searchPatients(q) {
  const list = patients();
  const lastVisit = new Map();
  for (const v of store.all("visit")) lastVisit.set(v.patientId, Math.max(lastVisit.get(v.patientId) || 0, v.at));
  const score = (p) => lastVisit.get(p.id) || p.updatedAt || 0;
  const n = norm(q).trim();
  const hits = n ? list.filter((p) => {
    const vil = village(p.villageId);
    return [p.name, p.id, p.phone, vil && vil.name].some((f) => norm(f).includes(n));
  }) : list;
  return hits.sort((a, b) => score(b) - score(a));
}

/* ---------- visits, memory, ledger ---------- */

export const visitsFor = (patientId) => store.all("visit").filter((v) => v.patientId === patientId).sort((a, b) => b.at - a.at);
export const allVisits = () => store.all("visit").sort((a, b) => b.at - a.at);

export function recall(patientId, topN = 5) {
  return store.all("memory").filter((m) => m.patientId === patientId).sort((a, b) => b.timestamp - a.timestamp).slice(0, topN);
}

async function log(memoryId, action, details) {
  await store.put("ledger", { id: store.newId("l-"), memoryId, action, details: details || {}, timestamp: Date.now() });
}

export async function saveVisit({ patientId, intake, result, evidence, observation, recommendation }) {
  const at = Date.now();
  const visit = { id: store.newId("visit-"), patientId, at, intake, action: result.action, score: result.score,
    level: result.level, confidence: result.confidence, abstain: result.abstain,
    village: evidence.village, zone: evidence.endemic_zone, feedback: null };
  await store.put("visit", visit);
  const obs = { id: store.newId("m-"), patientId, content: observation, source: "nurse_intake", confidence: 0.9,
    tags: ["clinical", "event:chat_message", `run:${visit.id}`], timestamp: at, kind: "observation", visitId: visit.id };
  const rec = { id: store.newId("m-"), patientId, content: recommendation, source: "agent:on-device-rules", confidence: 0.6,
    tags: ["clinical", "event:model_response", "agent-recommendation", `run:${visit.id}`, `rec:${result.action}`],
    timestamp: at, kind: "recommendation", refs: [obs.id], action: result.action, visitId: visit.id };
  await store.put("memory", obs);
  await store.put("memory", rec);
  await log(obs.id, "create", { patientId });
  await log(rec.id, "create", { patientId });
  return visit;
}

/** The nurse says an earlier recommendation was right or wrong. */
export async function feedback(memoryId, kind) {
  const m = store.get("memory", memoryId);
  if (!m || !(kind in FEEDBACK_DELTAS)) throw new Error("unknown memory or feedback");
  const prev = m.confidence;
  m.confidence = round2(clamp01(m.confidence + FEEDBACK_DELTAS[kind]));
  if (kind === "wrong" && !m.tags.includes("review")) m.tags.push("review");
  m.feedback = kind;
  await store.put("memory", m);
  await log(memoryId, "feedback", { kind, delta: FEEDBACK_DELTAS[kind], from: prev, to: m.confidence });
  if (m.visitId) {
    const v = store.get("visit", m.visitId);
    if (v) await store.put("visit", { ...v, feedback: kind });
  }
  return m;
}

/* ---------- evidence for the rules ---------- */

/**
 * Builds the rows the rules read, in the shape the server agent gets from Zetaris:
 *   Q1 patient register, Q2 village / district data, Q3 earlier visits at this health post.
 */
export function evidenceRows(p) {
  const out = [];
  const vil = village(p.villageId);
  out.push({ qid: "Q1", source: "patients", rows: [{
    patient_id: p.id, village: vil ? vil.name : null, family_history_malaria: p.familyHistory,
  }] });
  if (vil && vil.zone) {
    out.push({ qid: "Q2", source: "villages", rows: [{ village: vil.name, endemic_zone: vil.zone, active_cases_this_week: vil.cases }] });
  }
  const prior = visitsFor(p.id).map((v) => ({ visit_id: v.id, patient_id: p.id,
    visit_date: new Date(v.at).toISOString().slice(0, 10), fever_temp_c: v.intake.temperature_c }));
  if (prior.length) out.push({ qid: "Q3", source: "visits", rows: prior });
  return out;
}

/* ---------- server outbox ---------- */

export const outbox = () => store.all("outbox");
export const queue = (item) => store.put("outbox", item);
export const unqueue = (id) => store.remove("outbox", id);

/* ---------- demo data ---------- */

export async function loadDemo() {
  const byName = {};
  for (const r of BUNDLE.epidemiology) {
    const v = await saveVillage({ name: r.village, zone: r.endemic_zone.toLowerCase(), cases: r.active_cases_this_week, demo: true });
    byName[r.village] = v.id;
  }
  for (const r of BUNDLE.patients) {
    if (patient(r.patient_id)) continue;
    await store.put("patient", { id: r.patient_id, name: `Demo ${r.village} ${r.gender === "F" ? "F" : "M"}${r.age}`,
      sex: r.gender, ageYears: Number(r.age), ageRecordedAt: Date.now(), villageId: byName[r.village],
      phone: "", familyHistory: r.family_history_malaria === "TRUE", createdAt: Date.now(), updatedAt: Date.now(), demo: true });
  }
}

export async function removeDemo() {
  const demoPatients = new Set(patients().filter((p) => p.demo).map((p) => p.id));
  for (const kind of ["visit", "memory", "outbox"]) {
    for (const r of store.all(kind)) if (demoPatients.has(r.patientId || (r.intake && r.intake.patient_id))) await store.remove(kind, r.id);
  }
  for (const id of demoPatients) await store.remove("patient", id);
  const used = new Set(patients().map((p) => p.villageId));
  for (const v of villages()) if (v.demo && !used.has(v.id)) await store.remove("village", v.id);
}

export const hasDemo = () => patients().some((p) => p.demo);

/* ---------- export ---------- */

const csvCell = (v) => {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

/** One row per visit, for the monthly report. Names and phone numbers are left out. */
export function visitsCsv(fromMs = 0) {
  const post = getPost() || {};
  const head = ["date", "time", "health_post", "district", "patient_id", "sex", "age_years", "village", "endemic_zone",
    "temperature_c", "fever_days", "pregnant", "symptoms", "danger_signs", "test_result", "next_step", "malaria_score",
    "confidence", "weak_suggestion", "nurse_feedback", "demo"];
  const rows = allVisits().filter((v) => v.at >= fromMs).reverse().map((v) => {
    const p = patient(v.patientId) || {};
    const d = new Date(v.at);
    return [d.toISOString().slice(0, 10), d.toTimeString().slice(0, 5), post.name, post.district, v.patientId, p.sex,
      v.intake.age_years, v.village, v.zone, v.intake.temperature_c, v.intake.fever_days, v.intake.pregnant ? "yes" : "no",
      v.intake.symptoms.join(" "), v.intake.danger_signs.join(" "), v.intake.test_result, v.action, v.score, v.confidence,
      v.abstain ? "yes" : "no", v.feedback || "", p.demo ? "yes" : "no"];
  });
  return [head, ...rows].map((r) => r.map(csvCell).join(",")).join("\n") + "\n";
}

/** Counts for the home screen and the monthly summary. */
export function summary(fromMs) {
  const vs = allVisits().filter((v) => v.at >= fromMs);
  const by = {};
  for (const v of vs) by[v.action] = (by[v.action] || 0) + 1;
  const tested = vs.filter((v) => v.intake.test_result !== "not_done");
  const positive = tested.filter((v) => ["rdt_positive", "smear_positive"].includes(v.intake.test_result));
  return { visits: vs.length, byAction: by, tested: tested.length, positive: positive.length };
}
