// SangoDiag on-device triage rules.
// A line-by-line port of agent/triage.py so the phone reaches the same next step
// as the server when there is no network. No language model runs here.
// Parity with the Python rules is checked by tests/parity.test.mjs.
//
// Demo protocol, not clinically validated:
//   - Test before treat.
//   - Any danger sign means urgent referral.
//   - Fever within 28 days of a treated episode (patient memory) means possible
//     treatment failure: send for microscopy / clinician review.
//   - SangoDiag never computes drug doses.

export const DAY_MS = 24 * 60 * 60 * 1000;

export const SYMPTOMS = ["fever", "chills", "headache", "body_pain", "vomiting", "diarrhoea",
  "cough", "rash", "eye_pain", "dysuria", "abdominal_pain"];

export const DANGER_SIGNS = ["cannot_drink", "vomits_everything", "convulsions", "impaired_consciousness",
  "prostration", "breathing_difficulty", "jaundice", "dark_urine", "severe_pallor", "bleeding"];

export const TEST_RESULTS = ["not_done", "rdt_positive", "rdt_negative", "smear_positive",
  "smear_negative", "inconclusive"];

export const ACTIONS = ["REFER_URGENT", "TREAT_PER_PROTOCOL", "DO_RDT", "SEND_LAB", "OTHER_CAUSE", "STANDARD_CARE"];

const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const truthy = (v) => {
  if (v === null || v === undefined) return null;
  if (typeof v === "boolean") return v;
  return ["true", "1", "yes", "y"].includes(String(v).trim().toLowerCase());
};

// Python's round() rounds halves to the nearest even number.
export function pyRound(x) {
  const f = Math.floor(x);
  const diff = x - f;
  if (Math.abs(diff - 0.5) < 1e-9) return f % 2 === 0 ? f : f + 1;
  return Math.round(x);
}

export function hasFever(intake) {
  return (intake.symptoms || []).includes("fever") ||
    (intake.temperature_c !== null && intake.temperature_c !== undefined && intake.temperature_c >= 37.5);
}

/** Same logic as extract_evidence() in triage.py. */
export function extractEvidence(queryRows, memoryItems, vision, patientId, nowMs) {
  const ev = { village: null, endemic_zone: null, active_cases: null, family_history: null,
    prior_visits: [], cites: {}, recent_treatment_days: null, vision: vision || null };
  for (const q of queryRows) {
    const qid = q.qid || "Q?";
    for (const row of q.rows || []) {
      const low = {};
      for (const [k, v] of Object.entries(row)) low[String(k).toLowerCase()] = v;
      const pid = low.patient_id ?? null;
      const mine = pid === null || String(pid) === String(patientId);
      if (pid !== null && String(pid) !== String(patientId) && !("endemic_zone" in low)) continue;
      if (low.village && ev.village === null && mine) {
        ev.village = String(low.village);
        ev.cites.village = qid;
      }
      if (low.endemic_zone && ev.endemic_zone === null) {
        if (ev.village === null || String(low.village ?? ev.village) === ev.village) {
          ev.endemic_zone = String(low.endemic_zone);
          ev.cites.endemic_zone = qid;
          const cases = low.active_cases_this_week ?? low.active_cases;
          if (cases !== null && cases !== undefined && cases !== "" && Number.isFinite(Number(cases))) {
            ev.active_cases = Math.trunc(Number(cases));
            ev.cites.active_cases = qid;
          }
        }
      }
      const fhCol = "family_history_malaria" in low ? "family_history_malaria" : "family_history";
      if (fhCol in low && ev.family_history === null && mine) {
        ev.family_history = truthy(low[fhCol]);
        ev.cites.family_history = qid;
      }
      if (low.visit_id && mine) {
        if (ev.prior_visits.every((v) => v.visit_id !== low.visit_id)) {
          ev.prior_visits.push({ visit_id: low.visit_id, visit_date: low.visit_date ?? null,
            fever_temp: low.fever_temp_c ?? low.fever_temp ?? null, cite: qid });
        }
      }
    }
  }
  for (const m of memoryItems || []) {
    if ((m.tags || []).includes("rec:TREAT_PER_PROTOCOL") && m.timestamp) {
      const days = Math.trunc((nowMs - m.timestamp) / DAY_MS);
      if (days >= 0 && days <= 28 && (ev.recent_treatment_days === null || days < ev.recent_treatment_days)) {
        ev.recent_treatment_days = days;
        ev.cites.recent_treatment = `MEM:${m.id}`;
      }
    }
  }
  return ev;
}

/**
 * Same logic as triage() in triage.py. Reasons and steps are returned as
 * {key, params} so the screen can show them in English or French.
 */
export function triage(intake, ev) {
  const reasons = [];
  const add = (key, params, pts, cite = "NURSE", isKey = false) =>
    reasons.push({ key, params: params || {}, points: pts, cite, isKey });

  const symptoms = intake.symptoms || [];
  const dangerSigns = intake.danger_signs || [];
  const test = intake.test_result || "not_done";
  const temp = num(intake.temperature_c);

  for (const d of dangerSigns) add("r_danger", { sign: d }, 0, "NURSE", true);
  if (ev.recent_treatment_days !== null) {
    add("r_treated", { days: ev.recent_treatment_days }, 0, ev.cites.recent_treatment || "MEM", true);
  }
  if (test !== "not_done") add("r_test", { test }, 0, "NURSE", true);

  const s = new Set(symptoms);
  const fever = hasFever({ ...intake, temperature_c: temp });
  let score = 0;
  if (fever) { score += 25; add("r_fever", {}, 25); }
  if (temp !== null && temp >= 39.0) { score += 10; add("r_high_temp", { temp }, 10); }
  for (const [key, pts] of [["chills", 10], ["headache", 5], ["body_pain", 5], ["vomiting", 5]]) {
    if (s.has(key)) { score += pts; add("r_symptom", { symptom: key }, pts); }
  }

  const zonePts = { high: 20, medium: 10, low: 3 };
  if (ev.endemic_zone) {
    const pts = zonePts[ev.endemic_zone.toLowerCase()] || 0;
    score += pts;
    add("r_zone", { village: ev.village, zone: ev.endemic_zone }, pts, ev.cites.endemic_zone || "Q?");
  }
  if (ev.active_cases !== null && ev.active_cases >= 40) {
    score += 5;
    add("r_cases", { cases: ev.active_cases }, 5, ev.cites.active_cases || "Q?");
  }
  if (ev.family_history || intake.household_cases) {
    score += 5;
    add("r_family", {}, 5, ev.family_history ? (ev.cites.family_history || "NURSE") : "NURSE");
  }
  if (intake.recent_travel) { score += 5; add("r_travel", {}, 5); }
  const febrile = ev.prior_visits.filter((v) => num(v.fever_temp) && num(v.fever_temp) >= 37.5);
  if (febrile.length) add("r_prior", { n: febrile.length }, 0, febrile[0].cite);

  if (s.has("cough")) { score -= 10; add("r_cough", {}, -10); }
  if (s.has("dysuria")) { score -= 10; add("r_dysuria", {}, -10); }
  if (s.has("rash") || s.has("eye_pain")) { score -= 5; add("r_dengue", {}, -5); }

  const vision = ev.vision || {};
  if (vision.available && vision.parasite_present !== null && vision.parasite_present !== undefined) {
    const conf = Number(vision.confidence || 0);
    if (vision.parasite_present && conf >= 0.5) { score += 20; add("r_img_pos", { conf }, 20, "IMG"); }
    else if (!vision.parasite_present && conf >= 0.5) { score -= 5; add("r_img_neg", { conf }, -5, "IMG"); }
  }

  score = Math.max(0, Math.min(100, score));
  const level = score >= 60 ? "high" : score >= 35 ? "moderate" : "low";

  const weights = {
    malaria: Math.max(score, 1),
    dengue: 10 + (s.has("rash") ? 25 : 0) + (s.has("eye_pain") ? 20 : 0) + (dangerSigns.includes("bleeding") ? 15 : 0),
    bacterial: 10 + (s.has("cough") ? 20 : 0) + (s.has("dysuria") ? 25 : 0) + (s.has("abdominal_pain") ? 15 : 0)
      + ((intake.fever_days || 0) >= 5 ? 10 : 0),
    viral: 15 + (s.has("cough") ? 10 : 0),
  };
  if (test === "rdt_positive" || test === "smear_positive") weights.malaria = Math.max(weights.malaria, 85) * 3;
  else if (test === "rdt_negative" || test === "smear_negative") weights.malaria = Math.max(1, Math.floor(weights.malaria / 5));
  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  const differential = {};
  for (const [k, v] of Object.entries(weights)) differential[k] = pyRound((100 * v) / total);

  const missing = [];
  if (!ev.endemic_zone) missing.push("m_zone");
  if (ev.village === null) missing.push("m_record");
  if (temp === null) missing.push("m_temp");
  const confidence = !missing.length ? "high" : missing.length === 1 ? "medium" : "low";

  const positive = test === "rdt_positive" || test === "smear_positive";
  const negative = test === "rdt_negative" || test === "smear_negative";
  let steps = [];
  let abstain = false;
  let action;
  if (dangerSigns.length) {
    action = "REFER_URGENT";
    steps = [{ key: "s_refer_1", params: { signs: dangerSigns } }, { key: "s_refer_2" }, { key: "s_refer_3" }];
  } else if (fever && ev.recent_treatment_days !== null) {
    action = "SEND_LAB";
    steps = [{ key: "s_fail_1", params: { days: ev.recent_treatment_days } }, { key: "s_fail_2" }];
  } else if (positive) {
    action = "TREAT_PER_PROTOCOL";
    steps = [{ key: "s_treat_1" }, { key: "s_treat_2" }, { key: "s_treat_3" }];
  } else if (test === "inconclusive") {
    action = "SEND_LAB";
    steps = [{ key: "s_inconclusive" }];
  } else if (negative && score >= 60) {
    action = "SEND_LAB";
    steps = [{ key: "s_negstrong_1" }, { key: "s_negstrong_2" }];
  } else if (negative) {
    action = "OTHER_CAUSE";
    steps = [{ key: "s_other_1" }, { key: "s_other_2" }];
  } else if (fever || score >= 35) {
    action = "DO_RDT";
    steps = [{ key: "s_rdt_1" }, { key: "s_rdt_2" }];
    if (vision.parasite_present) steps.push({ key: "s_rdt_img" });
  } else {
    action = "STANDARD_CARE";
    abstain = true;
    steps = [{ key: "s_std_1" }, { key: "s_std_2" }];
  }
  if (confidence === "low" && action !== "REFER_URGENT") {
    abstain = true;
    steps.push({ key: "s_weak", params: { missing } });
  }

  return { score, level, action, urgent: action === "REFER_URGENT", confidence, abstain,
    reasons, differential, missing, next_steps: steps };
}

/** Plain-language summary of the visit, stored in the patient's memory. */
export function describeIntake(intake) {
  const parts = [];
  if (intake.age_years !== null && intake.age_years !== undefined) parts.push(`age ${intake.age_years}`);
  if (intake.pregnant) parts.push("pregnant");
  if (intake.temperature_c !== null && intake.temperature_c !== undefined) parts.push(`temperature ${Number(intake.temperature_c).toFixed(1)} C`);
  if (intake.fever_days) parts.push(`fever for ${intake.fever_days} day(s)`);
  parts.push("symptoms: " + ((intake.symptoms || []).join(", ") || "none reported"));
  parts.push("danger signs: " + ((intake.danger_signs || []).join(", ") || "none"));
  if (intake.recent_travel) parts.push("recent travel");
  if (intake.household_cases) parts.push("fever cases in the household");
  parts.push("test: " + (intake.test_result || "not_done"));
  if (intake.notes) parts.push(`nurse note: ${intake.notes}`);
  return parts.join("; ");
}
