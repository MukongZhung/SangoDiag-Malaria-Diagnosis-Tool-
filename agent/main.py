"""
SangoDiag command line.

    python -m agent.main --status                      # is Nightshift / Zetaris reachable?
    python -m agent.main --case clear_malaria          # one demo case, live Nightshift + live Zetaris
    python -m agent.main --case all --local-data       # all demo cases, Zetaris replaced by the CSV replica
    python -m agent.main --case all --offline --local-data   # rehearsal, no model calls (clearly labelled)

The nurse UI (streamlit run app.py) runs exactly the same agent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import llm, tools_zetaris  # noqa: E402
from agent.agent import Event, demo_cases, run_case  # noqa: E402
from agent.triage import Intake  # noqa: E402


def _load_dotenv() -> None:
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def sample_mode() -> bool:
    """SAMPLE_MODE=true runs with no keys: offline simulator + local CSV copy."""
    return os.environ.get("SAMPLE_MODE", "").strip().lower() in ("1", "true", "yes")


def _print_event(e: Event) -> None:
    lane = f" [{e.lane.upper()} LANE]" if e.lane else ""
    mark = {"ok": " ", "warn": "!", "error": "X", "revise": "~"}.get(e.status, " ")
    print(f"{mark} {e.t} {e.actor:<13}{lane} {e.title}")
    if e.call:
        c = e.call
        tag = "LIVE" if c["live"] else "SIMULATED - no model call"
        usage = c.get("usage") or {}
        tok = f", {usage.get('total_tokens')} tokens" if usage.get("total_tokens") else ""
        print(f"      model asked: {c['model_requested']} | answered by: {c['model_reported']} "
              f"| {c['latency_ms']} ms{tok} | {tag}")
    if e.step == "execute":
        print(f"      {e.data['sql']}")
        if e.data.get("error"):
            print(f"      error: {e.data['error']}")
    if e.step == "critic" and e.data.get("issues"):
        for i in e.data["issues"]:
            print(f"      - {i}")


def main() -> int:
    # Windows consoles default to cp1252; Nemotron output can contain any Unicode character
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    _load_dotenv()
    ap = argparse.ArgumentParser(description="SangoDiag malaria triage agent")
    ap.add_argument("--status", action="store_true", help="check Nightshift and Zetaris, then exit")
    ap.add_argument("--case", default="clear_malaria", help="demo case name from examples/demo_cases.json, or 'all'")
    ap.add_argument("--offline", action="store_true", help="rehearse without Nightshift (simulated, labelled)")
    ap.add_argument("--local-data", action="store_true", help="use the CSV replica instead of live Zetaris")
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = ap.parse_args()
    if sample_mode():
        args.offline, args.local_data = True, True
        print("SAMPLE_MODE=true: scripted stand-in model and local CSV copy, no Nightshift or Zetaris calls")

    if args.status:
        ns = llm.provider_status()
        print(f"Nightshift : {ns['state']} at {ns['base_url']} {ns.get('detail') or ''}")
        for lane, info in (ns.get("lanes") or {}).items():
            print(f"  {lane} lane -> {info['model']} ({'listed' if info['listed'] else 'NOT listed in /v1/models'})")
        zs = tools_zetaris.status("live")
        print(f"Zetaris    : {zs['state']} {zs.get('detail') or ''}")
        return 0

    cases = demo_cases()
    names = list(cases) if args.case == "all" else [args.case]
    model_mode = "offline" if args.offline else "live"
    data_mode = "local" if args.local_data else "live"
    failures = 0
    for name in names:
        case = cases[name]
        print("\n" + "=" * 78 + f"\n{case['label']}\n{case['story']}\n" + "=" * 78)
        result = run_case(Intake(**case["intake"]), model_mode=model_mode, data_mode=data_mode,
                          on_event=_print_event)
        if result.error:
            print(f"\nRUN FAILED: {result.error}")
            failures += 1
            continue
        print("\n" + result.report)
        got = result.triage["action"]
        ok = got == case.get("expected_action")
        failures += 0 if ok else 1
        print(f"\n-> {got} (expected {case.get('expected_action')}) {'OK' if ok else 'MISMATCH'} "
              f"| report by {result.report_source} | {result.elapsed_s}s | log {result.log_path}")
        if args.json:
            print(json.dumps(result.to_dict(), default=str, indent=1))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
