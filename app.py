"""
SangoDiag nurse UI (Streamlit).

    streamlit run app.py

Runs the same agent as the CLI (agent/agent.py) and shows the agent's work: the
H-MEM recall, every Nightshift call with its lane and the model that answered,
every SQL statement with the rows Zetaris returned, and each critic decision.
"""

from __future__ import annotations

import html
import os
import re
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import engine_h_mem, llm, tools_zetaris  # noqa: E402
from agent.agent import Event, demo_cases, run_case  # noqa: E402
from agent.main import _load_dotenv, sample_mode  # noqa: E402
from agent.triage import DANGER_SIGNS, SYMPTOMS, TEST_RESULTS, Intake  # noqa: E402

_load_dotenv()
DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
st.set_page_config(page_title="SangoDiag", page_icon=os.path.join(DOCS, "logo.png"), layout="wide")
st.logo(os.path.join(DOCS, "logo-wordmark.png"), size="large")

# One colour per next step, shared with the logo, slides and video
ACTION_STYLE = {
    "REFER_URGENT": ("#D9502F", "Danger sign found"),
    "TREAT_PER_PROTOCOL": ("#1E9E83", "Treat per protocol"),
    "DO_RDT": ("#C98A12", "Test first"),
    "SEND_LAB": ("#5B3A8E", "Needs the lab"),
    "OTHER_CAUSE": ("#3F8FD8", "Look elsewhere"),
    "STANDARD_CARE": ("#6B6478", "No malaria signal"),
}

LOGO_SVG = (
    '<svg viewBox="0 0 120 120" width="52" height="52" aria-hidden="true">'
    '<rect width="120" height="120" rx="28" fill="#5B3A8E"/>'
    '<path d="M60 17C60 17 29 53 29 75a31 31 0 0 0 62 0C91 53 60 17 60 17Z" fill="#fff"/>'
    '<path d="M45 76l11 11 21-24" fill="none" stroke="#5B3A8E" stroke-width="9" stroke-linecap="round" '
    'stroke-linejoin="round"/><circle cx="92" cy="27" r="9" fill="#EF6A4C"/></svg>'
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&display=swap');
:root { --ink:#1E1530; --paper:#F6F4F9; --giemsa:#5B3A8E; --line:#DDD5EA; --quiet:#6B6478; --coral:#EF6A4C; }
html, body, [class*="css"], .stMarkdown, .stTextInput, .stButton button, label, p, li {
  font-family: 'Atkinson Hyperlegible', system-ui, sans-serif !important; }
.stApp { background: var(--paper); color: var(--ink); }
h1, h2, h3 { font-family: 'Atkinson Hyperlegible', system-ui, sans-serif !important; color: var(--ink); letter-spacing: -0.01em; }
/* flat look: no Streamlit gradient bar, no deploy button */
[data-testid="stDecoration"], .stDeployButton, [data-testid="stAppDeployButton"] { display: none !important; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] { background: #fff; border-right: 1px solid var(--line); }
.block-container { padding-top: 2.6rem; max-width: 1280px; }
div.sd-head { display: flex; align-items: center; gap: .9rem; }
div.sd-title { font-size: 2.3rem; font-weight: 700; line-height: 1.1; margin: 0; }
div.sd-title span { color: var(--giemsa); }
.stButton button[kind="primary"], div[data-testid="stFormSubmitButton"] button { border-radius: 10px; font-weight: 700; }
@media (max-width: 760px) {
  .block-container { padding: 3.6rem 1rem 2rem; }
  div.sd-title { font-size: 1.8rem; }
  div.sd-head svg { width: 40px; height: 40px; }
  .sd-card .action { font-size: 1.45rem; }
}
.sd-sub { color: var(--quiet); font-size: 1.02rem; margin: .25rem 0 1.2rem; max-width: 70ch; }
.sd-card { border-left: 14px solid var(--band); background: #fff; border-radius: 6px; padding: 1.1rem 1.3rem 1rem;
  box-shadow: 0 1px 0 var(--line); margin-bottom: 1rem; }
.sd-card .kicker { color: var(--band); font-weight: 700; font-size: .95rem; margin: 0; }
.sd-card .action { font-size: 1.85rem; font-weight: 700; line-height: 1.15; margin: .15rem 0 .5rem; color: var(--ink); }
.sd-card .facts { color: var(--quiet); font-size: .95rem; margin: 0; }
.sd-card .facts b { color: var(--ink); }
.sd-mem { background: #EFE9F7; border: 1px solid #D9CEEA; border-radius: 6px; padding: .8rem 1rem; margin-bottom: 1rem; }
.sd-mem b { color: var(--giemsa); }
.sd-lane { display:inline-block; border:1px solid var(--line); border-radius: 4px; padding: 0 .4rem; font-size:.82rem;
  color: var(--giemsa); background:#fff; margin-left:.35rem; }
.sd-sim { color:#8A5A00; background:#FFF4DC; border-color:#F0D9A8; }
.sd-bar { height: 10px; background: var(--line); border-radius: 5px; overflow: hidden; margin: .15rem 0 .6rem; }
.sd-bar span { display:block; height:100%; background: var(--giemsa); }
.sd-note { color: var(--quiet); font-size: .88rem; }
.sd-step { border-left: 3px solid var(--line); padding: .1rem 0 .55rem .9rem; margin-left: .2rem; }
.sd-step.revise { border-left-color: #C98A12; } .sd-step.warn { border-left-color: #C98A12; } .sd-step.error { border-left-color: #D9502F; }
.sd-step .who { font-weight: 700; } .sd-step .meta { color: var(--quiet); font-size: .86rem; }
div[data-testid="stForm"] { background:#fff; border: 1px solid var(--line); border-radius: 6px; }
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Sidebar: how this copy is wired
# ---------------------------------------------------------------------------

@st.cache_data(ttl=20, show_spinner=False)
def _status(data_mode: str):
    return llm.provider_status(), tools_zetaris.status(data_mode)


with st.sidebar:
    st.markdown("### Setup")
    model_choice = st.radio("AI provider", ["Meterless Nightshift (live Nemotron)", "Rehearsal without a model"],
                            index=1 if sample_mode() else 0,
                            help="Rehearsal runs the same agent with a scripted stand-in. Every result it makes is labelled.")
    model_mode = "live" if model_choice.startswith("Meterless") else "offline"
    data_choice = st.radio("Data", ["Zetaris (live)", "Local copy of the CSV files"], index=1 if sample_mode() else 0)
    data_mode = "live" if data_choice.startswith("Zetaris") else "local"

    ns, zs = _status(data_mode)
    s = llm.Settings.from_env()
    st.markdown("#### Connections")
    ns_text = {"online": "online", "unauthorized": "token rejected", "offline": "not reachable"}[ns["state"]]
    st.write(f"Nightshift: **{ns_text}**  \n{ns['base_url']}")
    if ns["state"] == "online":
        for lane, info in ns["lanes"].items():
            st.caption(f"{lane.title()} lane: {info['model']} " + ("(listed)" if info["listed"] else "(not in /v1/models)"))
    else:
        st.caption(f"Fast lane: {s.fast_model}  \nDeep lane: {s.deep_model}")
    zs_text = {"online": "online", "unauthorized": "API key missing or rejected", "offline": "not reachable"}[zs["state"]]
    st.write(f"Zetaris: **{zs_text}**" + (" (local copy)" if data_mode == "local" else ""))
    hs = engine_h_mem.stats()
    st.write(f"H-MEM: **{hs['records']} records** for {hs['patients']} patients")
    st.write("Smear model: **" + ("connected" if os.environ.get("VISION_ENDPOINT_URL") else "not connected") + "**")
    if st.button("Check again"):
        _status.clear()
        st.rerun()

    st.markdown("#### Demo cases")
    cases = demo_cases()
    pick = st.selectbox("Load a scripted case", ["(none)"] + list(cases),
                        format_func=lambda k: k if k == "(none)" else cases[k]["label"])
    if pick != "(none)":
        st.caption(cases[pick]["story"])
    show_work = st.toggle("Show the agent's work", value=True)

preset = cases[pick]["intake"] if pick != "(none)" else {}


@st.cache_data(ttl=60, show_spinner=False)
def _patients(mode: str):
    return tools_zetaris.list_patients(mode)


patients = _patients(data_mode) or _patients("local")
pids = [p["patient_id"] for p in patients]
labels = {p["patient_id"]: f"{p['patient_id']} ({p['village']})" for p in patients}


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.markdown(f'<div class="sd-head">{LOGO_SVG}<div class="sd-title">Sango<span>Diag</span></div></div>',
            unsafe_allow_html=True)
st.markdown('<p class="sd-sub">Malaria triage support for nurses in rural health posts. It checks the patient record, '
            'the village\'s malaria situation and the last visit, then suggests one next step. '
            'The nurse decides.</p>', unsafe_allow_html=True)

left, right = st.columns([5, 7], gap="large")

with left:
    with st.form("intake", border=True):
        st.markdown("**Patient**")
        default_pid = preset.get("patient_id", pids[0] if pids else "")
        pid = st.selectbox("Patient ID", pids, index=pids.index(default_pid) if default_pid in pids else 0,
                           format_func=lambda x: labels.get(x, x), key=f"pid_{pick}")
        c1, c2, c3 = st.columns(3)
        age = c1.number_input("Age (years)", 0.0, 110.0, float(preset.get("age_years", 25)), 1.0, format="%.0f", key=f"age_{pick}")
        temp = c2.number_input("Temperature (C)", 34.0, 43.0, float(preset.get("temperature_c", 37.0)), 0.1,
                               format="%.1f", key=f"t_{pick}")
        days = c3.number_input("Fever days", 0, 30, int(preset.get("fever_days", 0)), key=f"d_{pick}")
        pregnant = st.checkbox("Pregnant", value=preset.get("pregnant", False), key=f"preg_{pick}")

        st.markdown("**Symptoms**")
        symptoms = st.pills("Symptoms", list(SYMPTOMS), selection_mode="multi", format_func=SYMPTOMS.get,
                            default=preset.get("symptoms", []), key=f"sx_{pick}", label_visibility="collapsed")
        st.markdown("**Danger signs**")
        danger = st.pills("Danger signs", list(DANGER_SIGNS), selection_mode="multi", format_func=DANGER_SIGNS.get,
                          default=preset.get("danger_signs", []), key=f"ds_{pick}", label_visibility="collapsed")
        c4, c5 = st.columns(2)
        travel = c4.checkbox("Travelled recently", value=preset.get("recent_travel", False), key=f"tr_{pick}")
        household = c5.checkbox("Fever in the household", value=preset.get("household_cases", False), key=f"hh_{pick}")

        st.markdown("**Test**")
        test = st.radio("Test result", list(TEST_RESULTS), format_func=TEST_RESULTS.get, horizontal=True,
                        index=list(TEST_RESULTS).index(preset.get("test_result", "not_done")), key=f"test_{pick}",
                        label_visibility="collapsed")
        image = st.file_uploader("Blood smear photo (optional)", type=["png", "jpg", "jpeg"], key=f"img_{pick}")
        notes = st.text_input("Note (optional)", key=f"note_{pick}")
        go = st.form_submit_button("Check this patient", type="primary", use_container_width=True)


def _step_html(e: Event) -> str:
    lane = ""
    if e.lane:
        c = e.call or {}
        if c.get("live"):
            lane = (f'<span class="sd-lane">{e.lane.title()} lane, {html.escape(c.get("model_reported", ""))}</span>')
        else:
            lane = f'<span class="sd-lane sd-sim">{e.lane.title()} lane, rehearsal (no model call)</span>'
    meta = []
    if e.call:
        c = e.call
        meta.append(f"asked for {html.escape(c['model_requested'])}")
        meta.append(f"{c['latency_ms']} ms")
        if (c.get("usage") or {}).get("total_tokens"):
            meta.append(f"{c['usage']['total_tokens']} tokens")
    if e.step == "execute":
        meta.append(f"{e.data['source']}")
        if e.data.get("request_id"):
            meta.append(f"request {e.data['request_id'][:8]}")
        meta.append(f"written by the {e.data['asked_by']}")
    return (f'<div class="sd-step {e.status}"><span class="who">{html.escape(e.actor)}</span> '
            f'{html.escape(e.title)}{lane}<br><span class="meta">{", ".join(meta)}</span></div>')


if go:
    intake = Intake(patient_id=pid, temperature_c=float(temp), fever_days=int(days), age_years=float(age),
                    pregnant=pregnant, symptoms=list(symptoms or []), danger_signs=list(danger or []),
                    recent_travel=travel, household_cases=household, test_result=test, notes=notes)
    with right:
        box = st.status("Working on it", expanded=True)

        def on_event(e: Event):
            box.markdown(_step_html(e), unsafe_allow_html=True)

        result = run_case(intake, model_mode=model_mode, data_mode=data_mode,
                          image_bytes=image.getvalue() if image else None, on_event=on_event)
        box.update(label=("Stopped: " + result.error) if result.error else f"Done in {result.elapsed_s} s",
                   state="error" if result.error else "complete", expanded=False)
    st.session_state["result"] = result

result = st.session_state.get("result")

with right:
    if result is None:
        st.markdown("Fill in today's visit on the left, then press **Check this patient**. "
                    "Pick a scripted case in the sidebar to load one of the demo patients.")
    elif result.error:
        st.error(f"The check could not finish: {result.error}")
        if "Nightshift" in result.error:
            st.markdown("Start Nightshift and paste its runtime token into `.env` as `METERLESS_RUNTIME_TOKEN`, "
                        "or switch the sidebar to **Rehearsal without a model** to practise the flow.")
        elif "Zetaris" in result.error or "SQL" in result.error:
            st.markdown("Check that Zetaris is running (`./verify.sh`) or switch the data source to the local copy.")
    else:
        tr = result.triage
        mem = result.memory

        # Memory banner
        if mem.get("count"):
            st.markdown(f'<div class="sd-mem"><b>Memory retrieved.</b> SangoDiag remembers {mem["count"]} '
                        f'record(s) about this patient from earlier visits.</div>', unsafe_allow_html=True)
            with st.expander("What SangoDiag remembers, and was it right?"):
                for it in mem["items"]:
                    st.markdown(f"**{it['when']}** {it['content']}  \n"
                                f"<span class='sd-note'>source {it['source']}, confidence {it['confidence']}, "
                                f"relevance {it['relevance']}</span>", unsafe_allow_html=True)
                    if it["source"].startswith("agent:"):
                        b1, b2, _ = st.columns([1, 1, 3])
                        if b1.button("It was right", key=f"ok_{it['id']}"):
                            engine_h_mem.feedback(it["id"], "helpful")
                            st.toast("Saved: H-MEM trusts this record more")
                        if b2.button("It was wrong", key=f"bad_{it['id']}"):
                            engine_h_mem.feedback(it["id"], "wrong")
                            st.toast("Saved: H-MEM marked this record for review")
        else:
            st.markdown('<div class="sd-mem">First visit on this device: no earlier memory for this patient.</div>',
                        unsafe_allow_html=True)

        # Decision card
        color, kicker = ACTION_STYLE.get(tr["action"], ("#5B3A8E", ""))
        conf = {"high": "high", "medium": "medium", "low": "low"}[tr["confidence"]]
        abstain = " SangoDiag is not sure: treat this as a weak suggestion." if tr["abstain"] else ""
        st.markdown(
            f'<div class="sd-card" style="--band:{color}"><p class="kicker">{kicker}</p>'
            f'<p class="action">{html.escape(tr["action_label"])}</p>'
            f'<p class="facts">Malaria likelihood <b>{tr["level"]}</b> ({tr["score"]} out of 100). '
            f'Confidence <b>{conf}</b>.{abstain}</p></div>', unsafe_allow_html=True)

        # Report
        if result.report_source == "nemotron":
            deep = next((c for c in result.calls if c["lane"] == "deep" and c["live"]), {})
            st.caption(f"Explanation written by {deep.get('model_reported', 'Nemotron')} through Meterless Nightshift, "
                       f"checked by the critic.")
        elif result.report_source == "offline-simulator":
            st.caption("Rehearsal: this explanation was written by the scripted stand-in, not by a model.")
        else:
            st.caption("The model's draft did not pass the critic's checks, so the rules' own summary is shown.")
        st.markdown(re.sub(r"(\*\*[^*\n]+\*\*)\n(?!\n)", r"\1\n\n", result.report))

        st.markdown("**Other causes to keep in mind**")
        for name, pct in sorted(tr["differential"].items(), key=lambda kv: -kv[1]):
            st.markdown(f"{name}: {pct}%<div class='sd-bar'><span style='width:{pct}%'></span></div>",
                        unsafe_allow_html=True)
        st.markdown("<p class='sd-note'>Rough relative weights from the demo rules, not a validated probability. "
                    "SangoDiag supports the nurse's decision; it does not replace a test, a doctor or the "
                    "national protocol. All patient data here is synthetic.</p>", unsafe_allow_html=True)

        # The agent's work
        if show_work:
            st.markdown("### How SangoDiag got here")
            lanes = [c for c in result.calls]
            live = [c for c in lanes if c["live"]]
            st.markdown(f"{len(lanes)} model calls ({len(live)} live through Nightshift), "
                        f"{len(result.queries)} SQL queries, {result.elapsed_s} s. "
                        f"Trace saved to `{os.path.relpath(result.log_path) if result.log_path else 'n/a'}`.")
            for e in result.events:
                st.markdown(_step_html(e), unsafe_allow_html=True)
                if e.step == "execute":
                    st.code(e.data["sql"], language="sql", wrap_lines=True)
                    if e.data.get("error"):
                        st.caption(f"Error returned to the planner: {e.data['error']}")
                    elif e.data.get("rows"):
                        st.dataframe(pd.DataFrame(e.data["rows"]), hide_index=True, use_container_width=True)
                elif e.step == "critic" and e.data.get("issues"):
                    st.markdown("\n".join(f"- {i}" for i in e.data["issues"]))
                elif e.step == "decide":
                    rs = pd.DataFrame(e.data["triage"]["reasons"])[["text", "points", "cite"]]
                    rs.columns = ["Reason", "Points", "Source"]
                    st.dataframe(rs, hide_index=True, use_container_width=True)
            with st.expander("H-MEM audit trail for this patient"):
                st.dataframe(pd.DataFrame(engine_h_mem.patient_ledger(result.intake["patient_id"])),
                             hide_index=True, use_container_width=True)
