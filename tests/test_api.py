"""REST API used by the Android field app: offline simulator + local CSV replica, no keys needed."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from agent import api


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SANGODIAG_MODEL_MODE", "offline")
    monkeypatch.setenv("SANGODIAG_DATA_MODE", "local")
    monkeypatch.setenv("SANGODIAG_LOG_DIR", tempfile.mkdtemp())
    monkeypatch.setattr(api.engine_h_mem, "DB_PATH", os.path.join(tempfile.mkdtemp(), "hmem.db"))
    monkeypatch.setattr(api.engine_h_mem, "_engine", None)
    return TestClient(api.app)


def test_patients_come_from_the_hackathon_csv(client):
    villages = {p["village"] for p in client.get("/patients").json()}
    assert {"Ebolowa", "Garoua", "Bafoussam"} <= villages


def test_diagnose_runs_the_agent(client):
    case = client.get("/demo-cases").json()["danger_signs"]
    body = client.post("/diagnose", json=case["intake"]).json()
    assert body["error"] is None
    assert body["triage"]["action"] == case["expected_action"]
    assert body["queries"] and all(q["source"] == "local-replica" for q in body["queries"])
    assert all(c["model_reported"] == "offline-simulator" for c in body["calls"])


def test_diagnose_validates_input(client):
    assert client.post("/diagnose", json={"patient_id": "x", "temperature_c": 99}).status_code == 422
