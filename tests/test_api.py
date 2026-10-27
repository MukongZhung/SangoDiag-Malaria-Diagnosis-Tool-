"""
Test Suite: REST API used by the Android field app (offline mode)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from agent.api import app

client = TestClient(app)


def test_health_reports_offline_mode():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["nightshift"] == "offline-rules"


def test_diagnose_returns_structured_result():
    resp = client.post("/diagnose", json={
        "patient_id": "b2d4f6a8-3c5e-4d7f-9a21-2b3c4d5e6f02",
        "symptoms": "Fever (39.8°C), chills",
        "image_result": "RDT HRP2 positive",
        "weight_kg": 30,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["assessment"]["village"] == "Ebolowa"
    assert body["assessment"]["recent_travel"] is True
    assert body["assessment"]["coartem_tablets_per_dose"] == 3
    assert body["sql_queries"]
    assert body["llm_calls"][0]["mode"] == "offline-rules"
    assert client.get("/memory/b2d4f6a8-3c5e-4d7f-9a21-2b3c4d5e6f02").json()["context"]


def test_diagnose_validates_input():
    assert client.post("/diagnose", json={"patient_id": "x"}).status_code == 422


def test_sql_error_is_400():
    assert client.post("/sql", json={"query": "SELECT * FROM nope"}).status_code == 400
