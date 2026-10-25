"""
Test Suite: Meterless Engine (H-MEM) Persistent Memory Verification
==================================================================
Judges and automated CI can execute:
    pytest tests/test_engine.py

Verifies:
1. Engine saves patient clinical intake to SQLite (h_mem.db).
2. Engine retrieves persisted context across separate calls.
3. Engine updates existing patient context longitudinally without data loss.
"""

import os
import sys
import tempfile
import sqlite3
try:
    import pytest
except ImportError:
    pytest = None

# Ensure agent package can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.engine_h_mem import save_patient_context, get_patient_context, list_all_memories


def test_h_mem_save_and_retrieve():
    """Verify that clinical memory is correctly persisted and retrieved."""
    test_id = "test-patient-qa-001"
    initial_note = "Patient from Buea with fever 39.1C, diagnosed with uncomplicated P. falciparum."

    # Save context to H-MEM
    save_patient_context(test_id, initial_note)

    # Retrieve from H-MEM
    retrieved = get_patient_context(test_id)
    assert retrieved is not None, "Expected context to be found in H-MEM"
    assert "Buea" in retrieved
    assert "P. falciparum" in retrieved


def test_h_mem_longitudinal_update():
    """Verify that multiple encounters are merged into a longitudinal record."""
    test_id = "test-patient-qa-002"
    first_encounter = "Intake: Tested positive on RDT. Prescribed Artemether-Lumefantrine."
    followup_encounter = "Followup Day 3: Afebril (36.8C), parasite clearance confirmed, completed course."

    save_patient_context(test_id, first_encounter)
    save_patient_context(test_id, followup_encounter)

    updated = get_patient_context(test_id)
    assert updated is not None
    assert "Intake" in updated
    assert "Followup Day 3" in updated
    assert "Artemether-Lumefantrine" in updated


def test_h_mem_nonexistent_patient():
    """Verify that querying an unknown patient safely returns None without throwing."""
    unknown_id = "non-existent-patient-999999"
    result = get_patient_context(unknown_id)
    assert result is None


if __name__ == "__main__":
    print("\n[RUNNING H-MEM PERSISTENT MEMORY ENGINE TESTS]")
    test_h_mem_save_and_retrieve()
    print("  ✓ test_h_mem_save_and_retrieve PASSED")
    test_h_mem_longitudinal_update()
    print("  ✓ test_h_mem_longitudinal_update PASSED")
    test_h_mem_nonexistent_patient()
    print("  ✓ test_h_mem_nonexistent_patient PASSED")
    print("[ALL H-MEM ENGINE TESTS PASSED SUCCESSFULLY!]\n")

