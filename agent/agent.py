"""
SangoDiag agent: planner -> executor -> critic -> rules -> reporter -> critic -> memory.

    1. RECALL    H-MEM ranks what we already know about this patient.
    2. PLAN      Nemotron on the FAST lane decides which facts it needs and writes
                 the SQL, calling run_sql as a tool.
    3. EXECUTE   run_sql sends each statement to Zetaris; the smear image (if any)
                 goes to the vision endpoint.
    4. CHECK     The critic checks the evidence. Missing village, endemic zone or
                 visit history -> the planner gets the critique and revises its
                 queries (one revision round). Still missing -> a labelled
                 baseline query written by code, never silently.
    5. DECIDE    Transparent triage rules pick ONE next step (agent/triage.py).
    6. REPORT    Nemotron on the DEEP lane explains it for the nurse, citing [Qn].
    7. CHECK     The critic checks the draft: citations exist, no drug doses, no
                 antimalarial before a positive test, "refer" present when there is
                 a danger sign. Fails -> the reporter revises (up to 2 rounds).
    8. REMEMBER  H-MEM stores today's observation and the recommendation.

Every step is emitted as an event (for the UI) and written to logs/run-<id>.jsonl.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from agent import engine_h_mem, llm, tools_vision, tools_zetaris
from agent.triage import ACTIONS, Evidence, Intake, TriageResult, extract_evidence, triage

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.environ.get("SANGODIAG_LOG_DIR", os.path.join(BASE_DIR, "logs"))

MAX_PLANNER_TURNS = 4
MAX_PLANNER_REVISIONS = 1
MAX_REPORTER_REVISIONS = 2

RUN_SQL_TOOL = {
    "type": "function",
    "function": {
        "name": "run_sql",
        "description": "Run ONE read-only SQL statement on the Zetaris federated data platform and get rows back.",
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "A single SELECT statement."}},
            "required": ["sql"],
        },
    },
}


# ---------------------------------------------------------------------------
# Run state
# ---------------------------------------------------------------------------

@dataclass
class Event:
    step: str           # recall | plan | execute | critic | decide | report | remember | vision | error
    actor: str          # H-MEM | Planner | Zetaris | Critic | Rules | Reporter | Vision
    title: str
    status: str = "ok"  # ok | warn | error | revise
    lane: Optional[str] = None
    call: Optional[Dict[str, Any]] = None
    data: Dict[str, Any] = field(default_factory=dict)
    t: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))


@dataclass
class RunResult:
    run_id: str
    intake: Dict[str, Any]
    model_mode: str
    data_mode: str
    events: List[Event] = field(default_factory=list)
    queries: List[Dict[str, Any]] = field(default_factory=list)
    memory: Dict[str, Any] = field(default_factory=dict)
    vision: Optional[Dict[str, Any]] = None
    triage: Optional[Dict[str, Any]] = None
    report: str = ""
    report_source: str = ""
    calls: List[Dict[str, Any]] = field(default_factory=list)
    memory_written: List[str] = field(default_factory=list)
    error: Optional[str] = None
    elapsed_s: float = 0.0
    log_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


class _Run:
    def __init__(self, intake: Intake, model_mode: str, data_mode: str, on_event: Optional[Callable[[Event], None]]):
        self.intake = intake
        self.model_mode = model_mode
        self.data_mode = data_mode
        self.on_event = on_event
        self.settings = llm.Settings.from_env()
        self.result = RunResult(run_id=datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6],
                                intake=asdict(intake), model_mode=model_mode, data_mode=data_mode)
        self.tables = tools_zetaris.table_names()

    # -- plumbing --------------------------------------------------------
    def emit(self, ev: Event) -> None:
        self.result.events.append(ev)
        if ev.call:
            self.result.calls.append(ev.call)
        if self.on_event:
            self.on_event(ev)

    def call_model(self, messages, lane: str, role: str, tools=None, responder=None) -> llm.ChatResult:
        if self.model_mode == "offline":
            return llm.simulated_chat(messages, lane, role, responder, self.settings)
        return llm.chat(messages, lane, role, tools=tools, settings=self.settings)

    def execute_sql(self, sql: str, asked_by: str) -> tools_zetaris.SqlResult:
        res = tools_zetaris.run_sql(sql, mode=self.data_mode)
        res.qid = f"Q{len(self.result.queries) + 1}"
        res.asked_by = asked_by
        self.result.queries.append(res.to_dict())
        self.emit(Event("execute", "Zetaris" if res.source == "zetaris" else "Local replica",
                        f"{res.qid} {'returned ' + str(len(res.rows)) + ' row(s)' if res.ok else 'failed'}",
                        status="ok" if res.ok else "warn",
                        data={"qid": res.qid, "sql": res.sql, "rows": res.rows[:20], "columns": res.columns,
                              "source": res.source, "request_id": res.request_id, "latency_ms": res.latency_ms,
                              "error": res.error, "asked_by": asked_by}))
        return res


# ---------------------------------------------------------------------------
# Planner (FAST lane)
# ---------------------------------------------------------------------------

def _planner_system(tables: Dict[str, str]) -> str:
    return (
        "You are the PLANNER of SangoDiag, a malaria triage assistant for nurses in rural Cameroon.\n"
        "Your only job is to collect facts from the Zetaris data platform with the run_sql tool. Do not diagnose.\n\n"
        "Tables available (ANSI / Lightning SQL):\n" + tools_zetaris.schema_doc() + "\n\n"
        "You need, for the patient id given:\n"
        "  1. the patient's village and family history\n"
        "  2. the endemic zone and active cases of that village\n"
        "  3. the patient's earlier visits\n"
        "Rules: one SELECT per tool call; always filter on the patient id or the patient's village; "
        "quote string values with single quotes; joins are fine. If a query fails, read the error and fix it.\n"
        "When you have the facts, answer with the single word DONE."
    )


def _offline_planner(tables: Dict[str, str], pid: str):
    def respond(messages):
        done = sum(1 for m in messages if m.get("role") == "tool")
        critique = next((m["content"] for m in reversed(messages)
                         if m.get("role") == "user" and "CRITIC" in (m.get("content") or "")), None)
        if done == 0:
            sql = (f"SELECT p.patient_id, p.age, p.village, p.family_history_malaria, p.recent_travel, e.endemic_zone, e.active_cases_this_week "
                   f"FROM {tables['patients']} p JOIN {tables['regional_epidemiology']} e ON p.village = e.village "
                   f"WHERE p.patient_id = '{pid}'")
            return {"tool_calls": [llm.make_tool_call("run_sql", {"sql": sql}, "call_1")]}
        if done == 1:
            sql = (f"SELECT visit_id, patient_id, visit_date, fever_temp_c, body_pain, headache, nausea FROM {tables['clinical_visits']} "
                   f"WHERE patient_id = '{pid}'")
            return {"tool_calls": [llm.make_tool_call("run_sql", {"sql": sql}, "call_2")]}
        if critique and done < 4:
            sql = f"SELECT village, endemic_zone, active_cases_this_week, breeding_site_risk FROM {tables['regional_epidemiology']}"
            return {"tool_calls": [llm.make_tool_call("run_sql", {"sql": sql}, f"call_{done + 1}")]}
        return {"content": "DONE"}
    return respond


_SQL_BLOCK = re.compile(r"```sql\s*([\s\S]*?)```", re.I)


def _sql_from_text(text: str) -> List[str]:
    """Some lanes answer with SQL in text instead of a tool call; accept that too."""
    blocks = [b.strip() for b in _SQL_BLOCK.findall(text or "")]
    if blocks:
        return blocks
    return [ln.strip().rstrip(";") for ln in (text or "").splitlines() if re.match(r"^\s*(select|with)\b", ln, re.I)]


def _plan_round(run: _Run, messages: List[Dict[str, Any]], round_no: int) -> None:
    pid = run.intake.patient_id
    responder = _offline_planner(run.tables, pid)
    for turn in range(1, MAX_PLANNER_TURNS + 1):
        res = run.call_model(messages, "fast", "planner", tools=[RUN_SQL_TOOL], responder=responder)
        rec = res.record.to_dict()
        messages.append(res.message)
        calls = res.tool_calls
        if not calls:
            inline = _sql_from_text(res.content)
            if inline:
                calls = [llm.make_tool_call("run_sql", {"sql": s}, f"inline_{turn}_{i}") for i, s in enumerate(inline)]
                messages[-1] = {"role": "assistant", "content": res.content, "tool_calls": calls}
        sqls = []
        for c in calls:
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except (ValueError, KeyError):
                args = {}
            sqls.append(args.get("sql") or args.get("query") or "")
        n = len(calls)
        what = f"asks Zetaris for {n} quer{'y' if n == 1 else 'ies'}" if calls else "has the facts it needs"
        run.emit(Event("plan", "Planner", f"turn {turn}{f' (revision {round_no})' if round_no else ''}: {what}",
                       lane="fast", call=rec,
                       data={"decision": "query" if calls else "done", "sql": sqls,
                             "text": res.content[:400] if not calls else ""}))
        if not calls:
            return
        for c, sql in zip(calls, sqls):
            out = run.execute_sql(sql, asked_by="planner")
            messages.append({"role": "tool", "tool_call_id": c.get("id", "call"), "content": json.dumps(out.for_model())})


def _coverage(run: _Run) -> List[str]:
    """Critic, evidence pass: what is still missing?"""
    ev = extract_evidence(run.result.queries, [], None, run.intake.patient_id, int(time.time() * 1000))
    missing = []
    if ev.village is None:
        missing.append(f"No row for patient '{run.intake.patient_id}' with a village. Query {run.tables['patients']}.")
    if ev.endemic_zone is None:
        where = f" WHERE village = '{ev.village}'" if ev.village else ""
        missing.append(f"No endemic zone found for the patient's village. Query {run.tables['regional_epidemiology']}{where}.")
    visits_asked = any(q.get("error") is None and run.tables["clinical_visits"].lower() in q["sql"].lower()
                       for q in run.result.queries)
    if not visits_asked:
        missing.append(f"Earlier visits were not checked. Query {run.tables['clinical_visits']} for this patient.")
    return missing


def _baseline_queries(run: _Run, missing: List[str]) -> None:
    pid = run.intake.patient_id
    t = run.tables
    for m in missing:
        if m.startswith("No row") or m.startswith("No endemic"):
            run.execute_sql(f"SELECT p.patient_id, p.age, p.village, p.family_history_malaria, p.recent_travel, e.endemic_zone, e.active_cases_this_week "
                            f"FROM {t['patients']} p LEFT JOIN {t['regional_epidemiology']} e ON p.village = e.village "
                            f"WHERE p.patient_id = '{pid}'", asked_by="baseline")
            break
    if any(m.startswith("Earlier visits") for m in missing):
        run.execute_sql(f"SELECT visit_id, patient_id, visit_date, fever_temp_c, body_pain, headache, nausea FROM {t['clinical_visits']} "
                        f"WHERE patient_id = '{pid}'", asked_by="baseline")


# ---------------------------------------------------------------------------
# Reporter (DEEP lane) and the draft critic
# ---------------------------------------------------------------------------

_DOSE = re.compile(r"\b\d+(\.\d+)?\s?(mg|mcg|g|ml|tablets?|tabs?|caps(ules)?)\b", re.I)
_GIVE_ANTIMALARIAL = re.compile(
    r"\b(give|start|prescribe|administer|begin)\b[^.\n]{0,60}\b(act|artemether|lumefantrine|coartem|artesunate|antimalarial|quinine)", re.I)


def _reporter_system(tr: TriageResult) -> str:
    return (
        "You are the REPORTER of SangoDiag. You write for a nurse in a rural Cameroonian health post, "
        "in plain English she can read in 30 seconds.\n"
        f"The protocol rules have ALREADY chosen the next step: {tr.action} ({tr.action_label}). "
        "Do not change it and do not add a different main action.\n"
        "Explain it using ONLY the evidence given. Cite every fact in square brackets: [Q1], [Q2] for Zetaris "
        "queries (use only ids that exist), [MEM] for the patient's history, [NURSE] for what the nurse observed, "
        "[IMG] for the image model.\n"
        "Never give doses or quantities (no mg, no number of tablets): say 'per the national protocol chart'.\n"
        "Do not suggest any antimalarial unless the step is TREAT_PER_PROTOCOL.\n"
        "If there is a danger sign, say clearly that the patient must be referred.\n"
        "Format exactly:\n**Assessment**\n1-2 sentences.\n\n**Why**\n- 3 to 5 bullets, each ending with its citation\n\n"
        "**What to do now**\n1. numbered steps\n\n**Watch for**\n- 1 or 2 bullets\n"
        "Stay under 180 words."
    )


def _evidence_package(run: _Run, ev: Evidence, tr: TriageResult) -> Dict[str, Any]:
    return {
        "patient_id": run.intake.patient_id,
        "nurse_observation": run.intake.describe(),
        "zetaris_queries": [{"id": q["qid"], "sql": q["sql"], "rows": q["rows"][:10], "error": q.get("error")}
                            for q in run.result.queries],
        "patient_history_from_memory": run.result.memory.get("context") or "none (first visit)",
        "image_model": run.result.vision or "no image",
        "rules_decision": {"step": tr.action, "label": tr.action_label, "malaria_score": tr.score,
                           "level": tr.level, "confidence": tr.confidence, "reasons": tr.reasons,
                           "protocol_steps": tr.next_steps, "differential_percent": tr.differential},
    }


def template_report(run: _Run, ev: Evidence, tr: TriageResult) -> str:
    """Deterministic report built from the rules. Used offline and as the safety fallback."""
    zone = f"{ev.village} is a {ev.endemic_zone} malaria zone" if ev.endemic_zone else "endemic zone unknown"
    lines = ["**Assessment**", "",
             f"Malaria likelihood {tr.level} ({tr.score}/100); {zone}. Next step: {tr.action_label.lower()}.",
             "", "**Why**", ""]
    for r in sorted(tr.reasons, key=lambda r: (not r.get("key"), -abs(r["points"])))[:5]:
        cite = r["cite"] if r["cite"].startswith(("Q", "IMG")) else ("MEM" if r["cite"].startswith("MEM") else "NURSE")
        lines.append(f"- {r['text']} [{cite}]")
    lines += ["", "**What to do now**", ""] + [f"{i}. {s}" for i, s in enumerate(tr.next_steps, 1)]
    lines += ["", "**Watch for**", "",
              "- Convulsions, confusion, inability to drink, vomiting everything, breathing difficulty: refer at once."]
    return "\n".join(lines)


def _offline_reporter(run: _Run, ev: Evidence, tr: TriageResult):
    def respond(_messages):
        return {"content": template_report(run, ev, tr)}
    return respond


_NEGATION = re.compile(r"\b(not|no|never|avoid|without|before)\b|n't\b", re.I)


def _suggests_antimalarial(text: str) -> bool:
    """True when the text tells the nurse to give an antimalarial (negated phrasing is fine)."""
    for m in _GIVE_ANTIMALARIAL.finditer(text):
        start = max(text.rfind(".", 0, m.start()), text.rfind("\n", 0, m.start())) + 1
        if not _NEGATION.search(text[start:m.end()]):
            return True
    return False


def critique_report(text: str, tr: TriageResult, query_ids: List[str], danger: bool) -> List[str]:
    issues = []
    cited = set(re.findall(r"\[(Q\d+)\]", text))
    if query_ids and not cited:
        issues.append("Cite at least one Zetaris query, e.g. [Q1], next to the fact it supports.")
    unknown = sorted(c for c in cited if c not in query_ids)
    if unknown:
        issues.append(f"These citations do not exist: {', '.join(unknown)}. Use only {', '.join(query_ids)}.")
    if _DOSE.search(text):
        issues.append("Remove every dose or quantity; say 'per the national protocol chart' instead.")
    if tr.action not in ("TREAT_PER_PROTOCOL", "REFER_URGENT") and _suggests_antimalarial(text):
        issues.append("Do not suggest antimalarials: there is no positive test (test before treat).")
    if danger and "refer" not in text.lower():
        issues.append("There is a danger sign: say clearly that the patient must be referred.")
    keywords = {"DO_RDT": "rdt", "SEND_LAB": "microscop", "REFER_URGENT": "refer", "TREAT_PER_PROTOCOL": "protocol",
                "OTHER_CAUSE": "cause", "STANDARD_CARE": ""}
    kw = keywords.get(tr.action, "")
    if kw and kw not in text.lower():
        issues.append(f"State the decided next step ({tr.action_label}) explicitly.")
    for heading in ("**Assessment**", "**Why**", "**What to do now**"):
        if heading.lower() not in text.lower():
            issues.append(f"Keep the required format: the {heading} section is missing.")
    return issues


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_case(intake: Intake, model_mode: str = "live", data_mode: str = "live",
             image_bytes: Optional[bytes] = None, on_event: Optional[Callable[[Event], None]] = None,
             vision_override: Optional[Dict[str, Any]] = None) -> RunResult:
    started = time.perf_counter()
    run = _Run(intake, model_mode, data_mode, on_event)
    try:
        _run(run, image_bytes, vision_override)
    except (llm.NightshiftError, Exception) as e:  # noqa: BLE001 - surface every failure to the nurse UI
        run.result.error = f"{type(e).__name__}: {e}"
        run.emit(Event("error", "System", "Run stopped", status="error", data={"error": run.result.error}))
    run.result.elapsed_s = round(time.perf_counter() - started, 1)
    run.result.log_path = _write_log(run.result)
    return run.result


def _run(run: _Run, image_bytes: Optional[bytes], vision_override: Optional[Dict[str, Any]]) -> None:
    intake = run.intake
    pid = intake.patient_id
    presentation = intake.describe()

    # 1. RECALL
    mem = engine_h_mem.recall(pid, presentation)
    run.result.memory = mem
    run.emit(Event("recall", "H-MEM",
                   f"Memory retrieved: {mem['count']} earlier record(s)" if mem["count"] else "No earlier memory: first visit",
                   data={"items": mem["items"], "trace": mem["trace"]}))

    # 3a. EXECUTE (vision) - before the planner so the evidence package is complete
    if vision_override is not None:
        run.result.vision = vision_override
    elif image_bytes:
        run.result.vision = tools_vision.analyze_smear(image_bytes)
    if run.result.vision is not None:
        v = run.result.vision
        title = ("Image model: parasites flagged" if v.get("parasite_present") else
                 "Image model: no parasites seen" if v.get("parasite_present") is False else
                 "Image not classified")
        run.emit(Event("vision", "Vision", title, status="ok" if v.get("available") else "warn", data=v))

    # 2-4. PLAN / EXECUTE / CHECK (with revision)
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": _planner_system(run.tables)},
        {"role": "user", "content": f"Patient id: {pid}\nToday: {presentation}\n\n"
                                    f"{mem['context'] or 'No earlier memory for this patient.'}"},
    ]
    _plan_round(run, messages, 0)
    missing = _coverage(run)
    for rev in range(1, MAX_PLANNER_REVISIONS + 1):
        if not missing:
            break
        run.emit(Event("critic", "Critic", "Evidence incomplete: sent back to the planner", status="revise",
                       data={"issues": missing}))
        messages.append({"role": "user", "content": "CRITIC: the evidence is incomplete.\n- " + "\n- ".join(missing)
                                                    + "\nRun the missing queries, then answer DONE."})
        _plan_round(run, messages, rev)
        missing = _coverage(run)
    if missing:
        run.emit(Event("critic", "Critic", "Still incomplete: running labelled baseline queries", status="warn",
                       data={"issues": missing}))
        _baseline_queries(run, missing)
        missing = _coverage(run)
    run.emit(Event("critic", "Critic", "Evidence check passed" if not missing else "Evidence still incomplete",
                   status="ok" if not missing else "warn", data={"issues": missing}))

    # 5. DECIDE
    now_ms = int(time.time() * 1000)
    ev = extract_evidence(run.result.queries, mem["items"], run.result.vision, pid, now_ms)
    tr = triage(intake, ev)
    run.result.triage = tr.to_dict()
    run.emit(Event("decide", "Rules", f"{tr.action_label} (malaria score {tr.score}/100, {tr.level})",
                   status="warn" if tr.urgent else "ok",
                   data={"triage": tr.to_dict(), "evidence": asdict(ev)}))

    # 6-7. REPORT / CHECK (with revision)
    qids = [q["qid"] for q in run.result.queries if not q.get("error")]
    package = _evidence_package(run, ev, tr)
    rmsgs = [{"role": "system", "content": _reporter_system(tr)},
             {"role": "user", "content": "Evidence package (JSON):\n" + json.dumps(package, default=str, indent=1)}]
    responder = _offline_reporter(run, ev, tr)
    final, source = "", ""
    for attempt in range(MAX_REPORTER_REVISIONS + 1):
        res = run.call_model(rmsgs, "deep", "reporter", responder=responder)
        draft = res.content
        issues = critique_report(draft, tr, qids, bool(intake.danger_signs))
        run.emit(Event("report", "Reporter", "Draft written" if attempt == 0 else f"Revision {attempt}",
                       lane="deep", call=res.record.to_dict(), data={"draft": draft}))
        if not issues:
            run.emit(Event("critic", "Critic", "Report approved", data={"issues": []}))
            final, source = draft, ("nemotron" if res.record.live else "offline-simulator")
            break
        run.emit(Event("critic", "Critic", "Report rejected: sent back to the reporter", status="revise",
                       data={"issues": issues}))
        rmsgs += [res.message, {"role": "user", "content": "CRITIC: fix these problems and rewrite the whole report.\n- "
                                + "\n- ".join(issues)}]
    if not final:
        final, source = template_report(run, ev, tr), "rules-template"
        run.emit(Event("critic", "Critic", "Reporter could not pass the checks: showing the rules template",
                       status="warn"))
    run.result.report, run.result.report_source = final, source

    # 8. REMEMBER
    today = datetime.now().strftime("%Y-%m-%d")
    observation = f"Visit {today}: {presentation}."
    zone = f"{ev.village} {ev.endemic_zone} zone" if ev.endemic_zone else "zone unknown"
    recommendation = (f"Visit {today}: SangoDiag advised '{tr.action_label}' (malaria score {tr.score}/100, {tr.level}; "
                      f"{zone}; test: {intake.test_result}).")
    model = run.settings.deep_model if model_mode_live(run) else "offline-simulator"
    ids = engine_h_mem.remember_encounter(pid, observation, recommendation, model, run.result.run_id, action=tr.action)
    run.result.memory_written = ids
    run.emit(Event("remember", "H-MEM", f"Saved {len(ids)} memory records for next time",
                   data={"ids": ids, "observation": observation, "recommendation": recommendation}))


def model_mode_live(run: _Run) -> bool:
    return run.model_mode == "live"


def _write_log(result: RunResult) -> Optional[str]:
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, f"run-{result.run_id}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            head = {"run_id": result.run_id, "model_mode": result.model_mode, "data_mode": result.data_mode,
                    "intake": result.intake, "elapsed_s": result.elapsed_s, "error": result.error}
            f.write(json.dumps({"type": "run", **head}, default=str) + "\n")
            for e in result.events:
                f.write(json.dumps({"type": "event", **asdict(e)}, default=str) + "\n")
            f.write(json.dumps({"type": "result", "triage": result.triage, "report": result.report,
                                "report_source": result.report_source}, default=str) + "\n")
        return path
    except OSError:
        return None


def demo_cases() -> Dict[str, Dict[str, Any]]:
    with open(os.path.join(BASE_DIR, "examples", "demo_cases.json"), encoding="utf-8") as f:
        return json.load(f)
