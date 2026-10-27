"""
H-MEM engine, Python port of the Meterless reference implementation.

Source spec:  https://github.com/Meterless/Meterless/tree/main/engines/hmem
              (AGENTS.md + reference/src/*.ts, commit 1742dec, Apache-2.0)

This module follows the reference service by service so it can be checked
against the official conformance vectors (tests/conformance/hmem_vectors.json,
run by tests/test_engine_conformance.py):

  MemoryStoreService        tiered records, enrichment, source required
  TrustLedgerService        append-only audit log (17 canonical actions)
  MemoryRetrievalService    canonical hybrid ranking + reinjection + feedback
  ConflictDetectionService  opposing-claim scan, gated auto-resolve
  SleepCycleService         preview-first consolidate / archive / synthesize
  DreamingService           proposals that only become memory after approval

Differences from the TypeScript reference, all on purpose:
  * persistence is a local SQLite file instead of state.json + ledger.jsonl,
    so patient memory never leaves the device (local-first);
  * query() takes an optional `scope` that only returns records whose chat_id
    matches exactly. SangoDiag scopes every clinical memory to one patient, and
    one patient's notes must never surface for another.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# Types and defaults (reference: types.ts)
# ---------------------------------------------------------------------------

DAY_MS = 24 * 60 * 60 * 1000

FEEDBACK_DELTAS = {"helpful": 0.05, "not_helpful": -0.03, "wrong": -0.2}

DEFAULTS = {
    "retrievalTopN": 5,
    "retrievalThreshold": 0.35,  # on the final score, after the confidence multiplier
    "consolidationDays": 7,
    "archiveMinDays": 30,
    "archiveMaxAccess": 2,
    "synthesisCosine": 0.82,
    "dreamClusterMinSize": 2,
    "dreamRelatedness": 0.35,
    "maxDreamProposalsPerType": 8,
    "conflictAutoResolveGate": 0.7,
    "entityCap": 10,
    "relatedCap": 5,
    "recencyDays": 14,
}

LEDGER_ACTIONS = {
    "create", "read", "update", "delete", "feedback", "promote", "demote", "merge",
    "conflict_detected", "conflict_resolved",
    "sleep_consolidate", "sleep_archive", "sleep_synthesize",
    "dream_proposed", "dream_approved", "dream_rejected", "restore",
}

LAYER_WEIGHT = {"long_term": 1.0, "working": 0.8, "short_term": 0.6}


def clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


@dataclass
class MemoryRecord:
    id: str
    content: str
    type: str
    layer: str
    timestamp: int
    lastAccessed: int
    accessCount: int
    tags: List[str]
    embedding: List[float]
    confidence: float
    source: str
    provenance: Dict[str, Any]
    domain: str
    namespace: str
    entities: List[str]
    relatedTo: List[str]
    chatId: Optional[str] = None
    missionId: Optional[str] = None
    goalRunId: Optional[str] = None
    supersedes: Optional[str] = None
    supersededBy: Optional[str] = None
    derivedFrom: Optional[List[str]] = None
    score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def snapshot(r: MemoryRecord) -> Dict[str, Any]:
    d = copy.deepcopy(r.to_dict())
    d.pop("embedding", None)
    return d


# ---------------------------------------------------------------------------
# Deterministic mock embedder (reference: embeddings.ts)
# FNV-1a per token into a 64-dim vector, summed and L2-normalised.
# ---------------------------------------------------------------------------

DIM = 64
_NON_ALNUM = re.compile(r"[^a-z0-9\s]")


def tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"\s+", _NON_ALNUM.sub(" ", text.lower())) if len(t) > 1]


def _fnv1a(s: str) -> int:
    h = 0x811C9DC5
    for ch in s:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def embed(text: str) -> List[float]:
    vec = [0.0] * DIM
    for token in tokenize(text):
        h = _fnv1a(token)
        idx = h % DIM
        sign = 1 if (h >> 8) % 2 == 0 else -1
        mag = 1 + ((h >> 16) % 8) / 8
        vec[idx] += sign * mag
    norm = math.sqrt(sum(v * v for v in vec))
    return vec if norm == 0 else [v / norm for v in vec]


def cosine(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # both unit length


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return inter / (len(sa) + len(sb) - inter)


# ---------------------------------------------------------------------------
# Local SQLite persistence (replaces state.json / ledger.jsonl)
# ---------------------------------------------------------------------------

class _SqlitePersistence:
    def __init__(self, path: str):
        self.path = path
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS hmem_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS hmem_records (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
            c.execute(
                "CREATE TABLE IF NOT EXISTS hmem_ledger ("
                " seq INTEGER PRIMARY KEY AUTOINCREMENT, memory_id TEXT NOT NULL, action TEXT NOT NULL,"
                " actor TEXT NOT NULL, ts INTEGER NOT NULL, body TEXT NOT NULL)"
            )
            # Append-only by construction: the ledger rejects updates and deletes.
            c.execute(
                "CREATE TRIGGER IF NOT EXISTS hmem_ledger_no_update BEFORE UPDATE ON hmem_ledger "
                "BEGIN SELECT RAISE(ABORT, 'H-MEM ledger is append-only'); END"
            )
            c.execute(
                "CREATE TRIGGER IF NOT EXISTS hmem_ledger_no_delete BEFORE DELETE ON hmem_ledger "
                "BEGIN SELECT RAISE(ABORT, 'H-MEM ledger is append-only'); END"
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def load_records(self) -> tuple[int, List[MemoryRecord]]:
        with self._conn() as c:
            row = c.execute("SELECT value FROM hmem_meta WHERE key='seq'").fetchone()
            seq = int(row[0]) if row else 0
            rows = c.execute("SELECT body FROM hmem_records").fetchall()
        recs = [MemoryRecord(**json.loads(b)) for (b,) in rows]
        recs.sort(key=lambda r: int(r.id.split("-")[1]) if r.id.split("-")[-1].isdigit() else 0)
        return seq, recs

    def save_records(self, seq: int, records: Iterable[MemoryRecord]) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO hmem_meta (key, value) VALUES ('seq', ?)", (str(seq),))
            c.execute("DELETE FROM hmem_records")
            c.executemany(
                "INSERT INTO hmem_records (id, body) VALUES (?, ?)",
                [(r.id, json.dumps(r.to_dict())) for r in records],
            )

    def append_ledger(self, entry: Dict[str, Any]) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO hmem_ledger (memory_id, action, actor, ts, body) VALUES (?, ?, ?, ?, ?)",
                (entry["memoryId"], entry["action"], entry["actor"], entry["timestamp"], json.dumps(entry)),
            )

    def load_ledger(self) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT body FROM hmem_ledger ORDER BY seq").fetchall()
        return [json.loads(b) for (b,) in rows]


# ---------------------------------------------------------------------------
# Trust ledger (reference: trustLedger.ts)
# ---------------------------------------------------------------------------

class TrustLedgerService:
    def __init__(self, clock: Callable[[], int], db: Optional[_SqlitePersistence] = None):
        self._clock = clock
        self._db = db
        self._entries: List[Dict[str, Any]] = db.load_ledger() if db else []

    def log(self, memory_id: str, action: str, actor: str, previousState=None, newState=None, details=None) -> Dict[str, Any]:
        if action not in LEDGER_ACTIONS:
            raise ValueError(f"H-MEM: unknown ledger action {action}")
        entry: Dict[str, Any] = {"memoryId": memory_id, "action": action, "actor": actor, "timestamp": self._clock()}
        if previousState is not None:
            entry["previousState"] = previousState
        if newState is not None:
            entry["newState"] = newState
        if details is not None:
            entry["details"] = details
        self._entries.append(entry)
        if self._db:
            self._db.append_ledger(entry)
        return entry

    def history(self, memory_id: str) -> List[Dict[str, Any]]:
        return [e for e in self._entries if e["memoryId"] == memory_id]

    def all(self) -> List[Dict[str, Any]]:
        return list(self._entries)

    def stats(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in self._entries:
            out[e["action"]] = out.get(e["action"], 0) + 1
        return out


# ---------------------------------------------------------------------------
# Memory store with enrichment (reference: memoryStore.ts)
# ---------------------------------------------------------------------------

TECH_TERMS = [
    "react", "python", "typescript", "javascript", "rust", "sqlite", "postgres", "indexeddb",
    "node", "docker", "graphql", "redis", "webrtc", "tauri", "electron", "llm", "embedding",
]
# Clinical vocabulary added for SangoDiag so domain and entity enrichment mean
# something on health-post notes. The generic domains are kept as in the reference.
CLINICAL_TERMS = [
    "malaria", "fever", "rdt", "smear", "microscopy", "falciparum", "vivax", "act", "artemether",
    "lumefantrine", "artesunate", "paracetamol", "dengue", "typhoid", "referral", "referred",
    "vomiting", "convulsions", "anaemia", "jaundice", "prostration", "headache", "chills",
]
DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "tech": ["code", "bug", "api", "database", "deploy", "framework", "library", "server", *TECH_TERMS],
    "work": ["meeting", "deadline", "client", "project", "sprint", "review", "report"],
    "personal": ["family", "hobby", "prefer", "like", "dislike", "morning", "evening"],
    "clinical": ["patient", "visit", "symptoms", "diagnosis", "treatment", "test", "positive", "negative", *CLINICAL_TERMS],
}
_STOP_ENTITIES = {"the", "this", "that", "with"}
_CORRECTION = re.compile(r"\b(actually|instead|no longer|not anymore|changed to|correction)\b", re.I)


class MemoryStoreService:
    def __init__(self, clock: Callable[[], int], ledger: TrustLedgerService, actor: str, db: Optional[_SqlitePersistence] = None):
        self._clock = clock
        self._ledger = ledger
        self._actor = actor
        self._db = db
        self._records: Dict[str, MemoryRecord] = {}
        self._seq = 0
        if db:
            self._seq, recs = db.load_records()
            for r in recs:
                self._records[r.id] = r

    def persist(self) -> None:
        if self._db:
            self._db.save_records(self._seq, sorted(self._records.values(), key=lambda r: r.id))

    def add(self, content: str, source: str, type: str = "general", layer: str = "working", tags=None,
            confidence: Optional[float] = None, provenance=None, chatId=None, missionId=None, goalRunId=None,
            supersedes=None, derivedFrom=None) -> MemoryRecord:
        if not source or not str(source).strip():
            raise ValueError("H-MEM: a memory record with no source must be rejected by construction (AGENTS.md section 2)")
        now = self._clock()
        self._seq += 1
        rid = f"mem-{self._seq}"
        tags = list(tags or [])
        domain = self.classify_domain(content, tags, type)
        rec = MemoryRecord(
            id=rid, content=content, type=type, layer=layer, timestamp=now, lastAccessed=now, accessCount=0,
            tags=tags, embedding=embed(content), confidence=clamp01(0.7 if confidence is None else confidence),
            source=source, provenance=provenance or {"origin": "manual", "learnedAt": now, "label": source},
            domain=domain, namespace=self._namespace(domain, type), entities=self.extract_entities(content),
            relatedTo=[], chatId=chatId, missionId=missionId, goalRunId=goalRunId, supersedes=supersedes,
            derivedFrom=list(derivedFrom) if derivedFrom else None,
        )
        self._discover_relationships(rec)
        self._records[rid] = rec
        self._ledger.log(rid, "create", self._actor, newState=snapshot(rec))
        self.persist()
        return rec

    def get(self, rid: str) -> Optional[MemoryRecord]:
        return self._records.get(rid)

    def all(self) -> List[MemoryRecord]:
        return list(self._records.values())

    def update(self, rid: str, **patch) -> MemoryRecord:
        rec = self._must_get(rid)
        prev = snapshot(rec)
        for k, v in patch.items():
            setattr(rec, k, v)
        self._ledger.log(rid, "update", self._actor, previousState=prev, newState=snapshot(rec))
        self.persist()
        return rec

    def delete(self, rid: str, reason: str) -> None:
        rec = self._must_get(rid)
        del self._records[rid]
        self._ledger.log(rid, "delete", self._actor, previousState=snapshot(rec), details={"reason": reason})
        self.persist()

    def touch(self, rid: str) -> None:
        rec = self._must_get(rid)
        rec.lastAccessed = self._clock()
        rec.accessCount += 1

    def promote(self, rid: str, layer: str) -> None:
        rec = self._must_get(rid)
        prev = snapshot(rec)
        rec.layer = layer
        self._ledger.log(rid, "promote", self._actor, previousState=prev, newState=snapshot(rec))
        self.persist()

    def snapshot_all(self) -> Dict[str, Any]:
        return {"records": copy.deepcopy(list(self._records.values())), "seq": self._seq}

    def restore_all(self, records: List[MemoryRecord], seq: int) -> None:
        self._records = {r.id: copy.deepcopy(r) for r in records}
        self._seq = seq
        self.persist()

    def _must_get(self, rid: str) -> MemoryRecord:
        rec = self._records.get(rid)
        if rec is None:
            raise KeyError(f"H-MEM: unknown memory id {rid}")
        return rec

    # Multi-pass domain classification (AGENTS.md section 5)
    def classify_domain(self, content: str, tags: List[str], type: str) -> str:
        for t in tags:
            if t.startswith("project:"):
                return t[len("project:"):]
            if t.startswith("tech:"):
                return "tech"
        tokens = set(tokenize(content))
        best, best_score = "general", 0
        for domain, kws in DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in kws if kw in tokens)
            if domain == "personal" and type in ("personal", "preference"):
                score += 1
            if score > best_score:
                best, best_score = domain, score
        return best if best_score > 0 else "general"

    @staticmethod
    def _namespace(domain: str, type: str) -> str:
        bucket = "profile" if type in ("preference", "personal") else "facts" if type == "factual" else "notes"
        return f"{domain}/{bucket}"

    def extract_entities(self, content: str) -> List[str]:
        ents: List[str] = []
        for t in tokenize(content):
            if (t in TECH_TERMS or t in CLINICAL_TERMS) and t not in ents:
                ents.append(t)
        for m in re.finditer(r"\b([A-Z][a-zA-Z]{2,})\b", content):
            norm = m.group(1).lower()
            if norm not in _STOP_ENTITIES and norm not in ents:
                ents.append(norm)
        return ents[: DEFAULTS["entityCap"]]

    def _discover_relationships(self, rec: MemoryRecord) -> None:
        for other in self._records.values():
            if len(rec.relatedTo) >= DEFAULTS["relatedCap"]:
                break
            shared = [e for e in other.entities if e in rec.entities]
            sim = cosine(rec.embedding, other.embedding)
            if not rec.supersedes and sim > 0.85 and _CORRECTION.search(rec.content):
                rec.supersedes = other.id
                continue
            if shared and other.domain == rec.domain:
                rec.relatedTo.append(other.id)
                if len(other.relatedTo) < DEFAULTS["relatedCap"] and rec.id not in other.relatedTo:
                    other.relatedTo.append(rec.id)  # bidirectional link


# ---------------------------------------------------------------------------
# Retrieval, reinjection and feedback (reference: memoryRetrieval.ts)
#   raw = 0.35*semantic + 0.20*keyword + 0.10*tag + 0.10*domain
#       + 0.15*entity   + 0.05*layer   + 0.05*recency - 0.20*superseded
#   score = clamp01(raw) * confidence
# ---------------------------------------------------------------------------

@dataclass
class RetrievedMemory:
    memory: MemoryRecord
    relevance: float


@dataclass
class QueryResult:
    memories: List[RetrievedMemory]
    context: str
    trace: Dict[str, Any] = field(default_factory=dict)


class MemoryRetrievalService:
    def __init__(self, store: MemoryStoreService, ledger: TrustLedgerService, clock: Callable[[], int], actor: str):
        self._store, self._ledger, self._clock, self._actor = store, ledger, clock, actor

    def _score(self, m: MemoryRecord, q_emb, q_tokens, q_entities, q_domain) -> float:
        semantic = clamp01(cosine(q_emb, m.embedding))
        keyword = jaccard(q_tokens, tokenize(m.content))
        tag = jaccard(q_tokens, [t.lower() for t in m.tags])
        domain = 1.0 if m.domain == q_domain else 0.0
        entity = jaccard(q_entities, m.entities)
        layer = LAYER_WEIGHT[m.layer]
        age_days = (self._clock() - m.lastAccessed) / DAY_MS
        recency = math.exp(-age_days / DEFAULTS["recencyDays"])
        superseded = 1.0 if m.supersededBy else 0.0
        raw = (0.35 * semantic + 0.2 * keyword + 0.1 * tag + 0.1 * domain
               + 0.15 * entity + 0.05 * layer + 0.05 * recency - 0.2 * superseded)
        return clamp01(raw) * m.confidence

    def query(self, query: str, topN: Optional[int] = None, threshold: Optional[float] = None,
              chatId: Optional[str] = None, scope: Optional[str] = None) -> QueryResult:
        q_emb = embed(query)
        q_tokens = tokenize(query)[:8]
        q_entities = self._store.extract_entities(query)
        q_domain = self._store.classify_domain(query, [], "general")
        threshold = DEFAULTS["retrievalThreshold"] if threshold is None else threshold
        topN = DEFAULTS["retrievalTopN"] if topN is None else topN

        scored: List[RetrievedMemory] = []
        for m in self._store.all():
            if scope is not None and m.chatId != scope:
                continue  # strict scope: never leak another patient's memory
            if chatId and m.chatId and m.chatId != chatId:
                continue
            s = self._score(m, q_emb, q_tokens, q_entities, q_domain)
            if s >= threshold:
                scored.append(RetrievedMemory(m, s))
        scored.sort(key=lambda r: (-r.relevance, r.memory.id))
        top = scored[:topN]

        for r in top:
            self._store.touch(r.memory.id)
            self._ledger.log(r.memory.id, "read", self._actor, details={"query": query})
        if top:
            self._store.persist()

        if len(top) <= 1:
            strategy = "minimal"
        elif any(r.memory.type in ("personal", "preference") for r in top):
            strategy = "personal"
        else:
            strategy = "comprehensive"
        return QueryResult(
            memories=top,
            context=self.format_reinjection(top),
            trace={
                "retrievalReason": f'hybrid ranking for "{query}" (domain: {q_domain})',
                "strategy": strategy,
                "scores": {r.memory.id: round(r.relevance, 4) for r in top},
            },
        )

    @staticmethod
    def format_reinjection(items: List[RetrievedMemory]) -> str:
        if not items:
            return ""
        by_domain: Dict[str, List[RetrievedMemory]] = {}
        for it in items:
            by_domain.setdefault(it.memory.domain, []).append(it)
        lines = ["[MEMORY CONTEXT]"]
        for domain in sorted(by_domain):
            lines.append(f"## {domain}")
            for it in by_domain[domain]:
                m = it.memory
                marker = "LT" if m.layer == "long_term" else "WK" if m.layer == "working" else "ST"
                ents = f" (entities: {', '.join(m.entities)})" if m.entities else ""
                lines.append(f"- [{marker}] {m.content}{ents} <{m.id}>")
        lines.append("[/MEMORY CONTEXT]")
        return "\n".join(lines)

    def feedback(self, memory_id: str, kind: str) -> None:
        if kind not in FEEDBACK_DELTAS:
            raise ValueError(f"H-MEM: unknown feedback kind {kind}")
        m = self._store.get(memory_id)
        if m is None:
            raise KeyError(f"H-MEM: unknown memory id {memory_id}")
        prev = snapshot(m)
        if kind == "helpful":
            m.accessCount += 1
        m.confidence = clamp01(m.confidence + FEEDBACK_DELTAS[kind])
        if kind == "wrong" and "review" not in m.tags:
            m.tags.append("review")
        self._ledger.log(memory_id, "feedback", self._actor, previousState=prev, newState=snapshot(m),
                         details={"kind": kind, "delta": FEEDBACK_DELTAS[kind]})
        self._store.persist()


# ---------------------------------------------------------------------------
# Conflict detection and resolution (reference: conflictDetection.ts)
# ---------------------------------------------------------------------------

_OPPOSING_PAIRS = [
    (re.compile(r"\balways\b", re.I), re.compile(r"\bnever\b", re.I)),
    (re.compile(r"\benable[ds]?\b", re.I), re.compile(r"\bdisable[ds]?\b", re.I)),
    (re.compile(r"\bprefer[s]?\b", re.I), re.compile(r"\bavoid[s]?|dislike[s]?\b", re.I)),
    (re.compile(r"\bon\b", re.I), re.compile(r"\boff\b", re.I)),
    (re.compile(r"\byes\b", re.I), re.compile(r"\bno\b", re.I)),
    # clinical opposites
    (re.compile(r"\bpositive\b", re.I), re.compile(r"\bnegative\b", re.I)),
]


@dataclass
class ConflictRecord:
    id: str
    memoryA: str
    memoryB: str
    reason: str
    confidence: float
    resolved: bool = False
    resolution: Optional[str] = None


class ConflictDetectionService:
    def __init__(self, store: MemoryStoreService, ledger: TrustLedgerService, clock: Callable[[], int], actor: str):
        self._store, self._ledger, self._clock, self._actor = store, ledger, clock, actor
        self._conflicts: List[ConflictRecord] = []
        self._seq = 0

    def scan(self, scope: Optional[str] = None) -> List[ConflictRecord]:
        found: List[ConflictRecord] = []
        records = [m for m in self._store.all() if scope is None or m.chatId == scope]
        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                c = self._check(records[i], records[j])
                if c:
                    found.append(c)
                    self._conflicts.append(c)
                    self._ledger.log(c.memoryA, "conflict_detected", self._actor,
                                     details={"with": c.memoryB, "reason": c.reason, "confidence": c.confidence})
        return found

    def _check(self, a: MemoryRecord, b: MemoryRecord) -> Optional[ConflictRecord]:
        if a.supersedes == b.id or b.supersedes == a.id or a.supersededBy == b.id or b.supersededBy == a.id:
            return None
        sim = cosine(a.embedding, b.embedding)
        reason, confidence = "", 0.0
        for p, q in _OPPOSING_PAIRS:
            if (p.search(a.content) and q.search(b.content)) or (q.search(a.content) and p.search(b.content)):
                if sim > 0.5:
                    reason = "opposing phrase pair on similar content"
                    confidence = 0.5 + 0.3 * sim
        if not reason and sim > 0.8:
            nums_a = re.findall(r"\d+(?:\.\d+)?", a.content)
            nums_b = re.findall(r"\d+(?:\.\d+)?", b.content)
            if nums_a and nums_b and nums_a != nums_b:
                reason = "high-similarity conflicting numeric values"
                confidence = 0.55 + 0.25 * sim
        if not reason:
            return None
        if any(e in b.entities for e in a.entities):
            confidence += 0.1
        if a.domain == b.domain:
            confidence += 0.05
        if b.id in a.relatedTo:
            confidence -= 0.1
        self._seq += 1
        return ConflictRecord(id=f"conflict-{self._seq}", memoryA=a.id, memoryB=b.id, reason=reason,
                              confidence=clamp01(confidence))

    def auto_resolve(self, conflict: ConflictRecord) -> str:
        a = self._store.get(conflict.memoryA)
        b = self._store.get(conflict.memoryB)
        now = max(1, self._clock())

        def score_of(m: MemoryRecord) -> float:
            return (0.3 * (m.lastAccessed / now) + 0.2 * min(1.0, m.accessCount / 10) + 0.25 * m.confidence
                    + 0.1 * min(1.0, len(m.content) / 200)
                    + 0.15 * (1.0 if m.provenance.get("origin") == "user_correction" else 0.5))

        sa, sb = score_of(a), score_of(b)
        margin = abs(sa - sb) / max(sa, sb)
        decision_conf = clamp01(conflict.confidence * 0.6 + margin * 0.8)
        if decision_conf < DEFAULTS["conflictAutoResolveGate"]:
            return "queued"
        winner, loser = (a, b) if sa >= sb else (b, a)
        prev = snapshot(loser)
        loser.supersededBy = winner.id  # kept and penalised, never deleted
        conflict.resolved = True
        conflict.resolution = "keep_a" if winner.id == conflict.memoryA else "keep_b"
        self._ledger.log(loser.id, "conflict_resolved", self._actor, previousState=prev, newState=snapshot(loser),
                         details={"conflictId": conflict.id, "winner": winner.id,
                                  "decisionConfidence": round(decision_conf, 3)})
        self._store.persist()
        return "resolved"

    def queue(self) -> List[ConflictRecord]:
        return [c for c in self._conflicts if not c.resolved]


# ---------------------------------------------------------------------------
# Sleep cycle (reference: sleepCycle.ts)
# ---------------------------------------------------------------------------

HUB_THRESHOLD = 3


class SleepCycleService:
    def __init__(self, store: MemoryStoreService, ledger: TrustLedgerService, clock: Callable[[], int], actor: str):
        self._store, self._ledger, self._clock, self._actor = store, ledger, clock, actor
        self._backups: Dict[str, Dict[str, Any]] = {}
        self._backup_seq = 0

    def preview(self) -> Dict[str, Any]:
        now = self._clock()
        recs = self._store.all()
        referenced = set()
        for m in recs:
            referenced.update(m.relatedTo)
            if m.supersedes:
                referenced.add(m.supersedes)
            referenced.update(m.derivedFrom or [])

        to_consolidate = [m.id for m in recs
                          if m.layer == "short_term" and now - m.lastAccessed >= DEFAULTS["consolidationDays"] * DAY_MS]

        to_archive = []
        for m in recs:
            old_enough = now - m.timestamp >= DEFAULTS["archiveMinDays"] * DAY_MS
            low_access = m.accessCount <= DEFAULTS["archiveMaxAccess"]
            unreferenced = m.id not in referenced
            if not (old_enough and low_access and unreferenced):
                continue
            if m.supersedes or (m.derivedFrom or []) or len(m.relatedTo) >= HUB_THRESHOLD:
                continue  # guardrails (AGENTS.md section 8.2)
            to_archive.append(m.id)

        to_synthesize: List[List[str]] = []
        used = set()
        for i in range(len(recs)):
            if recs[i].id in used:
                continue
            group = [recs[i]]
            for j in range(i + 1, len(recs)):
                if recs[j].id in used:
                    continue
                if cosine(recs[i].embedding, recs[j].embedding) >= DEFAULTS["synthesisCosine"]:
                    group.append(recs[j])
            if len(group) >= 2:
                used.update(g.id for g in group)
                to_synthesize.append([g.id for g in group])
        return {"toConsolidate": to_consolidate, "toArchive": to_archive, "toSynthesize": to_synthesize}

    def execute(self, preview: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        plan = preview or self.preview()
        self._backup_seq += 1
        backup_id = f"backup-{self._backup_seq}"
        self._backups[backup_id] = self._store.snapshot_all()
        log = [f"backup {backup_id} created"]

        for rid in plan["toConsolidate"]:
            if not self._store.get(rid):
                continue
            self._store.promote(rid, "long_term")
            self._ledger.log(rid, "sleep_consolidate", self._actor, details={"from": "short_term", "to": "long_term"})
            log.append(f"consolidated {rid}")

        for rid in plan["toArchive"]:
            m = self._store.get(rid)
            if not m:
                continue
            self._ledger.log(rid, "sleep_archive", self._actor,
                             details={"age": self._clock() - m.timestamp, "accessCount": m.accessCount})
            self._store.delete(rid, "sleep archive")
            log.append(f"archived {rid}")

        synthesized = 0
        for group in plan["toSynthesize"]:
            members = [self._store.get(i) for i in group if self._store.get(i)]
            if len(members) < 2:
                continue
            tags: List[str] = []
            for m in members:
                for t in m.tags:
                    if t not in tags:
                        tags.append(t)
            merged = self._store.add(
                content="Synthesis: " + " | ".join(m.content for m in members),
                type="factual", layer="long_term", tags=tags,
                confidence=max(m.confidence for m in members), source="sleep:synthesis",
                provenance={"origin": "sleep_synthesis", "learnedAt": self._clock(),
                            "label": f"synthesized from {len(members)} memories"},
                derivedFrom=[m.id for m in members], chatId=members[0].chatId,
            )
            self._ledger.log(merged.id, "sleep_synthesize", self._actor, details={"sources": group})
            for m in members:
                self._store.delete(m.id, "merged by sleep synthesis")
            synthesized += 1
            log.append(f"synthesized {merged.id} from {', '.join(group)}")

        self._store.persist()
        return {"backupId": backup_id, "consolidated": len(plan["toConsolidate"]),
                "archived": len(plan["toArchive"]), "synthesized": synthesized, "actionLog": log}

    def restore(self, backup_id: str) -> None:
        b = self._backups.get(backup_id)
        if not b:
            raise KeyError(f"H-MEM: unknown backup {backup_id}")
        self._store.restore_all(b["records"], b["seq"])
        self._ledger.log("*", "restore", self._actor, details={"backupId": backup_id})


# ---------------------------------------------------------------------------
# Dreaming (reference: dreaming.ts) - never materialises before approval
# ---------------------------------------------------------------------------

@dataclass
class DreamProposal:
    id: str
    type: str
    content: str
    derivedFrom: List[str]
    suggestedDomain: Optional[str] = None
    status: str = "proposed"


class DreamingService:
    def __init__(self, store: MemoryStoreService, ledger: TrustLedgerService, clock: Callable[[], int], actor: str):
        self._store, self._ledger, self._clock, self._actor = store, ledger, clock, actor
        self._proposals: Dict[str, DreamProposal] = {}
        self._seq = 0

    @staticmethod
    def _relatedness(a: MemoryRecord, b: MemoryRecord) -> float:
        return (0.5 * max(0.0, cosine(a.embedding, b.embedding)) + 0.2 * jaccard(a.tags, b.tags)
                + 0.1 * (1.0 if a.domain == b.domain else 0.0) + 0.2 * jaccard(a.entities, b.entities))

    def _cluster(self) -> List[List[MemoryRecord]]:
        recs = self._store.all()
        used, clusters = set(), []
        for seed in recs:
            if seed.id in used:
                continue
            group = [seed]
            for other in recs:
                if other.id == seed.id or other.id in used:
                    continue
                if self._relatedness(seed, other) >= DEFAULTS["dreamRelatedness"]:
                    group.append(other)
            if len(group) >= DEFAULTS["dreamClusterMinSize"]:
                used.update(g.id for g in group)
                clusters.append(group)
        return clusters

    def _propose(self, out: List[DreamProposal], type: str, content: str, derivedFrom: List[str], suggestedDomain=None):
        self._seq += 1
        p = DreamProposal(id=f"dream-{self._seq}", type=type, content=content, derivedFrom=derivedFrom,
                          suggestedDomain=suggestedDomain)
        self._proposals[p.id] = p
        out.append(p)
        self._ledger.log(p.id, "dream_proposed", self._actor, details={"type": type, "derivedFrom": derivedFrom})

    def dream(self) -> List[DreamProposal]:
        created: List[DreamProposal] = []
        cap = DEFAULTS["maxDreamProposalsPerType"]
        for n, cluster in enumerate(self._cluster()):
            if n >= cap:
                break
            domains = "/".join(dict.fromkeys(m.domain for m in cluster))
            self._propose(created, "insight",
                          f"Across {len(cluster)} related memories ({domains}): " + " + ".join(m.content for m in cluster),
                          [m.id for m in cluster])
        domains_made = 0
        for m in self._store.all():
            if domains_made >= cap:
                break
            if m.domain != "general":
                continue
            suggested = self._store.classify_domain(m.content, m.tags, m.type)
            if suggested != "general":
                self._propose(created, "domain", f'Reclassify "{m.content[:60]}" as {suggested}', [m.id], suggested)
                domains_made += 1
        prefs = [m for m in self._store.all()
                 if m.type in ("preference", "personal") or "event:user_correction" in m.tags]
        by_domain: Dict[str, List[MemoryRecord]] = {}
        for p in prefs:
            by_domain.setdefault(p.domain, []).append(p)
        invariants = 0
        for domain, lst in by_domain.items():
            if invariants >= cap:
                break
            if len(lst) < 2:
                continue
            self._propose(created, "invariant", f"Stable pattern in {domain}: " + "; ".join(m.content for m in lst),
                          [m.id for m in lst])
            invariants += 1
        return created

    def pending(self) -> List[DreamProposal]:
        return [p for p in self._proposals.values() if p.status == "proposed"]

    def approve(self, proposal_id: str) -> Optional[MemoryRecord]:
        p = self._proposals.get(proposal_id)
        if not p or p.status != "proposed":
            raise KeyError(f"H-MEM: no pending proposal {proposal_id}")
        p.status = "approved"
        self._ledger.log(proposal_id, "dream_approved", self._actor, details={"type": p.type})
        if p.type == "domain":
            for rid in p.derivedFrom:
                if self._store.get(rid) and p.suggestedDomain:
                    self._store.update(rid, domain=p.suggestedDomain)
            return None
        return self._store.add(
            content=p.content, type="factual" if p.type == "insight" else "preference", layer="long_term",
            tags=[f"dream:{p.type}"], confidence=0.75, source="dreaming",
            provenance={"origin": "dream", "learnedAt": self._clock(), "label": f"approved {p.type} proposal"},
            derivedFrom=p.derivedFrom,
        )

    def reject(self, proposal_id: str) -> None:
        p = self._proposals.get(proposal_id)
        if not p or p.status != "proposed":
            raise KeyError(f"H-MEM: no pending proposal {proposal_id}")
        p.status = "rejected"
        self._ledger.log(proposal_id, "dream_rejected", self._actor, details={"type": p.type})


# ---------------------------------------------------------------------------
# Facade (reference: index.ts)
# ---------------------------------------------------------------------------

class HMEM:
    def __init__(self, clock: Optional[Callable[[], int]] = None, db_path: Optional[str] = None, actor: str = "system"):
        self.clock = clock or (lambda: int(time.time() * 1000))
        db = _SqlitePersistence(db_path) if db_path else None
        self.ledger = TrustLedgerService(self.clock, db)
        self.store = MemoryStoreService(self.clock, self.ledger, actor, db)
        self.retrieval = MemoryRetrievalService(self.store, self.ledger, self.clock, actor)
        self.conflicts = ConflictDetectionService(self.store, self.ledger, self.clock, actor)
        self.sleep = SleepCycleService(self.store, self.ledger, self.clock, actor)
        self.dreaming = DreamingService(self.store, self.ledger, self.clock, actor)

    def add(self, content: str, source: str, **kw) -> MemoryRecord:
        return self.store.add(content=content, source=source, **kw)

    def query(self, query: str, **kw) -> QueryResult:
        return self.retrieval.query(query, **kw)

    def feedback(self, memory_id: str, kind: str) -> None:
        self.retrieval.feedback(memory_id, kind)
