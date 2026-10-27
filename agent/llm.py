"""
Meterless Nightshift LLM Client
Connects to Meterless Nightshift (OpenAI-compatible API) to orchestrate NVIDIA Nemotron models
for clinical reasoning and tool-calling in rural healthcare diagnostics.
"""

import os
import re
import json
import logging
from typing import Dict, Any, List, Optional
try:
    import requests
except ImportError:
    requests = None
import urllib.request
import urllib.error

from agent import clinical_rules
from agent.tools_zetaris import patient_baseline_sql

logger = logging.getLogger("NightshiftLLM")
METERLESS_BASE_URL = os.environ.get("METERLESS_BASE_URL", "https://runtime.meterless.ai/v1").rstrip("/")
METERLESS_RUNTIME_TOKEN = os.environ.get("METERLESS_RUNTIME_TOKEN", "")
METERLESS_MODEL = os.environ.get("METERLESS_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")


def call_nightshift(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Call Meterless Nightshift OpenAI-compatible chat completions endpoint.
    Routes to NVIDIA Nemotron models with exact hackathon required headers.
    """
    # A local Meterless runtime (127.0.0.1 / localhost) needs no token
    is_local_runtime = any(h in METERLESS_BASE_URL for h in ("127.0.0.1", "localhost"))
    if not METERLESS_RUNTIME_TOKEN and not is_local_runtime:
        logger.info("METERLESS_RUNTIME_TOKEN not set. Running in offline rules mode.")
        return _autonomous_fallback_response(messages, tools)

    endpoint = f"{METERLESS_BASE_URL}/chat/completions"

    headers = {
        "Authorization": f"Bearer {METERLESS_RUNTIME_TOKEN}",
        "meterless-app": "malaria-agent",
        "meterless-scope": "user",
        "Content-Type": "application/json"
    }

    payload: Dict[str, Any] = {
        "model": METERLESS_MODEL,
        "messages": messages,
        "temperature": 0.2
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    try:
        if requests is not None:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                data = response.json()
                data["_headers"] = dict(response.headers)
                print_routing_info(data)
                return data
            else:
                logger.warning("Nightshift API status %s. Falling back to offline rules mode.", response.status_code)
                return _autonomous_fallback_response(messages, tools)
        else:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(endpoint, data=req_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                data["_headers"] = dict(resp.headers)
                print_routing_info(data)
                return data

    except Exception as e:
        logger.info("Nightshift remote endpoint connection: %s. Falling back to offline rules mode.", e)
        return _autonomous_fallback_response(messages, tools)


def print_routing_info(response: Dict[str, Any]) -> None:
    """
    Prints which model/lane actually served the request, using only what the
    response reports. Nothing is shown that the runtime did not return.
    """
    headers = {k.lower(): v for k, v in response.get("_headers", {}).items()}
    is_fallback = response.get("_fallback", False)

    print("\n" + "=" * 55)
    print("  METERLESS NIGHTSHIFT ROUTING AUDIT")
    print("=" * 55)
    print(f" Target Model : {METERLESS_MODEL}")
    if is_fallback:
        print(" Executed By  : LOCAL RULES ENGINE (offline - no remote call made)")
    else:
        print(f" Executed By  : {response.get('model', 'not reported')}")
        print(f" Routing Lane : {headers.get('x-meterless-lane') or headers.get('x-nightshift-lane') or 'not reported'}")
        print(f" Latency      : {headers.get('x-response-time') or 'not reported'}")
        usage = response.get("usage") or {}
        if usage:
            print(f" Tokens       : {usage.get('prompt_tokens', '?')} in / {usage.get('completion_tokens', '?')} out")
    print(" App Header   : meterless-app: malaria-agent")
    print(" Scope        : meterless-scope: user")
    print("=" * 55 + "\n")


def _extract_field(text: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.*)$", text or "", re.MULTILINE)
    return match.group(1).strip() if match else ""


def _autonomous_fallback_response(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Offline mode for field posts without connectivity (or without credentials).
    Mimics the tool-calling flow, but the diagnosis comes from the deterministic
    rules in clinical_rules.py applied to the real case and the real Zetaris rows.
    """
    user_text = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
    patient_id = _extract_field(user_text, "Patient ID")
    tool_messages = [m for m in messages if m.get("role") == "tool"]

    if tools and not tool_messages:
        patient_query = patient_baseline_sql(patient_id)
        response = {
            "id": "local-fallback-toolcall",
            "model": "local-rules-engine",
            "_fallback": True,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_zetaris_sql_001",
                        "type": "function",
                        "function": {"name": "run_sql", "arguments": json.dumps({"query": patient_query})}
                    }]
                },
                "finish_reason": "tool_calls"
            }]
        }
    else:
        records: List[Dict[str, Any]] = []
        for m in tool_messages:
            try:
                data = json.loads(m.get("content") or "[]")
            except ValueError:
                continue
            if isinstance(data, list):
                records.extend(r for r in data if isinstance(r, dict))

        weight_match = re.match(r"([\d.]+)\s*kg", _extract_field(user_text, "Body Weight"))
        weight_kg = float(weight_match.group(1)) if weight_match else None
        assessment = clinical_rules.assess(
            patient_id,
            _extract_field(user_text, "Presenting Symptoms"),
            _extract_field(user_text, "Rapid Diagnostic / Microscopy Image Result"),
            records,
            weight_kg,
        )
        response = {
            "id": "local-fallback-diagnosis",
            "model": "local-rules-engine",
            "_fallback": True,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": clinical_rules.render_report(assessment)},
                "finish_reason": "stop"
            }]
        }

    print_routing_info(response)
    return response
