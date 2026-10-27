"""
Deterministic Clinical Rules (Safety Layer)
===========================================
Rule-based malaria assessment derived from the WHO / Cameroon MINSANTE protocol.

Used for three things:
1. Offline diagnosis when the Nightshift LLM is unreachable.
2. A safety check that always flags severe malaria, whatever the LLM says.
3. A truthful one-line encounter summary for H-MEM.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Danger signs requiring parenteral Artesunate and referral (WHO severe malaria criteria)
SEVERE_SIGNS = {
    "confusion": "impaired consciousness / confusion",
    "unconscious": "impaired consciousness",
    "coma": "coma",
    "convulsion": "convulsions",
    "seizure": "convulsions",
    "prostration": "prostration",
    "unable to sit": "prostration",
    "unable to drink": "unable to drink or breastfeed",
    "persistent vomiting": "persistent vomiting (cannot take oral ACT)",
    "repeated vomiting": "persistent vomiting (cannot take oral ACT)",
    "respiratory distress": "respiratory distress",
    "difficulty breathing": "respiratory distress",
    "jaundice": "jaundice",
    "dark urine": "haemoglobinuria (dark urine)",
    "hemoglobinuria": "haemoglobinuria",
    "bleeding": "abnormal bleeding",
    "severe anemia": "severe anaemia",
    "severe anaemia": "severe anaemia",
}

POSITIVE_MARKERS = ("positive", "positif", "trophozoite", "schizont", "gametocyte", "parasites seen", "parasites visible")
NEGATIVE_MARKERS = ("negative", "négatif", "negatif", "no parasite", "not detected")

# Artemether 20mg / Lumefantrine 120mg tablets per dose, by body weight (WHO)
COARTEM_WEIGHT_BANDS = [
    (5, 15, 1),
    (15, 25, 2),
    (25, 35, 3),
    (35, 1000, 4),
]


@dataclass
class Assessment:
    patient_id: str
    test_result: str  # "positive" | "negative" | "unknown"
    temperature: Optional[float]
    severe_signs: List[str] = field(default_factory=list)
    village: Optional[str] = None
    endemic_zone: Optional[str] = None
    active_cases: Optional[str] = None
    breeding_site_risk: Optional[str] = None
    family_history: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    recent_travel: bool = False
    visit_findings: List[str] = field(default_factory=list)
    weight_kg: Optional[float] = None

    @property
    def is_under_five(self) -> bool:
        return self.age is not None and self.age < 5

    @property
    def is_severe(self) -> bool:
        return self.test_result == "positive" and bool(self.severe_signs)

    @property
    def diagnosis(self) -> str:
        if self.test_result == "positive":
            return "Severe malaria (suspected)" if self.severe_signs else "Uncomplicated P. falciparum malaria"
        if self.test_result == "negative":
            return "Malaria test negative - investigate other causes of fever"
        return "Malaria not confirmed - parasitological test required"

    @property
    def treatment(self) -> str:
        if self.is_severe:
            return "IV/IM Artesunate + urgent referral"
        if self.test_result == "positive":
            return "Artemether-Lumefantrine (Coartem) 6-dose course"
        if self.test_result == "negative":
            return "No antimalarial; treat symptoms, look for other causes"
        return "Perform RDT or microscopy before any antimalarial"


def parse_test_result(image_result: str) -> str:
    """A positive finding wins over a negative one (e.g. RDT negative but smear positive)."""
    text = (image_result or "").lower()
    if any(m in text for m in POSITIVE_MARKERS):
        return "positive"
    if any(m in text for m in NEGATIVE_MARKERS):
        return "negative"
    return "unknown"


def parse_temperature(*texts: str) -> Optional[float]:
    for text in texts:
        match = re.search(r"(\d{2}(?:[.,]\d)?)\s*°?\s*c\b", (text or "").lower())
        if match:
            return float(match.group(1).replace(",", "."))
    return None


def find_severe_signs(symptoms: str) -> List[str]:
    text = (symptoms or "").lower()
    found = []
    for keyword, label in SEVERE_SIGNS.items():
        if keyword in text and label not in found:
            found.append(label)
    return found


def coartem_tablets_per_dose(weight_kg: float) -> Optional[int]:
    for low, high, tablets in COARTEM_WEIGHT_BANDS:
        if low <= weight_kg < high:
            return tablets
    return None


def _is_true(value: Any) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def assess(patient_id: str, symptoms: str, image_result: str,
           records: Optional[List[Dict[str, Any]]] = None,
           weight_kg: Optional[float] = None) -> Assessment:
    """Build an assessment from the presenting case and the Zetaris rows retrieved for this patient."""
    record: Dict[str, Any] = {}
    for row in records or []:
        if isinstance(row, dict) and str(row.get("patient_id", patient_id)) == str(patient_id):
            record.update({k: v for k, v in row.items() if v is not None})

    temperature = parse_temperature(symptoms)
    if temperature is None and record.get("fever_temp_c") not in (None, ""):
        try:
            temperature = float(record["fever_temp_c"])
        except (TypeError, ValueError):
            pass

    visit_findings = [label for col, label in (("headache", "headache"), ("body_pain", "body pain"), ("nausea", "nausea"))
                      if _is_true(record.get(col))]

    return Assessment(
        patient_id=str(patient_id),
        test_result=parse_test_result(image_result),
        temperature=temperature,
        severe_signs=find_severe_signs(symptoms),
        village=record.get("village"),
        endemic_zone=record.get("endemic_zone"),
        active_cases=record.get("active_cases_this_week"),
        breeding_site_risk=record.get("breeding_site_risk"),
        family_history=record.get("family_history_malaria"),
        age=_to_int(record.get("age")),
        gender=record.get("gender"),
        recent_travel=_is_true(record.get("recent_travel")),
        visit_findings=visit_findings,
        weight_kg=weight_kg,
    )


def render_report(a: Assessment) -> str:
    """Full markdown report, used when the LLM is unavailable."""
    lines = ["### CLINICAL ASSESSMENT (rule-based, offline mode)", ""]

    lines.append("**1. Patient & epidemiological context (Zetaris):**")
    if a.village:
        if a.age is not None:
            lines.append(f"- Patient: {a.age} years, {a.gender or 'sex unknown'}"
                         + (" - **under 5: high-risk group**" if a.is_under_five else ""))
        lines.append(f"- Village: {a.village} | Endemic zone: {a.endemic_zone or 'unknown'} | "
                     f"Active cases this week: {a.active_cases or 'unknown'} | Breeding-site risk: {a.breeding_site_risk or 'unknown'}")
        lines.append(f"- Family history of malaria: {a.family_history or 'unknown'}")
        if a.recent_travel:
            lines.append("- **Recent travel reported**: exposure may have occurred outside the home village.")
        if a.visit_findings:
            lines.append(f"- Findings at last recorded visit: {', '.join(a.visit_findings)}")
    else:
        lines.append("- No baseline record found for this patient in the federated data.")
    lines.append("")

    lines.append("**2. Diagnostic findings:**")
    lines.append(f"- Parasitological test: **{a.test_result.upper()}**")
    if a.temperature is not None:
        lines.append(f"- Temperature: {a.temperature} °C")
    else:
        lines.append("- Temperature: **not recorded - measure it now** (axillary)")
    if a.severe_signs:
        lines.append(f"- Danger signs: **{', '.join(a.severe_signs)}**")
    lines.append(f"- Conclusion: **{a.diagnosis}**")
    lines.append("")

    lines.append("**3. Management:**")
    if a.is_severe:
        lines.append("- **EMERGENCY:** give pre-referral Artesunate (IM 2.4 mg/kg, or rectal if IM unavailable) "
                     "and transfer immediately to the nearest regional hospital for IV Artesunate.")
    elif a.test_result == "positive":
        tablets = coartem_tablets_per_dose(a.weight_kg) if a.weight_kg else None
        if a.weight_kg and not tablets:
            lines.append(f"- Weight {a.weight_kg:g} kg is below the 5 kg Coartem band: refer for specialist dosing.")
        elif tablets:
            lines.append(f"- Artemether 20mg / Lumefantrine 120mg (Coartem): **{tablets} tablet(s) per dose** "
                         f"for {a.weight_kg:g} kg, at 0h, 8h, then twice daily on days 2 and 3 (6 doses), with fatty food or milk.")
        else:
            if a.is_under_five or (a.age is not None and a.age < 15):
                lines.append("- **Child: weigh before dosing.**")
            lines.append("- Artemether 20mg / Lumefantrine 120mg (Coartem), 6 doses at 0h, 8h, then twice daily on days 2 and 3, "
                         "with fatty food or milk. Tablets per dose by weight: 5-14 kg: 1 | 15-24 kg: 2 | 25-34 kg: 3 | 35 kg+: 4.")
        lines.append("- Return immediately if danger signs appear (vomiting everything, confusion, convulsions, dark urine).")
    elif a.test_result == "negative":
        lines.append("- Do not give antimalarials. Look for other causes of fever (respiratory infection, typhoid, UTI, dengue).")
        lines.append("- Re-test if fever persists beyond 48 hours.")
    else:
        lines.append("- Perform an RDT or microscopy before prescribing; WHO requires parasitological confirmation.")

    if a.temperature is not None and a.temperature > 38.5 and not a.is_severe:
        lines.append("- Paracetamol 15 mg/kg (adult 1 g) every 6 hours for fever, plus oral rehydration.")
    if a.severe_signs and a.test_result != "positive":
        lines.append(f"- Danger signs present ({', '.join(a.severe_signs)}): refer urgently whatever the test result.")

    return "\n".join(lines)


def safety_alert(a: Assessment) -> Optional[str]:
    """Banner appended to any LLM answer when the rules detect danger signs."""
    if not a.severe_signs:
        return None
    return (f"⚠️ SAFETY CHECK (rules engine): danger signs detected ({', '.join(a.severe_signs)}). "
            "Urgent referral required; pre-referral Artesunate if malaria is confirmed.")


def encounter_summary(a: Assessment, symptoms: str, image_result: str) -> str:
    return (f"Symptoms: {symptoms} | Test: {image_result} | "
            f"Diagnosis: {a.diagnosis} | Plan: {a.treatment}")
