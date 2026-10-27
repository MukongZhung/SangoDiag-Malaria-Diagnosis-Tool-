"""
Data layer: Zetaris REST SQL tool (run_sql).

Live mode talks to the local Zetaris platform exactly as the hackathon's Start Here
lesson describes:

    POST {ZETARIS_BASE_URL}/sql-editor/sqls/run          (default http://localhost:8888/api/v1.0)
    Authorization: Bearer <ZETARIS_API_KEY>
    X-Org-ID: 1                                           (local install)
    X-Request-ID: <fresh UUID per request>
    body: {"queryId": <UUID>, "sql": <ONE statement>, "source": "SqlEditor", "limit": N}

Rules we follow from Zetaris's AGENTS.md: one Lightning SQL statement per call,
never print credentials. On top of that, the agent may only read: anything that is
not a single SELECT / WITH statement is refused before it leaves the process.

Local replica mode loads synthetic_data/*.csv into an in-memory SQLite under the
same table names, so the same SQL runs offline. Every result says which source
answered (`source` = "zetaris" or "local-replica"), and nothing falls back from one
to the other silently.

Table names are configurable because Engineer 2 decides how the S3 files are
registered in Zetaris (for example `malaria_s3.patients`):
    ZETARIS_TABLE_PATIENTS, ZETARIS_TABLE_VISITS, ZETARIS_TABLE_EPI
"""

from __future__ import annotations

import csv
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYNTHETIC_DIR = os.path.join(BASE_DIR, "synthetic_data")
MAX_ROWS = 200


def table_names() -> Dict[str, str]:
    return {
        "patients": os.environ.get("ZETARIS_TABLE_PATIENTS", "patients"),
        "clinical_visits": os.environ.get("ZETARIS_TABLE_VISITS", "clinical_visits"),
        "regional_epidemiology": os.environ.get("ZETARIS_TABLE_EPI", "regional_epidemiology"),
    }


SCHEMA_DOC = """\
{patients}(patient_id, age, gender, village, family_history_malaria, recent_travel)   -- one row per patient; booleans are 'TRUE'/'FALSE'
{clinical_visits}(visit_id, patient_id, visit_date, fever_temp_c, body_pain, headache, nausea)   -- earlier visits; fever_temp_c in degrees C, may be empty
{regional_epidemiology}(village, endemic_zone, active_cases_this_week, breeding_site_risk)   -- endemic_zone and breeding_site_risk are High / Medium / Low"""


def schema_doc() -> str:
    return SCHEMA_DOC.format(**table_names())


class ZetarisError(RuntimeError):
    pass


class SqlRefused(ZetarisError):
    pass


_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|truncate|merge|grant|revoke|attach|pragma)\b", re.I)


def check_read_only(sql: str) -> str:
    s = (sql or "").strip().rstrip(";").strip()
    if not s:
        raise SqlRefused("empty SQL")
    if ";" in s:
        raise SqlRefused("one statement per call (Zetaris rule)")
    if not re.match(r"^(select|with)\b", s, re.I):
        raise SqlRefused("only SELECT / WITH queries are allowed")
    if _FORBIDDEN.search(s):
        raise SqlRefused("write or DDL keyword found; the agent may only read")
    return s


@dataclass
class SqlResult:
    sql: str
    source: str                    # "zetaris" | "local-replica"
    columns: List[str]
    rows: List[Dict[str, Any]]
    latency_ms: int
    request_id: Optional[str] = None
    error: Optional[str] = None
    qid: Optional[str] = None      # set by the agent: Q1, Q2, ...
    asked_by: str = "planner"      # who wrote the SQL: planner (Nemotron) | baseline (code) | critic

    @property
    def ok(self) -> bool:
        return self.error is None

    def for_model(self) -> Dict[str, Any]:
        if self.error:
            return {"query_id": self.qid, "error": self.error}
        return {"query_id": self.qid, "row_count": len(self.rows), "rows": self.rows[:50]}

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


# ---------------------------------------------------------------------------
# Live Zetaris
# ---------------------------------------------------------------------------

def _settings():
    return (
        os.environ.get("ZETARIS_BASE_URL", "http://localhost:8888/api/v1.0").rstrip("/"),
        os.environ.get("ZETARIS_API_KEY", "").strip(),
        os.environ.get("ZETARIS_ORG_ID", "1"),
    )


def _normalise(body: Any) -> tuple[List[str], List[Dict[str, Any]]]:
    if isinstance(body, list):
        data, meta = body, None
    else:
        data = body.get("data") or []
        meta = body.get("headers") or body.get("columns") or body.get("columnNames") or body.get("schema")
    cols: List[str] = []
    if isinstance(meta, list):
        cols = [c if isinstance(c, str) else str(c.get("name") or c.get("columnName") or "") for c in meta]
    if data and isinstance(data[0], dict):
        cols = cols or list(data[0].keys())
        return cols, [dict(r) for r in data]
    if data and isinstance(data[0], list):
        if not cols:
            cols = [f"col{i}" for i in range(len(data[0]))]
        return cols, [dict(zip(cols, r)) for r in data]
    return cols, []


def _run_live(sql: str, limit: int) -> SqlResult:
    base, key, org = _settings()
    if not key:
        raise ZetarisError("ZETARIS_API_KEY is not set (create one in the Zetaris web UI)")
    request_id = str(uuid.uuid4())
    headers = {"Authorization": f"Bearer {key}", "X-Org-ID": str(org), "X-Request-ID": request_id,
               "Content-Type": "application/json"}
    payload = {"queryId": str(uuid.uuid4()), "sql": sql, "source": "SqlEditor", "limit": limit}
    started = time.perf_counter()
    last = None
    for _ in range(2):  # Zetaris runs Spark underneath; one retry on timeout / 5xx
        try:
            r = requests.post(f"{base}/sql-editor/sqls/run", headers=headers, json=payload, timeout=60)
        except requests.Timeout as e:
            last = f"timeout ({e.__class__.__name__})"
            continue
        except requests.RequestException as e:
            raise ZetarisError(f"Zetaris unreachable at {base} ({type(e).__name__})") from e
        if r.status_code >= 500:
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            headers["X-Request-ID"] = request_id = str(uuid.uuid4())  # fresh UUID per request
            continue
        if r.status_code == 401:
            raise ZetarisError("HTTP 401: Zetaris API key missing, wrong or expired")
        if r.status_code == 400:
            raise ZetarisError(f"HTTP 400: {r.text[:300]} (check X-Org-ID and the SQL)")
        if r.status_code != 200:
            raise ZetarisError(f"HTTP {r.status_code}: {r.text[:300]}")
        cols, rows = _normalise(r.json())
        return SqlResult(sql=sql, source="zetaris", columns=cols, rows=rows,
                         latency_ms=int((time.perf_counter() - started) * 1000), request_id=request_id)
    raise ZetarisError(f"Zetaris query failed after a retry: {last}")


# ---------------------------------------------------------------------------
# Local replica (same table names, SQLite)
# ---------------------------------------------------------------------------

_replica: Optional[sqlite3.Connection] = None


def _replica_conn() -> sqlite3.Connection:
    global _replica
    if _replica is not None:
        return _replica
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    for logical, qualified in table_names().items():
        schema, _, table = qualified.rpartition(".")
        if schema:
            try:
                conn.execute(f"ATTACH DATABASE ':memory:' AS \"{schema}\"")
            except sqlite3.OperationalError:
                pass  # already attached
            target = f'"{schema}"."{table}"'
        else:
            target = f'"{table}"'
        with open(os.path.join(SYNTHETIC_DIR, f"{logical}.csv"), encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            conn.execute(f"CREATE TABLE {target} ({', '.join(f'{chr(34)}{c}{chr(34)} TEXT' for c in header)})")
            conn.executemany(f"INSERT INTO {target} VALUES ({','.join('?' * len(header))})", list(reader))
    _replica = conn
    return conn


def _run_replica(sql: str, limit: int) -> SqlResult:
    started = time.perf_counter()
    try:
        cur = _replica_conn().execute(sql)
    except sqlite3.Error as e:
        raise ZetarisError(f"SQL error: {e}") from e
    rows = [dict(r) for r in cur.fetchmany(limit)]
    cols = [d[0] for d in cur.description or []]
    return SqlResult(sql=sql, source="local-replica", columns=cols, rows=rows,
                     latency_ms=int((time.perf_counter() - started) * 1000))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_sql(sql: str, mode: str = "live", limit: int = MAX_ROWS) -> SqlResult:
    """Run ONE read-only statement. mode = "live" (Zetaris REST) or "local" (CSV replica).

    Errors come back inside the result (error=...) so the planner can read them and
    fix its SQL on the next turn; they are never replaced by made-up rows.
    """
    try:
        clean = check_read_only(sql)
        return _run_live(clean, limit) if mode == "live" else _run_replica(clean, limit)
    except ZetarisError as e:
        return SqlResult(sql=sql, source="zetaris" if mode == "live" else "local-replica",
                         columns=[], rows=[], latency_ms=0, error=str(e))


def status(mode: str = "live") -> Dict[str, Any]:
    res = run_sql("SELECT 1 AS one", mode=mode, limit=1)
    if res.ok:
        return {"state": "online", "source": res.source}
    state = "unauthorized" if "401" in (res.error or "") or "API_KEY" in (res.error or "") else "offline"
    return {"state": state, "source": res.source, "detail": res.error}


def list_patients(mode: str = "local") -> List[Dict[str, Any]]:
    t = table_names()
    res = run_sql(f"SELECT patient_id, village FROM {t['patients']} ORDER BY patient_id", mode=mode)
    return res.rows if res.ok else []
