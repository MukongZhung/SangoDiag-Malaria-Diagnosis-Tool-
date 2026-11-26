// The phone's rules must give exactly what agent/triage.py gives.
// Regenerate fixtures with: python3 mobile-app/tests/make_fixtures.py
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { extractEvidence, triage } from "../js/triage.js";
import { renderReason, renderStep } from "../js/i18n.js";
import { lookup } from "../js/register.js";

// fixtures.json is generated (not committed): python3 mobile-app/tests/make_fixtures.py
const cases = JSON.parse(readFileSync(new URL("./fixtures.json", import.meta.url), "utf8"));

test(`parity with agent/triage.py on ${cases.length} intakes`, () => {
  for (const c of cases) {
    const ev = extractEvidence(lookup(c.intake.patient_id, c.village), c.memory, null, c.intake.patient_id, c.now);
    const r = triage(c.intake, ev);
    const e = c.expected;
    const got = {
      score: r.score, level: r.level, action: r.action, confidence: r.confidence, abstain: r.abstain,
      differential: Object.values(r.differential),
      reasons: r.reasons.map((x) => [renderReason("en", x), x.points, x.cite]),
      next_steps: r.next_steps.map((s) => renderStep("en", s)),
    };
    const want = { ...e, next_steps: e.next_steps.map((x) => x.replace("patient record in Zetaris", "patient's village in the register")) };
    delete want.missing;
    assert.deepEqual(got, want, c.name);
  }
});

test("every reason and step also renders in French", () => {
  for (const c of cases) {
    const ev = extractEvidence(lookup(c.intake.patient_id, c.village), c.memory, null, c.intake.patient_id, c.now);
    const r = triage(c.intake, ev);
    for (const x of r.reasons) assert.ok(renderReason("fr", x), c.name);
    for (const s of r.next_steps) assert.ok(renderStep("fr", s), c.name);
  }
});

test("demo cases give the expected next step", () => {
  for (const c of cases.filter((x) => x.expected_action)) {
    const ev = extractEvidence(lookup(c.intake.patient_id, c.village), c.memory, null, c.intake.patient_id, c.now);
    assert.equal(triage(c.intake, ev).action, c.expected_action, c.name);
  }
});
