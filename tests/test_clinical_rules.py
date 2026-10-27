"""
Test Suite: Clinical rules and the end-to-end agent loop (offline mode)
=======================================================================
Verifies that the diagnosis depends on the actual case and the patient's Zetaris record.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import clinical_rules
from agent.engine_h_mem import get_patient_context
from agent.main import diagnose_patient


def test_parse_test_result():
    assert clinical_rules.parse_test_result("RDT: HRP2 line positive") == "positive"
    assert clinical_rules.parse_test_result("Smear: ring-form trophozoites visible") == "positive"
    assert clinical_rules.parse_test_result("RDT: HRP2 negative") == "negative"
    assert clinical_rules.parse_test_result("RDT negative; smear positive") == "positive"
    assert clinical_rules.parse_test_result("not done") == "unknown"


def test_parse_temperature():
    assert clinical_rules.parse_temperature("High fever (39.4°C), chills") == 39.4
    assert clinical_rules.parse_temperature("fièvre 38,5 C") == 38.5
    assert clinical_rules.parse_temperature("chills only") is None


def test_coartem_weight_bands():
    assert clinical_rules.coartem_tablets_per_dose(10) == 1
    assert clinical_rules.coartem_tablets_per_dose(18) == 2
    assert clinical_rules.coartem_tablets_per_dose(30) == 3
    assert clinical_rules.coartem_tablets_per_dose(62) == 4


def test_severe_malaria_detected():
    a = clinical_rules.assess("x", "Fever 39.7°C, persistent vomiting, confusion", "RDT positive")
    assert a.is_severe
    assert "Artesunate" in a.treatment
    assert clinical_rules.safety_alert(a) is not None


def test_negative_test_gets_no_antimalarial():
    a = clinical_rules.assess("x", "Fever 38.2°C, cough", "RDT HRP2 negative")
    assert not a.is_severe
    report = clinical_rules.render_report(a)
    assert "Do not give antimalarials" in report
    assert "6 doses" not in report


def test_assessment_uses_zetaris_record():
    rows = [{"patient_id": "p1", "age": "3", "gender": "M", "village": "Garoua", "family_history_malaria": "TRUE",
             "recent_travel": "FALSE", "endemic_zone": "High", "active_cases_this_week": "35",
             "fever_temp_c": "40.3", "nausea": "TRUE", "headache": "FALSE"}]
    a = clinical_rules.assess("p1", "fever", "RDT positive", rows)
    assert a.village == "Garoua"
    assert a.temperature == 40.3
    assert a.is_under_five
    assert a.visit_findings == ["nausea"]
    report = clinical_rules.render_report(a)
    assert "under 5" in report
    assert "weigh before dosing" in report


def test_missing_temperature_is_flagged():
    rows = [{"patient_id": "p2", "village": "Bertoua", "fever_temp_c": None}]
    a = clinical_rules.assess("p2", "feels feverish", "RDT positive", rows)
    assert a.temperature is None
    assert "not recorded - measure it now" in clinical_rules.render_report(a)


def test_agent_loop_offline_is_grounded_on_patient():
    report = diagnose_patient(
        "f6b8d0e2-7a9c-4b1d-9465-6f7a8b9c0d06",
        "Fever (37.9°C), headache",
        "RDT HRP2 negative",
    )
    assert "Bafoussam" in report
    assert "NEGATIVE" in report
    memory = get_patient_context("f6b8d0e2-7a9c-4b1d-9465-6f7a8b9c0d06")
    assert "test negative" in memory
    assert "Coartem" not in memory


def test_agent_loop_reads_csv_record():
    # Bertoua visit has an empty temperature cell in clinical_visits.csv
    report = diagnose_patient("d4f6b8c0-5e7a-4f9b-b243-4d5e6f7a8b04", "body pain", "RDT positive")
    assert "Bertoua" in report
    assert "not recorded" in report


def test_agent_loop_unknown_patient():
    report = diagnose_patient("unknown-patient", "Fever 39°C", "RDT positive")
    assert "No baseline record" in report
