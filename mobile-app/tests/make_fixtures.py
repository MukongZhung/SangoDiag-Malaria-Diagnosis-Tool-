"""Run the Python triage rules (agent/triage.py) on many intakes and save the results.

tests/parity.test.mjs runs the phone's JavaScript rules on the same intakes and
checks that every score, next step, reason and instruction is identical.

    python3 mobile-app/tests/make_fixtures.py
"""
import csv
import itertools
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from agent.triage import ACTIONS, Intake, extract_evidence, triage  # noqa: E402

DAY = 24 * 60 * 60 * 1000
NOW = 1_800_000_000_000


def rows(name):
    with open(os.path.join(ROOT, "synthetic_data", name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


PATIENTS, EPI, VISITS = rows("patients.csv"), rows("regional_epidemiology.csv"), rows("clinical_visits.csv")


def lookup(pid, village=None):
    """Mirror of mobile-app/js/register.js lookup()."""
    out = []
    p = next((r for r in PATIENTS if r["patient_id"] == pid), None)
    if p:
        out.append({"qid": "Q1", "rows": [p]})
    v = p["village"] if p else village
    if v:
        z = [r for r in EPI if r["village"] == v]
        if z:
            out.append({"qid": "Q2", "rows": z})
    if p:
        vs = [r for r in VISITS if r["patient_id"] == pid]
        if vs:
            out.append({"qid": "Q3", "rows": vs})
    return out


SYMPTOMS = ["fever", "chills", "headache", "body_pain", "vomiting", "diarrhoea", "cough", "rash", "eye_pain",
            "dysuria", "abdominal_pain"]
DANGER = ["cannot_drink", "vomits_everything", "convulsions", "impaired_consciousness", "bleeding"]
TESTS = ["not_done", "rdt_positive", "rdt_negative", "smear_positive", "smear_negative", "inconclusive"]

rng = random.Random(7)
cases = []

with open(os.path.join(ROOT, "examples", "demo_cases.json"), encoding="utf-8") as f:
    demo = json.load(f)
for key, c in demo.items():
    mem = []
    if c.get("needs"):
        mem = [{"id": "m1", "tags": ["rec:TREAT_PER_PROTOCOL"], "timestamp": NOW - 3 * DAY}]
    cases.append({"name": f"demo:{key}", "intake": c["intake"], "village": None, "memory": mem,
                  "expected_action": c["expected_action"]})

ids = [p["patient_id"] for p in PATIENTS] + ["new-patient"]
villages = [r["village"] for r in EPI] + [None]
for i in range(400):
    pid = rng.choice(ids)
    intake = {
        "patient_id": pid,
        "temperature_c": rng.choice([None, 36.8, 37.5, 38.2, 39.0, 39.6, 40.4]),
        "fever_days": rng.choice([None, 1, 3, 5, 7]),
        "age_years": rng.choice([None, 2, 9, 27, 61]),
        "symptoms": sorted(rng.sample(SYMPTOMS, rng.randint(0, 5))),
        "danger_signs": sorted(rng.sample(DANGER, 1)) if rng.random() < 0.15 else [],
        "recent_travel": rng.random() < 0.3,
        "household_cases": rng.random() < 0.3,
        "test_result": rng.choice(TESTS),
    }
    mem = []
    if rng.random() < 0.25:
        mem = [{"id": f"m{i}", "tags": ["rec:" + rng.choice(list(ACTIONS))], "timestamp": NOW - rng.choice([0, 2, 10, 28, 29, 40]) * DAY}]
    cases.append({"name": f"random:{i}", "intake": intake, "village": rng.choice(villages) if pid == "new-patient" else None,
                  "memory": mem})

for c in cases:
    intake = Intake(**c["intake"])
    ev = extract_evidence(lookup(intake.patient_id, c["village"]), c["memory"], None, intake.patient_id, NOW)
    tr = triage(intake, ev)
    c["now"] = NOW
    c["expected"] = {"score": tr.score, "level": tr.level, "action": tr.action, "confidence": tr.confidence,
                     "abstain": tr.abstain, "differential": list(tr.differential.values()),
                     "reasons": [[r["text"], r["points"], r["cite"]] for r in tr.reasons],
                     "next_steps": tr.next_steps, "missing": tr.missing}
    if "expected_action" in c:
        assert tr.action == c["expected_action"], c["name"]

with open(os.path.join(HERE, "fixtures.json"), "w", encoding="utf-8") as f:
    json.dump(cases, f, indent=0)
print(f"wrote {len(cases)} cases;", "actions:", sorted({c['expected']['action'] for c in cases}))
