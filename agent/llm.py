"""
Power layer: Meterless Nightshift client (SangoDiag's only AI provider).

Implements the Meterless Runtime provider contract
(https://github.com/Meterless/Meterless/blob/main/docs/agent-ready/add-meterless-provider.md):

  * OpenAI-compatible POST {base}/chat/completions, default base http://127.0.0.1:8088/v1
  * Authorization: Bearer <runtime token>   (Nightshift writes it to <stateDir>/proxy-token)
  * meterless-app: sangodiag on every request, meterless-scope: user on chat
  * GET {base}/models decides status: 200 + ids = online, 401/403 = unauthorized, else offline
  * 180 s timeout, because a cold model load can take minutes

Two lanes, both NVIDIA Nemotron behind Nightshift:
  FAST  (METERLESS_MODEL_FAST, default nvidia/nemotron-3.5-lightning-30b-a3b)
        planner: decides which Zetaris queries to run and writes the SQL (tool calls)
  DEEP  (METERLESS_MODEL_DEEP, default nvidia/nemotron-3-super-120b-a12b)
        reporter: writes the nurse-facing explanation from the gathered evidence

The NVIDIA API key never appears here. It lives only in Nightshift (Setup > Providers).

Every call returns a CallRecord with what really happened: the model id we asked
for, the model id Nightshift says answered, wall-clock latency, token usage and
any meterless-* response headers. Nothing in a CallRecord is made up.

Offline simulation exists for rehearsing the UI without a runtime. It must be
switched on explicitly (mode="offline"), and every record it produces says
live=False and model_reported="offline-simulator", so it can never pass for a
Nemotron call in a log or a screenshot.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import requests

APP_ID = "sangodiag"
DEFAULT_BASE_URL = "http://127.0.0.1:8088/v1"
DEFAULT_FAST = "nvidia/nemotron-3.5-lightning-30b-a3b"
DEFAULT_DEEP = "nvidia/nemotron-3-super-120b-a12b"
TIMEOUT_S = 180
# Nightshift stops a cloud lane after 45 s without a first token. Nemotron reasons
# before it answers, so ask for more room (the header takes up to 300000 ms).
TTFB_MS = os.environ.get("METERLESS_TTFB_MS", "240000")


class NightshiftError(RuntimeError):
    """Raised when a live Nightshift call fails. Never swallowed silently."""


def normalise_base_url(raw: str) -> str:
    """Accept a pasted URL with or without scheme, /v1, /v1/chat/completions, /v1/models or /healthz."""
    raw = (raw or DEFAULT_BASE_URL).strip()
    if "://" not in raw:
        raw = "http://" + raw
    p = urlparse(raw)
    path = p.path or ""
    for suffix in ("/chat/completions", "/models", "/healthz"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    path = path.rstrip("/")
    if path.endswith("/v1"):
        path = path[: -len("/v1")]
    return f"{p.scheme}://{p.netloc}{path}/v1"


@dataclass
class Settings:
    base_url: str
    token: str
    fast_model: str
    deep_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        fast = os.environ.get("METERLESS_MODEL_FAST") or os.environ.get("METERLESS_MODEL") or DEFAULT_FAST
        return cls(
            base_url=normalise_base_url(os.environ.get("METERLESS_BASE_URL", DEFAULT_BASE_URL)),
            token=os.environ.get("METERLESS_RUNTIME_TOKEN", "").strip(),
            fast_model=fast,
            deep_model=os.environ.get("METERLESS_MODEL_DEEP") or DEFAULT_DEEP,
        )

    def model_for(self, lane: str) -> str:
        return self.deep_model if lane == "deep" else self.fast_model


@dataclass
class CallRecord:
    lane: str                      # "fast" | "deep"
    role: str                      # what the call was for: planner, reporter, ...
    model_requested: str
    model_reported: str            # the id Nightshift returned in the response body / header
    live: bool                     # False only for the explicit offline simulator
    latency_ms: int
    usage: Dict[str, Any] = field(default_factory=dict)
    runtime_headers: Dict[str, str] = field(default_factory=dict)
    finish_reason: Optional[str] = None
    retries: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ChatResult:
    content: str
    tool_calls: List[Dict[str, Any]]
    message: Dict[str, Any]        # assistant message to append to the conversation
    record: CallRecord


def strip_reasoning(text: Optional[str]) -> str:
    """Nemotron reasoning models can return their thinking inline, ending with </think>."""
    if not text:
        return ""
    end = text.rfind("</think>")
    if end >= 0:
        text = text[end + len("</think>"):]
    return re.sub(r"<think>[\s\S]*$", "", text).strip()


def _headers(settings: Settings, chat: bool) -> Dict[str, str]:
    h = {"meterless-app": APP_ID}
    if settings.token:
        h["Authorization"] = f"Bearer {settings.token}"
    if chat:
        h.update({"meterless-scope": "user", "meterless-ttfb-ms": TTFB_MS, "Content-Type": "application/json"})
    return h


def provider_status(settings: Optional[Settings] = None, timeout: float = 5.0) -> Dict[str, Any]:
    """Online check per the contract: /v1/models decides, not /healthz."""
    s = settings or Settings.from_env()
    try:
        r = requests.get(f"{s.base_url}/models", headers=_headers(s, chat=False), timeout=timeout)
    except requests.RequestException as e:
        return {"state": "offline", "models": [], "detail": type(e).__name__, "base_url": s.base_url}
    if r.status_code in (401, 403):
        return {"state": "unauthorized", "models": [], "detail": f"HTTP {r.status_code}", "base_url": s.base_url}
    if r.status_code != 200:
        return {"state": "offline", "models": [], "detail": f"HTTP {r.status_code}", "base_url": s.base_url}
    try:
        ids = [m.get("id") for m in r.json().get("data", []) if m.get("id")]
    except ValueError:
        ids = []
    lanes = {
        "fast": {"model": s.fast_model, "listed": s.fast_model in ids},
        "deep": {"model": s.deep_model, "listed": s.deep_model in ids},
    }
    return {"state": "online" if ids else "offline", "models": ids, "lanes": lanes, "base_url": s.base_url,
            "detail": "" if ids else "no models listed"}


def chat(messages: List[Dict[str, Any]], lane: str, role: str, tools: Optional[List[Dict[str, Any]]] = None,
         settings: Optional[Settings] = None, temperature: float = 0.2) -> ChatResult:
    """One live chat completion on a Nightshift lane. Retries once on 5xx or an empty answer."""
    s = settings or Settings.from_env()
    if not s.token:
        raise NightshiftError("METERLESS_RUNTIME_TOKEN is not set. Copy it from Nightshift (Console / proxy-token).")
    model = s.model_for(lane)
    payload: Dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    last_err: Optional[str] = None
    for attempt in range(2):
        started = time.perf_counter()
        try:
            r = requests.post(f"{s.base_url}/chat/completions", headers=_headers(s, chat=True),
                              json=payload, timeout=TIMEOUT_S)
        except requests.RequestException as e:
            raise NightshiftError(f"Nightshift unreachable at {s.base_url} ({type(e).__name__})") from e
        latency = int((time.perf_counter() - started) * 1000)
        if r.status_code in (401, 403):
            raise NightshiftError(f"Nightshift rejected the runtime token (HTTP {r.status_code})")
        if r.status_code >= 500:
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            time.sleep(2)
            continue
        if r.status_code != 200:
            raise NightshiftError(f"Nightshift returned HTTP {r.status_code}: {r.text[:300]}")
        body = r.json()
        choice = (body.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = strip_reasoning(msg.get("content"))
        tool_calls = msg.get("tool_calls") or []
        if not content and not tool_calls:
            last_err = "empty answer"
            continue
        record = CallRecord(
            lane=lane, role=role, model_requested=model,
            model_reported=body.get("model") or r.headers.get("meterless-model") or "not reported",
            live=True, latency_ms=latency, usage=body.get("usage") or {},
            runtime_headers={k: v for k, v in r.headers.items() if k.lower().startswith(("meterless", "x-meterless"))},
            finish_reason=choice.get("finish_reason"), retries=attempt,
        )
        assistant = {"role": "assistant", "content": msg.get("content")}
        if tool_calls:
            assistant["tool_calls"] = tool_calls
        return ChatResult(content=content, tool_calls=tool_calls, message=assistant, record=record)
    raise NightshiftError(f"Nightshift failed after a retry: {last_err}")


# ---------------------------------------------------------------------------
# Explicit offline simulator (rehearsal only, always labelled)
# ---------------------------------------------------------------------------

def simulated_chat(messages: List[Dict[str, Any]], lane: str, role: str,
                   responder: Callable[[List[Dict[str, Any]]], Dict[str, Any]],
                   settings: Optional[Settings] = None) -> ChatResult:
    """Runs a deterministic stand-in supplied by the agent. Never claims to be Nemotron."""
    s = settings or Settings.from_env()
    started = time.perf_counter()
    msg = responder(messages)
    record = CallRecord(lane=lane, role=role, model_requested=s.model_for(lane),
                        model_reported="offline-simulator", live=False,
                        latency_ms=int((time.perf_counter() - started) * 1000))
    tool_calls = msg.get("tool_calls") or []
    assistant = {"role": "assistant", "content": msg.get("content")}
    if tool_calls:
        assistant["tool_calls"] = tool_calls
    return ChatResult(content=strip_reasoning(msg.get("content")), tool_calls=tool_calls,
                      message=assistant, record=record)


def make_tool_call(name: str, arguments: Dict[str, Any], call_id: str) -> Dict[str, Any]:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
