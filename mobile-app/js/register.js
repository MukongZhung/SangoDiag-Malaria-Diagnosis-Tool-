// Read-only copy of the SANGODIAG tables, bundled with the app so it works with no network.
// Each lookup is labelled like a query (Q1, Q2, Q3) so every reason can cite where it came from.
import { BUNDLE } from "./data.js";

export const PATIENTS = BUNDLE.patients;
export const EPIDEMIOLOGY = BUNDLE.epidemiology;
export const DEMO_CASES = BUNDLE.demo_cases;
export const VILLAGES = EPIDEMIOLOGY.map((r) => r.village).sort();

export function findPatient(id) {
  return PATIENTS.find((p) => p.patient_id === id) || null;
}

/**
 * Returns the evidence rows the rules need, in the same shape the server agent
 * gets back from Zetaris: [{qid, source, rows}].
 *   Q1 patient register   (patients)
 *   Q2 district data      (regional_epidemiology)
 *   Q3 past visits        (clinical_visits)
 */
export function lookup(patientId, villageForNewPatient) {
  const out = [];
  const p = findPatient(patientId);
  if (p) out.push({ qid: "Q1", source: "patients", rows: [p] });
  const village = p ? p.village : villageForNewPatient;
  if (village) {
    const zone = EPIDEMIOLOGY.filter((r) => r.village === village);
    if (zone.length) out.push({ qid: "Q2", source: "regional_epidemiology", rows: zone });
  }
  if (p) {
    const visits = BUNDLE.visits.filter((v) => v.patient_id === patientId);
    if (visits.length) out.push({ qid: "Q3", source: "clinical_visits", rows: visits });
  }
  return out;
}
