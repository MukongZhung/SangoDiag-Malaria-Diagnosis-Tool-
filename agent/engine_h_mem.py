"""
Build layer: Meterless H-MEM wired into the clinical workflow.

The engine itself is agent/hmem/core.py (a Python port of the Meterless H-MEM
reference that passes the official conformance vectors). This module is the thin
clinical adapter the agent calls:

  recall(patient_id, presentation)   ->  what we already know about this patient,
                                         ranked by the canonical H-MEM formula and
                                         formatted as a [MEMORY CONTEXT] block that
                                         is injected into the planner and reporter prompts
  remember_encounter(...)            ->  writes today's visit as two records:
                                         the nurse's observations (high confidence) and
                                         the agent's recommendation (lower confidence)
  feedback(memory_id, kind)          ->  the nurse confirms or rejects an earlier
                                         recommendation; H-MEM adjusts its confidence
                                         (+0.05 helpful / -0.20 wrong) and audits it

Every memory is scoped to one patient (chat_id = "patient:<id>") and stored in a
local SQLite file (h_mem.db). Nothing leaves the device.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from agent.hmem import HMEM

DB_PATH = os.environ.get(
    "H_MEM_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "h_mem.db")
)

_engine: Optional[HMEM] = None


def engine(db_path: Optional[str] = None) -> HMEM:
    global _engine
    if db_path:
        return HMEM(db_path=db_path, actor="sangodiag")
    if _engine is None:
        _engine = HMEM(db_path=DB_PATH, actor="sangodiag")
    return _engine


def scope_for(patient_id: str) -> str:
    return f"patient:{patient_id}"


def _fmt_time(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")


def recall(patient_id: str, presentation: str, hmem: Optional[HMEM] = None) -> Dict[str, Any]:
    """Rank this patient's memories against today's presentation.

    threshold=0 on purpose: for a known patient every earlier visit is eligible,
    and the H-MEM score decides the order and the top 5. The default 0.35 gate is
    meant for open-ended recall across many topics, not for one patient's chart.
    """
    h = hmem or engine()
    res = h.query(presentation, scope=scope_for(patient_id), threshold=0, topN=5)
    items = [
        {
            "id": r.memory.id,
            "content": r.memory.content,
            "relevance": round(r.relevance, 3),
            "confidence": round(r.memory.confidence, 2),
            "layer": r.memory.layer,
            "source": r.memory.source,
            "origin": r.memory.provenance.get("origin"),
            "when": _fmt_time(r.memory.timestamp),
            "timestamp": r.memory.timestamp,
            "tags": list(r.memory.tags),
        }
        for r in res.memories
    ]
    return {"patient_id": patient_id, "count": len(items), "items": items, "context": res.context,
            "trace": res.trace}


def remember_encounter(patient_id: str, observation: str, recommendation: str, model: str, run_id: str,
                       action: str = "", hmem: Optional[HMEM] = None) -> List[str]:
    h = hmem or engine()
    sc = scope_for(patient_id)
    obs = h.add(
        content=observation, source="nurse_intake", type="factual", layer="working", confidence=0.9,
        tags=["clinical", "event:chat_message", f"run:{run_id}"], chatId=sc, missionId=run_id,
        provenance={"origin": "chat_message", "learnedAt": h.clock(), "label": "observed by the nurse"},
    )
    rec = h.add(
        content=recommendation, source=f"agent:{model}", type="factual", layer="working", confidence=0.6,
        tags=["clinical", "event:model_response", "agent-recommendation", f"run:{run_id}"]
        + ([f"rec:{action}"] if action else []), chatId=sc,
        missionId=run_id, provenance={"origin": "model_response", "learnedAt": h.clock(),
                                      "label": "SangoDiag recommendation", "refs": [obs.id]},
    )
    return [obs.id, rec.id]


def feedback(memory_id: str, kind: str, hmem: Optional[HMEM] = None) -> Dict[str, Any]:
    h = hmem or engine()
    h.feedback(memory_id, kind)
    m = h.store.get(memory_id)
    return {"id": memory_id, "confidence": round(m.confidence, 2), "tags": m.tags}


def patient_ledger(patient_id: str, hmem: Optional[HMEM] = None, limit: int = 30) -> List[Dict[str, Any]]:
    h = hmem or engine()
    ids = {m.id for m in h.store.all() if m.chatId == scope_for(patient_id)}
    out = [e for e in h.ledger.all() if e["memoryId"] in ids]
    return [{"memory": e["memoryId"], "action": e["action"], "when": _fmt_time(e["timestamp"]),
             "details": e.get("details", {})} for e in out[-limit:]]


def stats(hmem: Optional[HMEM] = None) -> Dict[str, Any]:
    h = hmem or engine()
    patients = {m.chatId for m in h.store.all() if m.chatId}
    return {"records": len(h.store.all()), "patients": len(patients), "ledger": h.ledger.stats()}


# Back-compat helpers used by older scripts.
def save_patient_context(patient_id: str, context_string: str) -> None:
    h = engine()
    h.add(content=context_string, source="legacy", chatId=scope_for(patient_id), tags=["clinical"])


def get_patient_context(patient_id: str) -> Optional[str]:
    r = recall(patient_id, "patient history")
    return r["context"] or None
