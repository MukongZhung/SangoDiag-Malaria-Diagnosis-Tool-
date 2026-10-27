"""
Clinical H-MEM adapter tests (agent/engine_h_mem.py): the engine as the agent uses it.
The engine's own spec compliance is in test_engine_conformance.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import engine_h_mem as mem  # noqa: E402
from agent.hmem import HMEM  # noqa: E402


def _h(tmp_path):
    return HMEM(db_path=str(tmp_path / "h.db"), actor="test")


def test_first_visit_has_no_memory(tmp_path):
    r = mem.recall("p-new", "fever and chills", hmem=_h(tmp_path))
    assert r["count"] == 0 and r["context"] == ""


def test_encounter_is_recalled_next_visit_across_restart(tmp_path):
    db = str(tmp_path / "h.db")
    ids = mem.remember_encounter("p101", "Visit: temperature 39.4 C, RDT positive.",
                                 "SangoDiag advised 'Treat per national protocol'.", "nemotron", "run-1",
                                 action="TREAT_PER_PROTOCOL", hmem=HMEM(db_path=db))
    later = HMEM(db_path=db)  # new process, same device
    r = mem.recall("p101", "fever again", hmem=later)
    assert r["count"] == 2 and {i["id"] for i in r["items"]} == set(ids)
    assert "[MEMORY CONTEXT]" in r["context"] and "RDT positive" in r["context"]
    rec = next(i for i in r["items"] if i["source"] == "agent:nemotron")
    assert "rec:TREAT_PER_PROTOCOL" in rec["tags"] and rec["confidence"] == 0.6


def test_memories_never_cross_patients(tmp_path):
    h = _h(tmp_path)
    mem.remember_encounter("A", "Visit: RDT positive.", "advised treat", "m", "r1", hmem=h)
    assert mem.recall("B", "RDT positive", hmem=h)["count"] == 0


def test_nurse_feedback_updates_confidence_and_is_audited(tmp_path):
    h = _h(tmp_path)
    _, rec = mem.remember_encounter("A", "Visit.", "advised RDT", "m", "r1", hmem=h)
    out = mem.feedback(rec, "wrong", hmem=h)
    assert out["confidence"] == 0.4 and "review" in out["tags"]
    actions = [e["action"] for e in mem.patient_ledger("A", hmem=h)]
    assert actions.count("create") == 2 and "feedback" in actions
