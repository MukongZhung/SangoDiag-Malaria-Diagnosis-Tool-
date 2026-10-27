"""
Evidence fusion: transparent triage rules (no LLM in this step).

Turns the nurse's intake, the Zetaris evidence, the H-MEM history and any test or
image result into:
  * a malaria likelihood score (0-100) with every point explained
  * a rough differential (malaria / dengue / bacterial infection / other viral)
  * ONE next step from a fixed demo protocol
  * a confidence level, and an abstention when the evidence is too thin

The language model never decides the next step. Nemotron explains it, and the
critic checks that the explanation does not contradict it.

Protocol rules encoded here (demo protocol, not clinically validated):
  - Test before treat: treatment is only recommended after a positive RDT or
    microscopy result (WHO: confirm every suspected case with a parasite test).
  - Any danger sign means urgent referral, whatever the test says.
  - Fever within 28 days of a treated malaria episode (from H-MEM) means
    possible treatment failure: send for microscopy / clinician review.
  - The smear image model is a proxy (trained on Brazilian P. vivax smears). It
    can raise suspicion and ask for confirmation; it never confirms on its own.
  - SangoDiag does not compute drug doses. It points to the national protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DAY_MS = 24 * 60 * 60 * 1000

SYMPTOMS = {
    "fever": "Fever (reported)",
    "chills": "Chills / shivering",
    "headache": "Headache",
    "body_pain": "Body or joint pain",
    "vomiting": "Vomiting",
    "diarrhoea": "Diarrhoea",
    "cough": "Cough / runny nose",
    "rash": "Skin rash",
    "eye_pain": "Pain behind the eyes",
    "dysuria": "Pain when passing urine",
    "abdominal_pain": "Abdominal pain",
}

DANGER_SIGNS = {
    "cannot_drink": "Unable to drink or breastfeed",
    "vomits_everything": "Vomits everything",
    "convulsions": "Convulsions",
    "impaired_consciousness": "Lethargic, confused or unconscious",
    "prostration": "Unable to sit or stand",
    "breathing_difficulty": "Difficulty breathing",
    "jaundice": "Yellow eyes or skin",
    "dark_urine": "Dark or cola-coloured urine",
    "severe_pallor": "Severe pallor (very pale palms)",
    "bleeding": "Abnormal bleeding",
}

TEST_RESULTS = {
    "not_done": "No test yet",
    "rdt_positive": "RDT positive",
    "rdt_negative": "RDT negative",
    "smear_positive": "Microscopy positive",
    "smear_negative": "Microscopy negative",
    "inconclusive": "Test inconclusive / invalid",
}

ACTIONS = {
    "REFER_URGENT": "Refer urgently",
    "TREAT_PER_PROTOCOL": "Treat per national protocol",
    "DO_RDT": "Do a malaria RDT now",
    "SEND_LAB": "Send for microscopy / clinician review",
    "OTHER_CAUSE": "Malaria unlikely: look for another cause",
    "STANDARD_CARE": "No malaria signal: standard assessment",
}


@dataclass
class Intake:
    patient_id: str
    temperature_c: Optional[float] = None
    fever_days: Optional[int] = None
    age_years: Optional[float] = None
    pregnant: bool = False
    symptoms: List[str] = field(default_factory=list)
    danger_signs: List[str] = field(default_factory=list)
    recent_travel: bool = False
    household_cases: bool = False
    test_result: str = "not_done"
    notes: str = ""

    def has_fever(self) -> bool:
        return "fever" in self.symptoms or (self.temperature_c is not None and self.temperature_c >= 37.5)

    def describe(self) -> str:
        parts = []
        if self.age_years is not None:
            parts.append(f"age {self.age_years:g}")
        if self.pregnant:
            parts.append("pregnant")
        if self.temperature_c is not None:
            parts.append(f"temperature {self.temperature_c:.1f} C")
        if self.fever_days:
            parts.append(f"fever for {self.fever_days} day(s)")
        sx = [SYMPTOMS.get(s, s).lower() for s in self.symptoms]
        parts.append("symptoms: " + (", ".join(sx) if sx else "none reported"))
        ds = [DANGER_SIGNS.get(s, s).lower() for s in self.danger_signs]
        parts.append("danger signs: " + (", ".join(ds) if ds else "none"))
        if self.recent_travel:
            parts.append("recent travel")
        if self.household_cases:
            parts.append("fever cases in the household")
        parts.append("test: " + TEST_RESULTS.get(self.test_result, self.test_result))
        if self.notes:
            parts.append(f"nurse note: {self.notes}")
        return "; ".join(parts)


@dataclass
class Evidence:
    """What the agent found, each fact tied to where it came from."""
    village: Optional[str] = None
    endemic_zone: Optional[str] = None
    active_cases: Optional[int] = None
    family_history: Optional[bool] = None
    prior_visits: List[Dict[str, Any]] = field(default_factory=list)
    cites: Dict[str, str] = field(default_factory=dict)   # fact -> "Q1" / "MEM" / "IMG"
    recent_treatment_days: Optional[int] = None            # from H-MEM
    vision: Optional[Dict[str, Any]] = None


@dataclass
class TriageResult:
    score: int
    level: str                       # high / moderate / low
    action: str                      # key of ACTIONS
    action_label: str
    urgent: bool
    confidence: str                  # high / medium / low
    abstain: bool
    reasons: List[Dict[str, Any]]    # {"text", "points", "cite"}
    differential: Dict[str, int]     # percentages
    missing: List[str]
    next_steps: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def _truthy(v: Any) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes", "y")


def extract_evidence(query_rows: List[Dict[str, Any]], memory_items: List[Dict[str, Any]],
                     vision: Optional[Dict[str, Any]], patient_id: str, now_ms: int) -> Evidence:
    """Pull the facts the rules need out of whatever rows the planner fetched."""
    ev = Evidence(vision=vision)
    for q in query_rows:
        qid = q.get("qid") or "Q?"
        for row in q.get("rows", []):
            low = {str(k).lower(): v for k, v in row.items()}
            pid = low.get("patient_id")
            if pid is not None and str(pid) != str(patient_id) and "endemic_zone" not in low:
                continue
            if low.get("village") and ev.village is None and (pid is None or str(pid) == str(patient_id)):
                ev.village = str(low["village"])
                ev.cites["village"] = qid
            if low.get("endemic_zone") and ev.endemic_zone is None:
                if ev.village is None or str(low.get("village", ev.village)) == ev.village:
                    ev.endemic_zone = str(low["endemic_zone"])
                    ev.cites["endemic_zone"] = qid
                    cases = low.get("active_cases_this_week", low.get("active_cases"))
                    if cases not in (None, ""):
                        try:
                            ev.active_cases = int(float(cases))
                            ev.cites["active_cases"] = qid
                        except ValueError:
                            pass
            fh_col = "family_history_malaria" if "family_history_malaria" in low else "family_history"
            if fh_col in low and ev.family_history is None and (pid is None or str(pid) == str(patient_id)):
                ev.family_history = _truthy(low[fh_col])
                ev.cites["family_history"] = qid
            if low.get("visit_id") and (pid is None or str(pid) == str(patient_id)):
                if all(v.get("visit_id") != low["visit_id"] for v in ev.prior_visits):
                    ev.prior_visits.append({"visit_id": low["visit_id"], "visit_date": low.get("visit_date"),
                                            "fever_temp": low.get("fever_temp_c", low.get("fever_temp")),
                                            "body_pain": low.get("body_pain"), "headache": low.get("headache"),
                                            "nausea": low.get("nausea"), "cite": qid})
    for m in memory_items:
        if "rec:TREAT_PER_PROTOCOL" in m.get("tags", []) and m.get("timestamp"):
            days = int((now_ms - m["timestamp"]) / DAY_MS)
            if 0 <= days <= 28 and (ev.recent_treatment_days is None or days < ev.recent_treatment_days):
                ev.recent_treatment_days = days
                ev.cites["recent_treatment"] = f"MEM:{m['id']}"
    return ev


def triage(intake: Intake, ev: Evidence) -> TriageResult:
    reasons: List[Dict[str, Any]] = []

    def add(text: str, pts: int, cite: str = "NURSE", key: bool = False):
        reasons.append({"text": text, "points": pts, "cite": cite, "key": key})

    # Decisive facts first: they drive the next step regardless of the score.
    for d in intake.danger_signs:
        add(f"Danger sign: {DANGER_SIGNS.get(d, d)}", 0, "NURSE", key=True)
    if ev.recent_treatment_days is not None:
        when = "earlier today" if ev.recent_treatment_days == 0 else f"{ev.recent_treatment_days} day(s) ago"
        add(f"Treated for malaria {when} (patient history)", 0, ev.cites.get("recent_treatment", "MEM"), key=True)
    if intake.test_result != "not_done":
        add(TEST_RESULTS.get(intake.test_result, intake.test_result), 0, "NURSE", key=True)

    s = set(intake.symptoms)
    fever = intake.has_fever()
    score = 0
    if fever:
        score += 25
        add("Fever reported or measured", 25)
    if intake.temperature_c is not None and intake.temperature_c >= 39.0:
        score += 10
        add(f"High temperature ({intake.temperature_c:.1f} C)", 10)
    for key, pts in (("chills", 10), ("headache", 5), ("body_pain", 5), ("vomiting", 5)):
        if key in s:
            score += pts
            add(SYMPTOMS[key], pts)

    zone_pts = {"high": 20, "medium": 10, "low": 3}
    if ev.endemic_zone:
        pts = zone_pts.get(ev.endemic_zone.lower(), 0)
        score += pts
        add(f"{ev.village or 'Village'} is a {ev.endemic_zone} endemic zone", pts, ev.cites.get("endemic_zone", "Q?"))
    if ev.active_cases is not None and ev.active_cases >= 40:
        score += 5
        add(f"{ev.active_cases} active cases currently reported there", 5, ev.cites.get("active_cases", "Q?"))
    if ev.family_history or intake.household_cases:
        score += 5
        add("Malaria or fever in the family / household", 5,
            ev.cites.get("family_history", "NURSE") if ev.family_history else "NURSE")
    if intake.recent_travel:
        score += 5
        add("Recent travel", 5)
    febrile_visits = [v for v in ev.prior_visits if _num(v.get("fever_temp")) and _num(v.get("fever_temp")) >= 37.5]
    if febrile_visits:
        add(f"{len(febrile_visits)} earlier febrile visit(s) on record", 0, febrile_visits[0]["cite"])

    # Features pointing elsewhere
    if "cough" in s:
        score -= 10
        add("Cough / runny nose points to a respiratory cause", -10)
    if "dysuria" in s:
        score -= 10
        add("Pain on urination points to a urinary infection", -10)
    if "rash" in s or "eye_pain" in s:
        score -= 5
        add("Rash or pain behind the eyes: think of dengue", -5)

    vision = ev.vision or {}
    if vision.get("available") and vision.get("parasite_present") is not None:
        conf = float(vision.get("confidence") or 0)
        if vision["parasite_present"] and conf >= 0.5:
            score += 20
            add(f"Smear image model flags parasites (confidence {conf:.2f}, proxy model)", 20, "IMG")
        elif not vision["parasite_present"] and conf >= 0.5:
            score -= 5
            add(f"Smear image model sees no parasites (confidence {conf:.2f}, proxy model)", -5, "IMG")

    score = max(0, min(100, score))
    level = "high" if score >= 60 else "moderate" if score >= 35 else "low"

    # Differential (rough, relative)
    weights = {
        "Malaria": max(score, 1),
        "Dengue": 10 + (25 if "rash" in s else 0) + (20 if "eye_pain" in s else 0) + (15 if "bleeding" in intake.danger_signs else 0),
        "Bacterial infection (typhoid, pneumonia, UTI)": 10 + (20 if "cough" in s else 0) + (25 if "dysuria" in s else 0)
        + (15 if "abdominal_pain" in s else 0) + (10 if (intake.fever_days or 0) >= 5 else 0),
        "Other viral illness": 15 + (10 if "cough" in s else 0),
    }
    test = intake.test_result
    if test in ("rdt_positive", "smear_positive"):
        weights["Malaria"] = max(weights["Malaria"], 85) * 3
    elif test in ("rdt_negative", "smear_negative"):
        weights["Malaria"] = max(1, weights["Malaria"] // 5)
    total = sum(weights.values())
    differential = {k: round(100 * v / total) for k, v in weights.items()}

    # Missing evidence and confidence
    missing = []
    if not ev.endemic_zone:
        missing.append("endemic zone for the patient's village")
    if ev.village is None:
        missing.append("patient record in Zetaris")
    if intake.temperature_c is None:
        missing.append("measured temperature")
    confidence = "high" if not missing else "medium" if len(missing) == 1 else "low"

    # Decide ONE next step
    danger = [DANGER_SIGNS.get(d, d) for d in intake.danger_signs]
    positive = test in ("rdt_positive", "smear_positive")
    negative = test in ("rdt_negative", "smear_negative")
    steps: List[str] = []
    abstain = False
    if danger:
        action = "REFER_URGENT"
        steps = [f"Danger sign(s): {', '.join(danger)}. Arrange urgent transfer to the referral hospital.",
                 "Give pre-referral treatment only as your national protocol allows, and note the time given.",
                 "If an RDT is quick to do, do it, but do not delay the transfer for it."]
    elif fever and ev.recent_treatment_days is not None:
        action = "SEND_LAB"
        when = "earlier today" if ev.recent_treatment_days == 0 else f"{ev.recent_treatment_days} day(s) ago"
        steps = [f"Malaria was treated {when} and the fever is back: possible treatment failure.",
                 "Send a blood smear for microscopy and ask a clinician to review before treating again."]
    elif positive:
        action = "TREAT_PER_PROTOCOL"
        steps = ["Confirmed uncomplicated malaria: give first-line ACT following the national protocol chart (dose by weight).",
                 "Paracetamol for fever, oral fluids, sleep under a treated net.",
                 "Explain the danger signs and ask the family to come back at once if any appear, or in 3 days if the fever persists."]
    elif test == "inconclusive":
        action = "SEND_LAB"
        steps = ["The test was invalid or unclear. Repeat the RDT with a new cassette, or send a smear for microscopy."]
    elif negative and score >= 60:
        action = "SEND_LAB"
        steps = ["Negative test but a strong malaria picture: send a smear for microscopy.",
                 "Look for other causes at the same time (see differential)."]
    elif negative:
        action = "OTHER_CAUSE"
        steps = ["Malaria is unlikely with a negative test. Do not give antimalarials.",
                 "Assess for the other causes in the differential and treat or refer per your guidelines."]
    elif fever or score >= 35:
        action = "DO_RDT"
        steps = ["Suspected malaria: do an RDT now, before any antimalarial (test before treat).",
                 "If no RDT is available, send a smear for microscopy."]
        if vision.get("parasite_present"):
            steps.append("The image model flags parasites, but it is a proxy model: confirm with RDT or microscopy.")
    else:
        action = "STANDARD_CARE"
        abstain = True
        steps = ["Nothing here points to malaria. Continue the standard consultation.",
                 "SangoDiag is not confident enough to say more; use your own clinical judgement."]
    if confidence == "low" and action not in ("REFER_URGENT",):
        abstain = True
        steps.append("Key evidence is missing (" + ", ".join(missing) + "), so treat this as a weak suggestion.")

    return TriageResult(score=score, level=level, action=action, action_label=ACTIONS[action],
                        urgent=action == "REFER_URGENT", confidence=confidence, abstain=abstain,
                        reasons=reasons, differential=differential, missing=missing, next_steps=steps)


def _num(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
