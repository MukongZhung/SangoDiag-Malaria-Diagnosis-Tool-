"""
H-MEM conformance suite, ported to pytest.

The vectors in tests/conformance/hmem_vectors.json are copied unchanged from the
official Meterless repository (engines/hmem/conformance/vectors/vectors.json,
commit 1742dec, Apache-2.0). Each check below mirrors one block of the official
TypeScript runner (engines/hmem/conformance/runner.ts), so a green run here is
the same scorecard the Meterless suite asks for.

Run:  pytest tests/test_engine_conformance.py -v
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.hmem import HMEM  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "conformance", "hmem_vectors.json"), encoding="utf-8") as f:
    VECTORS = json.load(f)

T0 = VECTORS["clock"]
DAY = 24 * 60 * 60 * 1000
S = VECTORS["sections"]


def approx(a, b, eps=1e-9):
    return abs(a - b) < eps


def ids(section):
    return [c["id"] for c in S[section]]


@pytest.mark.parametrize("c", S["record-validation"], ids=ids("record-validation"))
def test_record_validation(c):
    hmem = HMEM(clock=lambda: T0)
    rejected = False
    try:
        hmem.add(content=c["input"]["content"], source=c["input"]["source"])
    except ValueError:
        rejected = True
    assert rejected == (c["expect"] == "reject"), c["description"]


@pytest.mark.parametrize("c", S["feedback-deltas"], ids=ids("feedback-deltas"))
def test_feedback_deltas(c):
    hmem = HMEM(clock=lambda: T0)
    m = hmem.add(content="feedback target record", confidence=c["start"], source="conformance")
    before = m.accessCount
    hmem.feedback(m.id, c["kind"])
    after = hmem.store.get(m.id)
    assert approx(after.confidence, c["expectConfidence"]), (after.confidence, c)
    if "expectAccessDelta" in c:
        assert after.accessCount - before == c["expectAccessDelta"]
    if "expectTag" in c:
        assert c["expectTag"] in after.tags


@pytest.mark.parametrize("c", S["ranking-order"], ids=ids("ranking-order"))
def test_ranking_order(c):
    hmem = HMEM(clock=lambda: T0)
    by_key = {}
    for r in c["records"]:
        by_key[r["key"]] = hmem.add(content=r["content"], confidence=r["confidence"], layer=r["layer"],
                                    source="conformance")
    for r in c["records"]:
        if "supersededByKey" in r:
            by_key[r["key"]].supersededBy = by_key[r["supersededByKey"]].id
    result = hmem.query(c["query"], threshold=0, topN=10)
    order = [m.memory.id for m in result.memories]
    expected = [by_key[k].id for k in c["expectOrder"]]
    for a, b in zip(expected, expected[1:]):
        assert order.index(a) < order.index(b), (c["expectOrder"], order)


@pytest.mark.parametrize("c", S["sleep-guardrails"], ids=ids("sleep-guardrails"))
def test_sleep_guardrails(c):
    now = {"t": T0}
    hmem = HMEM(clock=lambda: now["t"])
    by_key = {}
    for r in c["records"]:
        by_key[r["key"]] = hmem.add(content=r["content"], source=r["source"], derivedFrom=r.get("derivedFrom"))
    now["t"] = T0 + c["ageDays"] * DAY
    before = sorted(m.id for m in hmem.store.all())
    preview = hmem.sleep.preview()
    assert sorted(m.id for m in hmem.store.all()) == before, "preview mutated the store"
    for k in c["expectArchived"]:
        assert by_key[k].id in preview["toArchive"], f"{k} should be archivable"
    for k in c["expectProtected"]:
        assert by_key[k].id not in preview["toArchive"], f"{k} is guardrail-protected"
    report = hmem.sleep.execute(preview)
    for k in c["expectProtected"]:
        assert hmem.store.get(by_key[k].id) is not None, f"{k} deleted despite guardrails"
    assert isinstance(report["backupId"], str) and report["backupId"]


@pytest.mark.parametrize("c", S["conflict-gate"], ids=ids("conflict-gate"))
def test_conflict_gate(c):
    hmem = HMEM(clock=lambda: T0)
    a = hmem.add(content=c["a"]["content"], confidence=c["a"]["confidence"], source="conformance")
    b = hmem.add(content=c["b"]["content"], confidence=c["b"]["confidence"], source="conformance")
    found = hmem.conflicts.scan()
    assert found, "opposing always/never pair on similar content must be detected"
    outcome = hmem.conflicts.auto_resolve(found[0])
    assert outcome in ("resolved", "queued")
    if outcome == "resolved":
        assert any(m.supersededBy for m in (hmem.store.get(a.id), hmem.store.get(b.id)))
    assert hmem.store.get(a.id) and hmem.store.get(b.id), "conflict resolution must never delete records"


@pytest.mark.parametrize("c", S["ledger-audit"], ids=ids("ledger-audit"))
def test_ledger_audit(c):
    hmem = HMEM(clock=lambda: T0)
    m = hmem.add(content="audited record", confidence=c["start"], source="conformance")
    hmem.feedback(m.id, c["kind"])
    history = hmem.ledger.history(m.id)
    assert [h["action"] for h in history] == c["expectActions"]
    fb = history[-1]
    assert approx(fb["previousState"]["confidence"], c["expectPrev"])
    assert approx(fb["newState"]["confidence"], c["expectNew"])


@pytest.mark.parametrize("c", S["dream-boundary"], ids=ids("dream-boundary"))
def test_dream_boundary(c):
    hmem = HMEM(clock=lambda: T0)
    for r in c["records"]:
        hmem.add(content=r["content"], type=r["type"], source="conformance")
    count_before = len(hmem.store.all())
    proposals = hmem.dreaming.dream()
    assert proposals, "two related preferences must produce at least one proposal"
    assert len(hmem.store.all()) == count_before, "dreaming must not materialize before approval"
    created = hmem.dreaming.approve(proposals[0].id)
    if created:
        assert created.layer == "long_term"
        assert created.derivedFrom


# --- Extra checks beyond the official vectors -------------------------------

def test_sqlite_persistence_survives_restart(tmp_path):
    db = str(tmp_path / "h.db")
    h1 = HMEM(clock=lambda: T0, db_path=db)
    m = h1.add(content="Patient p101 tested RDT positive, treated per protocol", source="nurse_intake",
               chatId="patient:p101")
    h1.feedback(m.id, "helpful")
    h2 = HMEM(clock=lambda: T0, db_path=db)
    again = h2.store.get(m.id)
    assert again is not None and approx(again.confidence, 0.75)
    assert [e["action"] for e in h2.ledger.history(m.id)] == ["create", "feedback"]


def test_ledger_is_append_only_on_disk(tmp_path):
    import sqlite3
    db = str(tmp_path / "h.db")
    h = HMEM(clock=lambda: T0, db_path=db)
    h.add(content="audited", source="t")
    with pytest.raises(sqlite3.DatabaseError):
        with sqlite3.connect(db) as c:
            c.execute("DELETE FROM hmem_ledger")


def test_scope_never_leaks_other_patients():
    h = HMEM(clock=lambda: T0)
    h.add(content="fever and positive RDT, malaria treated", source="t", chatId="patient:A")
    h.add(content="fever and positive RDT, malaria treated", source="t", chatId="patient:B")
    res = h.query("fever malaria RDT", scope="patient:A", threshold=0)
    assert res.memories and all(r.memory.chatId == "patient:A" for r in res.memories)
