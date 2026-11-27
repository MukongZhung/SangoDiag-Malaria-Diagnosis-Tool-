// SangoDiag field app: one short screen in, one clear next step out.
// Screens: lock, setup, patients (home), patient form, patient page, visit, result, settings.
import { SYMPTOMS, DANGER_SIGNS, TEST_RESULTS, extractEvidence, triage, describeIntake } from "./triage.js";
import { LANGS, pack, ui, renderReason, renderStep } from "./i18n.js";
import { DEMO_CASES } from "./register.js";
import * as store from "./store.js";
import * as rec from "./records.js";
// a ?? b, written out so older phones (Chrome before 80) can run it.
const nn = (a, b) => (a === null || a === undefined ? b : a);
// Small stand-ins for newer browser functions, so the app also runs on older Android phones.
const flat = (a) => a.reduce((out, k) => out.concat(Array.isArray(k) ? flat(k) : [k]), []);
function fill(el, ...kids) { while (el.firstChild) el.removeChild(el.firstChild); for (const k of flat(kids)) el.append(k); }
const readText = (file) => new Promise((resolve, reject) => { const r = new FileReader(); r.onload = () => resolve(r.result); r.onerror = () => reject(r.error); r.readAsText(file); });

export const VERSION = "0.2.2";
const AUTO_LOCK_MS = 5 * 60 * 1000;
const DAY = 24 * 3600 * 1000;

const $ = (s, root = document) => root.querySelector(s);
const state = { lang: "en", server: "", screen: null, args: null, stack: [] };
const t = (key, ...a) => ui(state.lang, key, ...a);
const x = () => pack(state.lang);

/* ---------- tiny DOM helper ---------- */
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const k of flat(kids)) if (k !== null && k !== undefined && k !== false) el.append(k.nodeType ? k : String(k));
  return el;
}
const field = (label, input, hint) => h("label", { class: "field" }, h("span", {}, label), input, hint ? h("small", { class: "hint" }, hint) : null);
const num = (v) => { const s = String(nn(v, "")).trim().replace(",", "."); return s === "" ? null : Number(s); };
const fmtDate = (ms) => new Date(ms).toLocaleDateString(state.lang, { day: "numeric", month: "short", year: "numeric" });
const fmtDateTime = (ms) => new Date(ms).toLocaleString(state.lang, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function ageText(p) {
  const a = rec.ageNow(p);
  if (a === null) return "";
  return a < 2 ? `${Math.round(a * 12)} ${t("months")}` : `${a} ${t("years")}`;
}
function sexText(p) { return p.sex === "F" ? t("female") : p.sex === "M" ? t("male") : ""; }
function patientSub(p) {
  const v = rec.village(p.villageId);
  return [sexText(p), ageText(p), v && v.name].filter(Boolean).join(", ");
}

/* ---------- navigation ---------- */
const SCREENS = {};
function go(name, args = null, { push = true } = {}) {
  if (push && state.screen && !["lock", "setup"].includes(state.screen)) {
    state.stack.push({ name: state.screen, args: state.args });
    history.pushState({ d: state.stack.length }, "");
  }
  state.screen = name;
  state.args = args;
  $("#open-settings").hidden = !store.isUnlocked() || name === "settings";
  const view = $("#view");
  fill(view, SCREENS[name](args));
  window.scrollTo(0, 0);
}
function back() {
  const prev = state.stack.pop();
  if (prev) go(prev.name, prev.args, { push: false });
  else go("home", null, { push: false });
}
window.addEventListener("popstate", () => { if (store.isUnlocked()) back(); });
const backBtn = (label = t("back")) => h("button", { type: "button", class: "back", onclick: () => history.back() }, `‹ ${label}`);

/* ---------- lock and setup ---------- */
SCREENS.lock = () => {
  const err = h("p", { class: "form-error", role: "alert" });
  const pin = h("input", { type: "password", inputmode: "numeric", autocomplete: "current-password", maxlength: "8", pattern: "[0-9]*", "aria-label": t("unlock_title"), class: "pin" });
  const form = h("form", { class: "lock", onsubmit: async (e) => {
    e.preventDefault();
    err.textContent = "";
    if (await store.unlock(pin.value)) { pin.value = ""; afterUnlock(); }
    else { err.textContent = t("wrong_pin"); pin.value = ""; pin.focus(); }
  } },
  h("h1", {}, t("unlock_title")), pin, err,
  h("button", { class: "primary", type: "submit" }, t("unlock")),
  h("button", { type: "button", class: "danger-link", onclick: async () => {
    if (confirm(t("forgot_confirm"))) { await store.eraseAll(); go("setup", null, { push: false }); }
  } }, t("forgot_pin")));
  setTimeout(() => pin.focus(), 50);
  return form;
};

function villageEditor(list, onChange) {
  // list: array of {id?, name, zone, cases}
  const wrap = h("div", { class: "villages" });
  const render = () => {
    fill(wrap, ...list.map((v, i) => {
      const nameI = h("input", { value: v.name || "", maxlength: "60", "aria-label": t("village_name"), placeholder: t("village_name"),
        oninput: (e) => { v.name = e.target.value; onChange && onChange(v); } });
      const zoneS = h("select", { "aria-label": t("zone"), onchange: (e) => { v.zone = e.target.value || null; onChange && onChange(v); } },
        h("option", { value: "" }, t("zone_unknown")),
        ...rec.ZONES.map((z) => h("option", { value: z }, t(`zone_${z}`))));
      zoneS.value = v.zone || "";
      const casesI = h("input", { type: "number", inputmode: "numeric", min: "0", value: nn(v.cases, ""), "aria-label": t("cases_week"), placeholder: "0",
        oninput: (e) => { v.cases = e.target.value; onChange && onChange(v); } });
      const age = v.updatedAt ? Math.floor((Date.now() - v.updatedAt) / DAY) : null;
      return h("div", { class: "village-row" },
        field(t("village_name"), nameI),
        h("div", { class: "pair" }, field(t("zone"), zoneS), field(t("cases_week"), casesI)),
        age !== null ? h("small", { class: age > 14 ? "stale" : "hint" }, age > 14 ? t("stale") : t("updated_ago", age)) : null,
        list.length > 1 || v.id ? h("button", { type: "button", class: "danger-link small", onclick: () => {
          if (v.id && rec.patients().some((p) => p.villageId === v.id)) { alert(t("village_in_use")); return; }
          list.splice(i, 1); v._removed = true; onChange && onChange(v); render();
        } }, t("delete_village")) : null);
    }), h("button", { type: "button", class: "secondary", onclick: () => { list.push({ name: "", zone: null, cases: "" }); render(); } }, `+ ${t("add_village")}`));
  };
  render();
  return wrap;
}

SCREENS.setup = () => {
  const err = h("p", { class: "form-error", role: "alert" });
  const pin1 = h("input", { type: "password", inputmode: "numeric", maxlength: "8", autocomplete: "new-password", class: "pin" });
  const pin2 = h("input", { type: "password", inputmode: "numeric", maxlength: "8", autocomplete: "new-password", class: "pin" });
  const post = h("input", { maxlength: "80", autocomplete: "organization" });
  const district = h("input", { maxlength: "80" });
  const nurse = h("input", { maxlength: "60", autocomplete: "name" });
  const vils = [{ name: "", zone: null, cases: "" }];

  async function create(demo) {
    err.textContent = "";
    if (!/^\d{4,8}$/.test(pin1.value)) { err.textContent = t("pin_short"); pin1.focus(); return; }
    if (pin1.value !== pin2.value) { err.textContent = t("pin_mismatch"); pin2.focus(); return; }
    if (!demo && !post.value.trim()) { err.textContent = t("post_name"); post.focus(); return; }
    await store.createVault(pin1.value);
    await rec.savePost({ name: post.value.trim() || "Demo health post", district: district.value.trim(), nurse: nurse.value.trim(), createdAt: Date.now() });
    for (const v of vils) if (v.name && v.name.trim()) await rec.saveVillage(v);
    if (demo) await rec.loadDemo();
    pin1.value = pin2.value = "";
    afterUnlock();
  }

  const restoreInput = restoreControl(() => afterUnlock());
  return h("form", { class: "setup", onsubmit: (e) => { e.preventDefault(); create(false); } },
    h("h1", {}, t("setup_title")),
    langSwitch(() => go("setup", null, { push: false })),
    h("p", {}, t("setup_intro")),
    field(t("pin"), pin1), field(t("pin_again"), pin2),
    h("h2", {}, t("post_h")),
    field(t("post_name"), post), field(t("district"), district), field(t("nurse"), nurse),
    h("h2", {}, t("villages_h")), h("p", { class: "hint" }, t("villages_hint")),
    villageEditor(vils),
    h("p", { class: "hint note" }, t("pilot_note")),
    err,
    h("div", { class: "dock" }, h("button", { class: "primary", type: "submit" }, t("start"))),
    h("button", { type: "button", class: "secondary wide", onclick: () => create(true) }, t("use_demo")),
    h("details", { class: "restore-box" }, h("summary", {}, t("restore")), restoreInput));
};

function afterUnlock() {
  store.askPersistent().then((ok) => { state.persistent = ok; });
  touch();
  state.stack = [];
  go("home", null, { push: false });
  syncOutbox();
}

/* ---------- auto-lock ---------- */
let lastActive = Date.now();
function touch() { lastActive = Date.now(); }
["pointerdown", "keydown"].forEach((ev) => window.addEventListener(ev, touch, { passive: true }));
function lockNow() { store.lock(); state.stack = []; go("lock", null, { push: false }); }
setInterval(() => { if (store.isUnlocked() && Date.now() - lastActive > AUTO_LOCK_MS) lockNow(); }, 15000);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && store.isUnlocked() && Date.now() - lastActive > AUTO_LOCK_MS) lockNow();
});

/* ---------- home: patient register ---------- */
SCREENS.home = () => {
  const list = h("ul", { class: "plist" });
  const search = h("input", { type: "search", placeholder: t("search"), "aria-label": t("search"), autocomplete: "off",
    oninput: () => draw() });
  function draw() {
    const q = search.value;
    const hits = rec.searchPatients(q).slice(0, 50);
    if (!hits.length) {
      fill(list, h("li", { class: "empty" }, rec.patients().length ? t("no_match") : t("no_patients")));
      return;
    }
    fill(list, ...hits.map((p) => {
      const last = rec.visitsFor(p.id)[0];
      return h("li", {}, h("button", { type: "button", onclick: () => go("patient", p.id) },
        h("span", { class: "pname" }, p.name, p.demo ? h("em", { class: "tag" }, t("demo_tag")) : null),
        h("span", { class: "psub" }, `${patientSub(p)}, ${p.id}`),
        last ? h("span", { class: "plast", "data-action": last.action }, `${fmtDate(last.at)}: ${x().actions[last.action]}`) : null));
    }));
  }
  draw();
  const post = rec.getPost() || {};
  const month = new Date(); month.setDate(1); month.setHours(0, 0, 0, 0);
  const s = rec.summary(month.getTime());
  return h("div", {},
    rec.hasDemo() ? h("p", { class: "banner" }, t("demo_banner")) : null,
    h("div", { class: "post" }, h("strong", {}, post.name || ""), post.district ? h("span", {}, post.district) : null),
    h("div", { class: "stats" },
      h("span", {}, h("b", {}, t("this_month")), " ", t("visits_n", s.visits)),
      s.tested ? h("span", {}, t("positive_n", s.positive, s.tested)) : null,
      s.byAction.REFER_URGENT ? h("span", {}, t("referred_n", s.byAction.REFER_URGENT)) : null),
    h("button", { type: "button", class: "primary", onclick: () => go("patientForm", null) }, `+ ${t("new_patient_btn")}`),
    h("div", { class: "searchbox" }, search),
    list);
};

/* ---------- patient form ---------- */
SCREENS.patientForm = (id) => {
  const p = id ? rec.patient(id) : null;
  const err = h("p", { class: "form-error", role: "alert" });
  const name = h("input", { value: p ? p.name : "", maxlength: "80", autocomplete: "off" });
  let sex = p ? p.sex : null;
  const sexSeg = h("div", { class: "seg" }, ...["F", "M"].map((s) => h("button", { type: "button", "aria-pressed": String(sex === s),
    onclick: (e) => { sex = s; sexSeg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false")); e.currentTarget.setAttribute("aria-pressed", "true"); } },
  s === "F" ? t("female") : t("male"))));
  const age = h("input", { type: "text", inputmode: "decimal", maxlength: "5", autocomplete: "off", value: p ? nn(rec.ageNow(p), "") : "" });
  const vSel = h("select", {}, h("option", { value: "" }, "—"), ...rec.villages().map((v) => h("option", { value: v.id }, v.name)));
  vSel.value = p ? p.villageId || "" : "";
  const phone = h("input", { type: "tel", inputmode: "tel", value: p ? p.phone : "", maxlength: "20", autocomplete: "off" });
  let fam = p ? p.familyHistory : false;
  const famChip = h("button", { type: "button", class: "chip", "aria-pressed": String(fam),
    onclick: (e) => { fam = !fam; e.currentTarget.setAttribute("aria-pressed", String(fam)); } }, t("family_history"));

  return h("form", { onsubmit: async (e) => {
    e.preventDefault();
    err.textContent = "";
    if (!name.value.trim()) { err.textContent = t("name_required"); name.focus(); return; }
    if (!sex) { err.textContent = t("sex_required"); return; }
    if (num(age.value) === null || !(num(age.value) >= 0 && num(age.value) < 130)) { err.textContent = t("age_required"); age.focus(); return; }
    if (!vSel.value) { err.textContent = t("village_required"); vSel.focus(); return; }
    const keepAge = p && rec.ageNow(p) === num(age.value);
    const saved = await rec.savePatient({ id: p ? p.id : null, name: name.value, sex, ageYears: keepAge ? p.ageYears : num(age.value),
      villageId: vSel.value, phone: phone.value, familyHistory: fam, demo: p ? p.demo : false });
    if (p) history.back(); else go("patient", saved.id, { push: false });
  } },
  backBtn(t("back_patients")),
  h("h1", {}, p ? `${t("edit")}: ${p.name}` : t("new_patient_btn")),
  field(t("name"), name),
  h("fieldset", { class: "field" }, h("legend", {}, t("sex")), sexSeg),
  field(t("age"), age, t("age_hint")),
  field(t("village"), vSel),
  field(t("phone"), phone),
  h("div", { class: "chips" }, famChip),
  err,
  h("div", { class: "dock" }, h("button", { class: "primary", type: "submit" }, t("save_patient"))));
};

/* ---------- patient page ---------- */
SCREENS.patient = (id) => {
  const p = rec.patient(id);
  if (!p) return SCREENS.home();
  const visits = rec.visitsFor(id);
  const recs = new Map(rec.recall(id, 1000).filter((m) => m.kind === "recommendation").map((m) => [m.visitId, m]));
  return h("div", {},
    backBtn(t("back_patients")),
    h("div", { class: "phead" },
      h("h1", {}, p.name, p.demo ? h("em", { class: "tag" }, t("demo_tag")) : null),
      h("p", {}, patientSub(p)),
      h("p", { class: "hint" }, [p.id, p.phone, p.familyHistory ? t("family_history") : null].filter(Boolean).join(", ")),
      h("button", { type: "button", class: "link", onclick: () => go("patientForm", id) }, t("edit"))),
    h("button", { type: "button", class: "primary", onclick: () => go("visit", { patientId: id }) }, t("new_visit_for")),
    h("h2", { class: "spaced" }, t("visits_h")),
    visits.length ? h("ol", { class: "vlist" }, ...visits.map((v) => {
      const m = recs.get(v.id);
      const fb = h("div", { class: "feedback" });
      if (m && !v.feedback) {
        fb.append(
          h("button", { type: "button", class: "yes", onclick: async () => { await rec.feedback(m.id, "helpful"); go("patient", id, { push: false }); } }, t("was_right")),
          h("button", { type: "button", class: "no", onclick: async () => { await rec.feedback(m.id, "wrong"); go("patient", id, { push: false }); } }, t("was_wrong")));
      }
      return h("li", { "data-action": v.action },
        h("strong", {}, x().actions[v.action]),
        h("span", { class: "hint" }, `${fmtDateTime(v.at)}, ${t("score").toLowerCase()} ${v.score}/100${v.intake.temperature_c ? `, ${Number(v.intake.temperature_c).toLocaleString(state.lang)} °C` : ""}, ${x().tests[v.intake.test_result]}`),
        v.feedback ? h("span", { class: "hint" }, v.feedback === "wrong" ? t("was_wrong") : t("was_right")) : fb);
    })) : h("p", { class: "hint" }, t("no_visits")));
};

/* ---------- visit (intake) ---------- */
function chip(key, label, set) {
  return h("button", { type: "button", class: "chip", "data-key": key, "aria-pressed": String(set.has(key)),
    onclick: (e) => { set.has(key) ? set.delete(key) : set.add(key); e.currentTarget.setAttribute("aria-pressed", String(set.has(key))); } }, label);
}

SCREENS.visit = ({ patientId, preset }) => {
  const p = rec.patient(patientId);
  const pre = preset || {};
  const sym = new Set(pre.symptoms || []);
  const dan = new Set(pre.danger_signs || []);
  const flags = new Set([pre.pregnant && "pregnant", pre.recent_travel && "travel", pre.household_cases && "household"].filter(Boolean));
  let test = pre.test_result || "not_done";
  const err = h("p", { class: "form-error", role: "alert" });
  const temp = h("input", { type: "text", inputmode: "decimal", maxlength: "5", autocomplete: "off", placeholder: state.lang === "fr" ? "38,5" : "38.5", value: nn(pre.temperature_c, "") });
  const days = h("input", { type: "number", inputmode: "numeric", min: "0", max: "60", value: nn(pre.fever_days, "") });
  const notes = h("textarea", { rows: "2", maxlength: "300" });
  const age = rec.ageNow(p);
  const canBePregnant = p.sex === "F" && age !== null && age >= 12 && age <= 50;
  const tests = h("div", { class: "tests", role: "radiogroup" }, ...TEST_RESULTS.map((r) => h("button", { type: "button", role: "radio", "aria-checked": String(test === r), "data-key": r,
    onclick: () => { test = r; tests.querySelectorAll("button").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.key === r))); } }, x().tests[r])));

  return h("form", { novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    const tv = num(temp.value);
    if (tv !== null && !(tv >= 30 && tv <= 45)) {
      err.textContent = state.lang === "fr" ? "La température doit être entre 30 et 45 °C." : "Temperature must be between 30 and 45 °C.";
      temp.focus(); return;
    }
    const fd = num(days.value);
    if (fd !== null && !(fd >= 0 && fd <= 60)) {
      err.textContent = state.lang === "fr" ? "Jours de fièvre : entre 0 et 60." : "Days of fever: between 0 and 60.";
      days.focus(); return;
    }
    const intake = {
      patient_id: p.id, temperature_c: tv, fever_days: num(days.value), age_years: age, pregnant: flags.has("pregnant"),
      symptoms: SYMPTOMS.filter((s) => sym.has(s)), danger_signs: DANGER_SIGNS.filter((d) => dan.has(d)),
      recent_travel: flags.has("travel"), household_cases: flags.has("household"), test_result: test, notes: notes.value.trim(),
    };
    await decide(p, intake);
  } },
  backBtn(p.name),
  h("div", { class: "who-line" }, h("strong", {}, p.name), h("span", {}, patientSub(p))),
  h("section", { class: "block vitals" }, field(t("temp"), temp), field(t("fever_days"), days)),
  h("section", { class: "block" }, h("div", { class: "chips" },
    canBePregnant ? chip("pregnant", t("pregnant"), flags) : null, chip("travel", t("travel"), flags), chip("household", t("household"), flags))),
  h("section", { class: "block" }, h("h2", {}, t("symptoms_h")), h("div", { class: "chips" }, ...SYMPTOMS.map((s) => chip(s, x().symptoms[s], sym)))),
  h("section", { class: "block danger-block" }, h("h2", {}, t("danger_h")), h("p", { class: "hint" }, t("danger_hint")),
    h("div", { class: "chips" }, ...DANGER_SIGNS.map((d) => chip(d, x().danger[d], dan)))),
  h("section", { class: "block" }, h("h2", {}, t("test_h")), tests),
  h("section", { class: "block" }, field(t("notes"), notes), err),
  h("div", { class: "dock" }, h("button", { class: "primary", type: "submit" }, t("check"))));
};

async function decide(p, intake) {
  const now = Date.now();
  const memories = rec.recall(p.id);
  const ev = extractEvidence(rec.evidenceRows(p), memories, null, p.id, now);
  const result = triage(intake, ev);
  const today = rec.localDate(now);
  const zone = ev.endemic_zone ? `${ev.village} ${ev.endemic_zone} zone` : "zone unknown";
  const visit = await rec.saveVisit({ patientId: p.id, intake, result, evidence: ev,
    observation: `Visit ${today}: ${describeIntake(intake)}.`,
    recommendation: `Visit ${today}: SangoDiag advised '${pack("en").actions[result.action]}' (malaria score ${result.score}/100, ${result.level}; ${zone}; test: ${intake.test_result}).` });
  // the result replaces the visit form in history
  go("result", { patientId: p.id, intake, ev, result, memories, visitId: visit.id }, { push: false });
  if (state.server) {
    if (navigator.onLine) askServer(intake, visit.id);
    else await rec.queue({ id: visit.id, intake, at: now });
  }
}

/* ---------- result ---------- */
const SRC_KEYS = { NURSE: "src_NURSE", Q1: "src_Q1", Q2: "src_Q2", Q3: "src_Q3", IMG: "src_IMG" };
const srcLabel = (cite) => { const k = cite.startsWith("MEM") ? "src_MEM" : SRC_KEYS[cite]; return k ? t(k) : cite; };

SCREENS.result = ({ patientId, result, memories }) => {
  const p = rec.patient(patientId);
  const X = x();
  const lastRec = memories.find((m) => m.kind === "recommendation");
  const memBlock = h("div", { class: "memory" }, h("p", {}, memories.length ? t("memory_some", memories.length) : t("memory_none")));
  if (memories.length) {
    memBlock.append(h("details", {}, h("summary", {}, t("memory_show")),
      ...memories.map((m) => h("div", { class: "rec" }, m.content, h("small", {}, `${fmtDateTime(m.timestamp)}, ${state.lang === "fr" ? "confiance" : "trust"} ${m.confidence.toFixed(2)}`)))));
  }
  const current = lastRec ? rec.recall(patientId, 1000).find((m) => m.id === lastRec.id) : null;
  if (current && !current.feedback) {
    const done = h("p", { class: "feedback-done", hidden: true });
    const box = h("div", { class: "feedback" },
      h("button", { type: "button", class: "yes", onclick: () => give("helpful") }, t("was_right")),
      h("button", { type: "button", class: "no", onclick: () => give("wrong") }, t("was_wrong")));
    async function give(kind) {
      const m = await rec.feedback(current.id, kind);
      box.hidden = true; done.textContent = t("feedback_done", m.confidence.toFixed(2)); done.hidden = false;
    }
    memBlock.append(h("p", { class: "hint", style: "margin:10px 0 0" }, t("feedback_q")), box, done);
  }
  const reasons = result.reasons.map((r) => h("li", {},
    h("span", { class: r.isKey ? "key" : "" }, renderReason(state.lang, r)),
    h("span", { class: r.points > 0 ? "pts up" : r.points < 0 ? "pts down" : "pts" }, r.points ? (r.points > 0 ? `+${r.points}` : String(r.points)) : ""),
    h("span", { class: "src" }, h("b", {}, `[${r.cite.startsWith("MEM") ? "MEM" : r.cite}]`), srcLabel(r.cite))));
  const diff = Object.entries(result.differential).sort((a, b) => b[1] - a[1]).map(([k, v]) =>
    h("li", {}, h("span", {}, X.diff[k]), h("b", {}, `${v}%`), h("span", { class: "bar-wrap" }, h("i", { style: `width:${v}%` }))));

  return h("div", { id: "result" },
    h("div", { class: "slab reveal", "data-action": result.action },
      h("p", { class: "who" }, `${p.name}, ${patientSub(p)}`),
      h("p", { class: "step" }, X.actions[result.action]),
      h("p", { class: "engine" }, t("engine_local"))),
    h("div", { class: "score" },
      h("p", { class: "score-label" }, t("score")),
      h("div", { class: "score-head" },
        h("span", { class: "score-num" }, String(result.score)),
        h("span", { class: "score-of" }, `${t("out_of")}, ${X.level[result.level]}`),
        h("span", { class: "score-conf" }, `${t("confidence")}: ${X.conf[result.confidence]}`)),
      h("div", { class: "meter", role: "img", "aria-label": `${t("score")} ${result.score}/100` }, h("i", { style: `width:${result.score}%` })),
      result.abstain ? h("p", { class: "weak" }, t("weak")) : null),
    memBlock,
    h("div", { class: "section" }, h("h2", {}, t("todo")), h("ol", { class: "todo" }, ...result.next_steps.map((s) => h("li", {}, renderStep(state.lang, s))))),
    h("div", { class: "section" }, h("h2", {}, t("why")), h("ul", { class: "why" }, ...reasons)),
    h("div", { class: "section" }, h("h2", {}, t("differential")), h("ul", { class: "diff" }, ...diff)),
    h("div", { class: "section", id: "server-result", hidden: true }),
    h("p", { class: "disclaimer" }, t("disclaimer")),
    h("div", { class: "dock" }, h("button", { type: "button", class: "primary", onclick: () => history.back() }, t("done"))));
};

/* ---------- server (optional) ---------- */
async function askServer(intake, visitId) {
  try {
    const ctrl = window.AbortController ? new AbortController() : null;
    const timer = setTimeout(() => ctrl && ctrl.abort(), 120000);
    const r = await fetch(`${state.server.replace(/\/$/, "")}/diagnose`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(intake), signal: ctrl ? ctrl.signal : undefined });
    clearTimeout(timer);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    const note = $("#server-result");
    if (note && data.report) {
      fill(note, h("h2", {}, t("engine_server")), h("div", { class: "server-note" }, data.report.replace(/\*\*(.+?)\*\*/g, "$1").replace(/^\s*[-*] /gm, "• ")));
      note.hidden = false;
    }
  } catch (e) { await rec.queue({ id: visitId, intake, at: Date.now() }); }
}
async function syncOutbox() {
  if (!state.server || !navigator.onLine || !store.isUnlocked()) return;
  for (const item of rec.outbox()) {
    try {
      const r = await fetch(`${state.server.replace(/\/$/, "")}/diagnose`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(item.intake) });
      if (r.ok) await rec.unqueue(item.id); else break;
    } catch (e) { break; }
  }
}

/* ---------- settings ---------- */
function langSwitch(after) {
  return h("div", { class: "seg", role: "group", "aria-label": t("language") }, ...LANGS.map((l) => h("button", { type: "button", "aria-pressed": String(state.lang === l),
    onclick: async () => { state.lang = l; await store.setPlain("lang", l); applyChrome(); after(); } }, l === "fr" ? "Français" : "English")));
}

function download(name, text, type) {
  const blob = new Blob([text], { type });
  const file = new File([blob], name, { type });
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    navigator.share({ files: [file], title: name }).catch(() => {});
    return;
  }
  const a = h("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

function restoreControl(onDone) {
  const msg = h("p", { class: "hint", role: "status" });
  const fileI = h("input", { type: "file", accept: ".json,application/json" });
  const pinI = h("input", { type: "password", inputmode: "numeric", maxlength: "8", class: "pin" });
  return h("div", { class: "restore" }, fileI, field(t("restore_pin"), pinI),
    h("button", { type: "button", class: "secondary", onclick: async () => {
      const f = fileI.files && fileI.files[0];
      if (!f) return;
      let data;
      try { data = JSON.parse(await readText(f)); } catch (e) { msg.textContent = t("not_backup"); return; }
      if (!data || data.format !== "sangodiag-backup") { msg.textContent = t("not_backup"); return; }
      if (!confirm(t("restore_confirm"))) return;
      const ok = await store.restore(data, pinI.value);
      pinI.value = "";
      if (ok) { msg.textContent = t("restored"); onDone(); } else msg.textContent = t("restore_failed");
    } }, t("restore")), msg);
}

SCREENS.settings = () => {
  const post = rec.getPost() || {};
  const status = h("p", { class: "hint", role: "status" });
  const postName = h("input", { value: post.name || "", maxlength: "80" });
  const district = h("input", { value: post.district || "", maxlength: "80" });
  const vils = rec.villages().map((v) => ({ ...v }));
  const dirty = new Set();
  const server = h("input", { type: "url", inputmode: "url", value: state.server, placeholder: "https://…", autocomplete: "off" });
  const serverStatus = h("span", { class: "hint" });
  const oldPin = h("input", { type: "password", inputmode: "numeric", maxlength: "8", class: "pin" });
  const newPin = h("input", { type: "password", inputmode: "numeric", maxlength: "8", class: "pin" });
  const month = new Date(); month.setDate(1); month.setHours(0, 0, 0, 0);
  const stamp = rec.localDate(Date.now());
  const slug = (post.name || "sangodiag").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  async function saveAll() {
    await rec.savePost({ name: postName.value.trim(), district: district.value.trim() });
    for (const v of dirty) {
      if (v._removed) { if (v.id) await store.remove("village", v.id); continue; }
      if (v.name && v.name.trim()) await rec.saveVillage(v);
    }
    dirty.clear();
    status.textContent = t("saved");
  }

  return h("div", { class: "settings" },
    backBtn(),
    h("h1", {}, t("settings")),
    h("h2", {}, t("language")), langSwitch(() => go("settings", null, { push: false })),

    h("h2", { class: "spaced" }, t("post_h")),
    field(t("post_name"), postName), field(t("district"), district),
    h("h3", {}, t("villages_h")), h("p", { class: "hint" }, t("villages_hint")),
    villageEditor(vils, (v) => dirty.add(v)),
    h("div", { class: "row" }, h("button", { type: "button", class: "primary small-primary", onclick: saveAll }, t("save")), status),

    h("h2", { class: "spaced" }, t("export_h")),
    h("p", { class: "hint" }, t("export_hint")),
    h("div", { class: "stack" },
      h("button", { type: "button", class: "secondary", onclick: () => download(`sangodiag-${slug}-${stamp.slice(0, 7)}.csv`, "﻿" + rec.visitsCsv(month.getTime()), "text/csv") }, t("export_month")),
      h("button", { type: "button", class: "secondary", onclick: () => download(`sangodiag-${slug}-all-${stamp}.csv`, "﻿" + rec.visitsCsv(0), "text/csv") }, t("export_all")),
      h("button", { type: "button", class: "secondary", onclick: async () => download(`sangodiag-backup-${slug}-${stamp}.json`, JSON.stringify(await store.backup({ post: post.name, app: VERSION })), "application/json") }, t("backup"))),
    h("p", { class: "hint" }, t("backup_hint")),
    h("details", { class: "restore-box" }, h("summary", {}, t("restore")), restoreControl(() => afterUnlock())),
    h("p", { class: "hint" }, state.persistent ? t("storage_ok") : t("storage_warn")),

    h("h2", { class: "spaced" }, t("server_url")),
    h("p", { class: "hint" }, t("server_hint")),
    server,
    h("div", { class: "row" }, h("button", { type: "button", class: "secondary", onclick: async () => {
      state.server = server.value.trim();
      await store.setPlain("server", state.server);
      serverStatus.textContent = t("saved");
      if (state.server && navigator.onLine) {
        try { const r = await fetch(`${state.server.replace(/\/$/, "")}/health`); serverStatus.textContent = r.ok ? t("live") : `HTTP ${r.status}`; syncOutbox(); }
        catch (e) { serverStatus.textContent = `${t("saved")} (${e.message})`; }
      }
    } }, t("save")), serverStatus),
    rec.outbox().length ? h("p", { class: "hint" }, t("pending_sync", rec.outbox().length)) : null,

    h("h2", { class: "spaced" }, t("security_h")),
    h("button", { type: "button", class: "secondary wide", onclick: lockNow }, t("lock_now")),
    h("details", { class: "restore-box" }, h("summary", {}, t("change_pin")),
      field(t("old_pin"), oldPin), field(t("new_pin"), newPin),
      h("button", { type: "button", class: "secondary", onclick: async () => {
        if (!/^\d{4,8}$/.test(newPin.value)) { alert(t("pin_short")); return; }
        const ok = await store.changePin(oldPin.value, newPin.value);
        oldPin.value = newPin.value = "";
        alert(ok ? t("pin_changed") : t("wrong_pin"));
      } }, t("change_pin"))),

    h("h2", { class: "spaced" }, t("demo_h")),
    h("p", { class: "hint" }, t("demo_data")),
    rec.hasDemo()
      ? h("div", { class: "stack" },
        h("label", { class: "field" }, h("span", {}, t("demo_cases")), h("select", { onchange: (e) => {
          const c = DEMO_CASES[e.target.value];
          if (!c || !rec.patient(c.intake.patient_id)) return;
          go("patient", c.intake.patient_id);
          go("visit", { patientId: c.intake.patient_id, preset: c.intake });
        } }, h("option", { value: "" }, "—"), ...Object.entries(DEMO_CASES).map(([k, c]) => h("option", { value: k }, c.label)))),
        h("button", { type: "button", class: "secondary", onclick: async () => { await rec.removeDemo(); go("settings", null, { push: false }); } }, t("remove_demo")))
      : h("button", { type: "button", class: "secondary wide", onclick: async () => { await rec.loadDemo(); go("settings", null, { push: false }); } }, t("load_demo")),

    h("button", { type: "button", class: "danger-link", onclick: async () => {
      if (!confirm(t("erase_confirm"))) return;
      await store.eraseAll(); state.stack = []; go("setup", null, { push: false });
    } }, t("erase_all")),
    h("p", { class: "hint version" }, `SangoDiag ${VERSION}. ${t("pilot_note")}`));
};

/* ---------- chrome ---------- */
function applyChrome() {
  document.documentElement.lang = state.lang;
  $("#tagline").textContent = t("tagline");
  $("#open-settings").setAttribute("aria-label", t("settings"));
  updateNet();
}
function updateNet() {
  const el = $("#net");
  el.classList.toggle("off", !navigator.onLine);
  el.textContent = navigator.onLine ? t("online") : (state.lang === "fr" ? "Hors ligne" : "Offline");
  el.title = navigator.onLine ? "" : t("offline");
}

async function init() {
  try { await start(); } catch (e) {
    // Usually: storage blocked (in-app browser, incognito tab) or a very old browser.
    if (window.__sdHelp) window.__sdHelp("failed");
  }
}

// Chrome before 84 ignores `gap` in flex layouts: detect it so index.html can add spacing with margins instead.
function flexGapWorks() {
  const box = h("div", { style: "display:flex;flex-direction:column;row-gap:1px;position:absolute;visibility:hidden" }, h("div"), h("div"));
  document.body.append(box);
  const ok = box.scrollHeight === 1;
  box.remove();
  return ok;
}

async function start() {
  if (!flexGapWorks()) document.documentElement.classList.add("no-flex-gap");
  state.lang = (await store.getPlain("lang")) || ((navigator.language || "en").startsWith("fr") ? "fr" : "en");
  state.server = (await store.getPlain("server")) || "";
  applyChrome();
  $("#open-settings").addEventListener("click", () => go("settings"));
  window.addEventListener("online", () => { updateNet(); syncOutbox(); });
  window.addEventListener("offline", updateNet);
  go((await store.isSetUp()) ? "lock" : "setup", null, { push: false });
  window.__sdReady = true;
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
}

init();
