"""
Agent, power layer and data layer tests. No network: Nightshift and Zetaris are mocked
at the HTTP level so the exact requests we send are checked.

    pytest tests/ -v
"""

import json
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import engine_h_mem, llm, tools_zetaris  # noqa: E402
from agent.agent import critique_report, demo_cases, run_case  # noqa: E402
from agent.hmem import HMEM  # noqa: E402
from agent.triage import Evidence, Intake, triage  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_h_mem, "_engine", HMEM(db_path=str(tmp_path / "h.db"), actor="test"))
    monkeypatch.setenv("SANGODIAG_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr("agent.agent.LOG_DIR", str(tmp_path / "logs"))


class FakeResp:
    def __init__(self, status=200, body=None, headers=None, text=""):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.text = text or json.dumps(body)

    def json(self):
        return self._body


# --- Nightshift provider contract --------------------------------------------

@pytest.mark.parametrize("raw", [
    "127.0.0.1:8088", "http://127.0.0.1:8088", "http://127.0.0.1:8088/v1", "http://127.0.0.1:8088/v1/",
    "http://127.0.0.1:8088/v1/chat/completions", "http://127.0.0.1:8088/v1/models", "http://127.0.0.1:8088/healthz",
])
def test_base_url_normalised_without_double_v1(raw):
    assert llm.normalise_base_url(raw) == "http://127.0.0.1:8088/v1"


def _settings():
    return llm.Settings(base_url="http://127.0.0.1:8088/v1", token="tok-123",
                        fast_model="nvidia/nemotron-3.5-lightning-30b-a3b",
                        deep_model="nvidia/nemotron-3-super-120b-a12b")


def test_chat_sends_contract_headers_and_records_real_model(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResp(200, {"model": "nvidia/nemotron-3-super-120b-a12b",
                              "choices": [{"message": {"content": "<think>hmm</think>Final answer"},
                                           "finish_reason": "stop"}],
                              "usage": {"total_tokens": 321}},
                        headers={"meterless-lane": "deep", "Content-Type": "application/json"})

    monkeypatch.setattr(llm.requests, "post", fake_post)
    res = llm.chat([{"role": "user", "content": "hi"}], lane="deep", role="reporter", settings=_settings())
    h = seen["headers"]
    assert seen["url"] == "http://127.0.0.1:8088/v1/chat/completions"
    assert h["Authorization"] == "Bearer tok-123"
    assert h["meterless-app"] == "sangodiag" and h["meterless-scope"] == "user"
    assert int(h["meterless-ttfb-ms"]) > 45000
    assert seen["json"]["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert seen["timeout"] == 180
    assert res.content == "Final answer"                      # reasoning stripped
    assert res.record.live and res.record.model_reported == "nvidia/nemotron-3-super-120b-a12b"
    assert res.record.usage["total_tokens"] == 321
    assert res.record.runtime_headers == {"meterless-lane": "deep"}


def test_fast_lane_uses_fast_model(monkeypatch):
    seen = {}
    monkeypatch.setattr(llm.requests, "post", lambda url, headers=None, json=None, timeout=None: (
        seen.update(model=json["model"]) or FakeResp(200, {"choices": [{"message": {"content": "DONE"}}]})))
    res = llm.chat([{"role": "user", "content": "x"}], lane="fast", role="planner", settings=_settings())
    assert seen["model"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert res.record.model_reported == "not reported"        # never invented


def test_wrong_token_is_unauthorized_not_offline(monkeypatch):
    monkeypatch.setattr(llm.requests, "get", lambda *a, **k: FakeResp(401, {}))
    assert llm.provider_status(_settings())["state"] == "unauthorized"
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: FakeResp(403, {}))
    with pytest.raises(llm.NightshiftError, match="token"):
        llm.chat([{"role": "user", "content": "x"}], "fast", "planner", settings=_settings())


def test_status_online_lists_lanes(monkeypatch):
    monkeypatch.setattr(llm.requests, "get", lambda *a, **k: FakeResp(200, {"data": [
        {"id": "meterless/auto"}, {"id": "nvidia/nemotron-3.5-lightning-30b-a3b"}]}))
    st = llm.provider_status(_settings())
    assert st["state"] == "online"
    assert st["lanes"]["fast"]["listed"] and not st["lanes"]["deep"]["listed"]


def test_retry_once_on_5xx_then_fail_loudly(monkeypatch):
    calls = {"n": 0}

    def fake_post(*a, **k):
        calls["n"] += 1
        return FakeResp(502, {}, text="bad gateway")

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    with pytest.raises(llm.NightshiftError):
        llm.chat([{"role": "user", "content": "x"}], "fast", "planner", settings=_settings())
    assert calls["n"] == 2


def test_missing_token_refuses_to_call():
    s = _settings()
    s.token = ""
    with pytest.raises(llm.NightshiftError, match="METERLESS_RUNTIME_TOKEN"):
        llm.chat([{"role": "user", "content": "x"}], "fast", "planner", settings=s)


# --- Zetaris tool -------------------------------------------------------------

@pytest.mark.parametrize("sql", ["DELETE FROM patients", "SELECT 1; DROP TABLE patients", "UPDATE x SET a=1",
                                 "", "SELECT * FROM patients; SELECT 2"])
def test_run_sql_refuses_anything_but_one_select(sql):
    res = tools_zetaris.run_sql(sql, mode="local")
    assert not res.ok


def test_run_sql_live_request_shape(monkeypatch):
    monkeypatch.setenv("ZETARIS_API_KEY", "zk")
    monkeypatch.setenv("ZETARIS_ORG_ID", "1")
    seen = []

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.append((url, dict(headers), json))
        return FakeResp(200, {"headers": ["village", "endemic_zone"], "data": [["Buea", "High"]]})

    monkeypatch.setattr(tools_zetaris.requests, "post", fake_post)
    r1 = tools_zetaris.run_sql("SELECT village, endemic_zone FROM regional_epidemiology", mode="live")
    tools_zetaris.run_sql("SELECT 1 AS one", mode="live")
    url, h, body = seen[0]
    assert url.endswith("/sql-editor/sqls/run")
    assert h["Authorization"] == "Bearer zk" and h["X-Org-ID"] == "1"
    uuid.UUID(h["X-Request-ID"])
    assert seen[0][1]["X-Request-ID"] != seen[1][1]["X-Request-ID"]   # fresh UUID per request
    assert body["source"] == "SqlEditor" and body["sql"].startswith("SELECT") and "queryId" in body
    assert r1.source == "zetaris" and r1.rows == [{"village": "Buea", "endemic_zone": "High"}]


def test_live_failure_is_reported_not_replaced(monkeypatch):
    monkeypatch.setenv("ZETARIS_API_KEY", "zk")
    monkeypatch.setattr(tools_zetaris.requests, "post", lambda *a, **k: FakeResp(401, {}, text="nope"))
    res = tools_zetaris.run_sql("SELECT 1", mode="live")
    assert not res.ok and "401" in res.error and res.rows == []


# --- Rules and critic ---------------------------------------------------------

def test_no_treatment_without_positive_test():
    tr = triage(Intake(patient_id="x", temperature_c=39.5, symptoms=["fever", "chills"]),
                Evidence(village="Kumba", endemic_zone="High", active_cases=47))
    assert tr.action == "DO_RDT"


def test_danger_sign_always_refers_even_with_negative_test():
    tr = triage(Intake(patient_id="x", temperature_c=38, symptoms=["fever"], danger_signs=["convulsions"],
                       test_result="rdt_negative"), Evidence(village="Buea", endemic_zone="High"))
    assert tr.action == "REFER_URGENT" and tr.urgent


def test_image_model_alone_never_confirms():
    tr = triage(Intake(patient_id="x", temperature_c=38.5, symptoms=["fever"]),
                Evidence(village="Buea", endemic_zone="High",
                         vision={"available": True, "parasite_present": True, "confidence": 0.95}))
    assert tr.action == "DO_RDT"


def test_critic_catches_doses_bad_citations_and_test_before_treat():
    tr = triage(Intake(patient_id="x", temperature_c=39, symptoms=["fever"]), Evidence(endemic_zone="High"))
    bad = ("**Assessment**\nLikely malaria.\n\n**Why**\n- High zone [Q7]\n\n**What to do now**\n"
           "1. Give Coartem 4 tablets now.\n2. Do an RDT.")
    issues = " ".join(critique_report(bad, tr, ["Q1", "Q2"], danger=False))
    assert "Q7" in issues and "dose" in issues and "antimalarial" in issues


def test_critic_accepts_negated_antimalarial_advice():
    tr = triage(Intake(patient_id="x", temperature_c=37.8, symptoms=["fever", "cough"], test_result="rdt_negative"),
                Evidence(endemic_zone="Medium"))
    ok = ("**Assessment**\nMalaria unlikely; look for another cause.\n\n**Why**\n- Medium zone [Q1]\n\n"
          "**What to do now**\n1. Do not give antimalarials.\n2. Look for another cause.")
    assert critique_report(ok, tr, ["Q1"], danger=False) == []


# --- End to end ---------------------------------------------------------------

@pytest.mark.parametrize("name", ["clear_malaria", "ambiguous", "not_malaria", "danger_signs"])
def test_demo_cases_offline(name):
    case = demo_cases()[name]
    r = run_case(Intake(**case["intake"]), model_mode="offline", data_mode="local")
    assert r.error is None
    assert r.triage["action"] == case["expected_action"]
    assert r.report_source == "offline-simulator"
    assert all(not c["live"] and c["model_reported"] == "offline-simulator" for c in r.calls)
    assert {e.step for e in r.events} >= {"recall", "plan", "execute", "critic", "decide", "report", "remember"}


def test_hmem_changes_the_next_decision():
    cases = demo_cases()
    first = run_case(Intake(**cases["clear_malaria"]["intake"]), model_mode="offline", data_mode="local")
    assert first.triage["action"] == "TREAT_PER_PROTOCOL"
    follow = run_case(Intake(**cases["follow_up"]["intake"]), model_mode="offline", data_mode="local")
    assert follow.memory["count"] >= 2
    assert follow.triage["action"] == "SEND_LAB"           # possible treatment failure, from memory
    assert any(r["cite"].startswith("MEM") for r in follow.triage["reasons"])


def test_live_loop_with_mocked_nightshift_revises_bad_draft(monkeypatch):
    """Planner tool call -> Zetaris replica -> DONE; reporter's first draft has a dose, critic sends it back."""
    monkeypatch.setenv("METERLESS_RUNTIME_TOKEN", "tok")
    replies = {"fast": [], "deep": []}
    pid = "e5a7c9d1-6f8b-4a0c-8354-5e6f7a8b9c05"
    replies["fast"] = [
        {"model": "nvidia/nemotron-3.5-lightning-30b-a3b", "choices": [{"message": {"content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "run_sql", "arguments": json.dumps({
                "sql": "SELECT p.village, p.family_history_malaria, e.endemic_zone, e.active_cases_this_week FROM patients p "
                       f"JOIN regional_epidemiology e ON p.village = e.village WHERE p.patient_id = '{pid}'"})}},
            {"id": "c2", "type": "function", "function": {"name": "run_sql", "arguments": json.dumps({
                "sql": f"SELECT visit_id, fever_temp_c FROM clinical_visits WHERE patient_id = '{pid}'"})}}]}}]},
        {"model": "nvidia/nemotron-3.5-lightning-30b-a3b", "choices": [{"message": {"content": "DONE"}}]},
    ]
    replies["deep"] = [
        {"model": "nvidia/nemotron-3-super-120b-a12b", "choices": [{"message": {"content":
            "**Assessment**\nSuspected malaria.\n\n**Why**\n- Medium zone [Q1]\n\n**What to do now**\n"
            "1. Do an RDT.\n2. Paracetamol 500 mg."}}]},
        {"model": "nvidia/nemotron-3-super-120b-a12b", "choices": [{"message": {"content":
            "**Assessment**\nSuspected malaria in a Medium zone [Q1].\n\n**Why**\n- Fever [NURSE]\n\n"
            "**What to do now**\n1. Do an RDT now (test before treat).\n\n**Watch for**\n- Danger signs."}}]},
    ]

    def fake_post(url, headers=None, json=None, timeout=None):
        lane = "deep" if json["model"].endswith("120b-a12b") else "fast"
        return FakeResp(200, replies[lane].pop(0))

    monkeypatch.setattr(llm.requests, "post", fake_post)
    case = demo_cases()["ambiguous"]
    r = run_case(Intake(**case["intake"]), model_mode="live", data_mode="local")
    assert r.error is None, r.error
    assert [q["asked_by"] for q in r.queries] == ["planner", "planner"]
    assert r.triage["action"] == "DO_RDT"
    assert r.report_source == "nemotron" and "500 mg" not in r.report
    titles = [e.title for e in r.events]
    assert "Report rejected: sent back to the reporter" in titles and "Report approved" in titles
    lanes = {c["lane"]: c["model_reported"] for c in r.calls}
    assert lanes == {"fast": "nvidia/nemotron-3.5-lightning-30b-a3b", "deep": "nvidia/nemotron-3-super-120b-a12b"}


def test_planner_revision_when_evidence_missing(monkeypatch):
    """Planner forgets the endemic zone; the critic sends it back and it fixes it."""
    monkeypatch.setenv("METERLESS_RUNTIME_TOKEN", "tok")
    pid = "f6b8d0e2-7a9c-4b1d-9465-6f7a8b9c0d06"
    fast = [
        {"choices": [{"message": {"content": f"```sql\nSELECT patient_id, village, family_history_malaria FROM patients WHERE patient_id = '{pid}'\n```"}}]},
        {"choices": [{"message": {"content": "DONE"}}]},
        {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "c3", "type": "function", "function": {"name": "run_sql", "arguments": json.dumps({
                "sql": "SELECT village, endemic_zone, active_cases_this_week FROM regional_epidemiology WHERE village = 'Bafoussam'"})}},
            {"id": "c4", "type": "function", "function": {"name": "run_sql", "arguments": json.dumps({
                "sql": f"SELECT * FROM clinical_visits WHERE patient_id = '{pid}'"})}}]}}]},
        {"choices": [{"message": {"content": "DONE"}}]},
    ]
    good = ("**Assessment**\nMalaria unlikely; look for another cause [Q2].\n\n**Why**\n- RDT negative [NURSE]\n\n"
            "**What to do now**\n1. Do not give antimalarials; assess other causes.")

    def fake_post(url, headers=None, json=None, timeout=None):
        if json["model"].endswith("120b-a12b"):
            return FakeResp(200, {"choices": [{"message": {"content": good}}]})
        return FakeResp(200, fast.pop(0))

    monkeypatch.setattr(llm.requests, "post", fake_post)
    r = run_case(Intake(**demo_cases()["not_malaria"]["intake"]), model_mode="live", data_mode="local")
    assert r.error is None, r.error
    assert any(e.title.startswith("Evidence incomplete") for e in r.events)
    assert all(q["asked_by"] == "planner" for q in r.queries)        # no baseline needed
    assert r.triage["action"] == "OTHER_CAUSE"


def test_nightshift_down_stops_the_run_visibly(monkeypatch):
    monkeypatch.setenv("METERLESS_RUNTIME_TOKEN", "tok")

    def boom(*a, **k):
        raise llm.requests.ConnectionError("refused")

    monkeypatch.setattr(llm.requests, "post", boom)
    r = run_case(Intake(**demo_cases()["ambiguous"]["intake"]), model_mode="live", data_mode="local")
    assert r.error and "Nightshift unreachable" in r.error
    assert r.report == "" and r.triage is None
