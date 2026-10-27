"""
Orchestration Agent Loop: AI Malaria Diagnosis Agent for Rural Cameroon
========================================================================
Integrates:
- Meterless Nightshift (NVIDIA Nemotron 30B / 120B reasoning)
- Zetaris Federated SQL Data Layer (cross-querying S3 & local epidemiology)
- Meterless H-MEM Persistent Clinical Memory Engine
- Deterministic clinical safety rules (agent/clinical_rules.py)
"""

import sys
import os
import json
import time
import logging
from typing import Dict, Any, List, Optional

# Ensure agent package imports work cleanly whether invoked directly or as a module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.llm import call_nightshift
from agent.tools_zetaris import run_sql, patient_baseline_sql, TABLE_SCHEMAS
from agent.engine_h_mem import get_patient_context, save_patient_context
from agent import clinical_rules

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MalariaAgent")

# Tool schema definition for OpenAI-compatible function calling in Nightshift
TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": "Execute a SQL query against Zetaris federated database to retrieve patient history, prior clinical visits, and regional epidemiology endemicity in Cameroon.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The ANSI SQL query to run on the federated tables: "
                                       + "; ".join(f"{t}({cols})" for t, cols in TABLE_SCHEMAS.items())
                    }
                },
                "required": ["query"]
            }
        }
    }
]

def diagnose_patient(patient_id: str, symptoms: str, image_result: str,
                     weight_kg: Optional[float] = None) -> str:
    """Runs the agent and returns the clinical report text."""
    return run_diagnosis(patient_id, symptoms, image_result, weight_kg)["report"]


def run_diagnosis(patient_id: str, symptoms: str, image_result: str,
                  weight_kg: Optional[float] = None) -> Dict[str, Any]:
    """
    Orchestrates the clinical diagnosis workflow:
    1. H-MEM: Fetches past patient clinical memory.
    2. Constructs grounded clinical prompt.
    3. Calls Meterless Nightshift (Nemotron) with tool calling enabled.
    4. Handles SQL tool execution via Zetaris and feeds data back to model.
    5. Cross-checks the case with the deterministic safety rules.
    6. Saves a truthful encounter summary back to H-MEM persistent memory.
    """
    print("\n" + "=" * 65)
    print(f"  INITIATING AI MALARIA DIAGNOSIS FOR PATIENT: {patient_id}")
    print("=" * 65)

    # Step 1: Retrieve past memory using H-MEM
    past_memory = get_patient_context(patient_id)
    print(f"\n[H-MEM Retrieval] Memory for Patient {patient_id}:")
    if past_memory:
        print(f"  --> FOUND PERSISTENT CONTEXT:\n{past_memory}\n")
    else:
        print("  --> No prior sessions found. Starting fresh intake profile.\n")

    # Step 2: Construct the system prompt and conversation messages
    system_prompt = (
        "You are a medical AI in Cameroon specializing in infectious tropical diseases. "
        "Use SQL to query Zetaris for patient history and endemic zones. "
        "Combine this with the provided symptoms and vision results to recommend RDT or treatment. "
        "Always adhere strictly to Cameroon Ministry of Public Health and WHO malaria guidelines. "
        "Never prescribe antimalarials without a positive parasitological test. "
        "Include weight-based drug dosages (e.g. Artemether-Lumefantrine / Coartem), supportive antipyretic care, "
        "and danger signs requiring urgent hospital escalation."
    )

    user_message = (
        f"Patient ID: {patient_id}\n"
        f"Presenting Symptoms: {symptoms}\n"
        f"Rapid Diagnostic / Microscopy Image Result: {image_result}\n"
        f"Body Weight: {f'{weight_kg:g} kg' if weight_kg else 'not recorded'}\n"
        f"Longitudinal Memory from H-MEM: {past_memory or 'None'}\n\n"
        "Please query Zetaris for the patient's baseline record and village epidemiology to establish risk."
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    # Step 3: Agent Orchestration Loop (Tool Calling)
    max_turns = 5
    turn = 0
    final_diagnosis = ""
    zetaris_rows: List[Dict[str, Any]] = []
    sql_queries: List[str] = []
    llm_calls: List[Dict[str, Any]] = []

    while turn < max_turns:
        turn += 1
        print(f"[Agent Loop] Calling Nightshift LLM (Turn {turn})...")
        started = time.perf_counter()
        response = call_nightshift(messages, tools=TOOLS)
        headers = {k.lower(): v for k, v in response.get("_headers", {}).items()}
        llm_calls.append({
            "mode": "offline-rules" if response.get("_fallback") else "nightshift",
            "executed_model": response.get("model"),
            "routing_lane": headers.get("x-meterless-lane") or headers.get("x-nightshift-lane"),
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "usage": response.get("usage"),
        })

        choices = response.get("choices", [])
        if not choices:
            print("[Agent Loop] Warning: Received empty response choices.")
            break

        assistant_msg = choices[0].get("message", {})
        tool_calls = assistant_msg.get("tool_calls")

        # Append assistant message to history
        messages.append(assistant_msg)

        if tool_calls:
            for tool_call in tool_calls:
                call_id = tool_call.get("id")
                fn_name = tool_call.get("function", {}).get("name")
                fn_args_raw = tool_call.get("function", {}).get("arguments", "{}")

                print(f"[Agent Loop] LLM requested Tool: {fn_name}")

                if fn_name == "run_sql":
                    try:
                        args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                        sql_query = args.get("query", "")
                    except Exception:
                        sql_query = fn_args_raw

                    # Execute Zetaris SQL Tool
                    sql_queries.append(sql_query)
                    sql_result = run_sql(sql_query)
                    if isinstance(sql_result, list):
                        zetaris_rows.extend(r for r in sql_result if isinstance(r, dict))

                    # Append tool execution result
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(sql_result)
                    })
        else:
            # Model has produced final text output
            final_diagnosis = assistant_msg.get("content", "") or ""
            break

    # Step 4: Deterministic safety cross-check, grounded on the patient's own Zetaris record
    if not any(str(r.get("patient_id")) == str(patient_id) for r in zetaris_rows):
        baseline_sql = patient_baseline_sql(patient_id)
        sql_queries.append(baseline_sql)
        baseline = run_sql(baseline_sql)
        if isinstance(baseline, list):
            zetaris_rows.extend(baseline)
    assessment = clinical_rules.assess(patient_id, symptoms, image_result, zetaris_rows, weight_kg)

    if not final_diagnosis:
        print("[Agent Loop] No final answer from the LLM. Using the rules engine report.")
        final_diagnosis = clinical_rules.render_report(assessment)
    alert = clinical_rules.safety_alert(assessment)
    if alert:
        final_diagnosis = f"{final_diagnosis}\n\n{alert}"

    print("\n" + "-" * 65)
    print("  GROUNDED CLINICAL DIAGNOSIS")
    print("-" * 65)
    print(final_diagnosis)
    print("-" * 65 + "\n")

    # Step 5: Persist interaction into H-MEM
    saved_note = clinical_rules.encounter_summary(assessment, symptoms, image_result)
    save_patient_context(patient_id, saved_note)

    return {
        "patient_id": str(patient_id),
        "report": final_diagnosis,
        "safety_alert": alert,
        "assessment": {
            "diagnosis": assessment.diagnosis,
            "treatment": assessment.treatment,
            "test_result": assessment.test_result,
            "temperature": assessment.temperature,
            "severe_signs": assessment.severe_signs,
            "is_severe": assessment.is_severe,
            "village": assessment.village,
            "endemic_zone": assessment.endemic_zone,
            "active_cases": assessment.active_cases,
            "age": assessment.age,
            "gender": assessment.gender,
            "recent_travel": assessment.recent_travel,
            "coartem_tablets_per_dose": (
                clinical_rules.coartem_tablets_per_dose(weight_kg)
                if weight_kg and assessment.test_result == "positive" and not assessment.is_severe else None
            ),
        },
        "sql_queries": sql_queries,
        "sql_rows": zetaris_rows,
        "memory_before": past_memory,
        "memory_saved_note": saved_note,
        "llm_calls": llm_calls,
    }


# Contrasting field cases from the hackathon dataset
DEMO_CASES = [
    {   # Limbe, 34 F, high endemic zone: confirmed uncomplicated malaria
        "patient_id": "a1c3e5f7-2b4d-4c6e-8f10-1a2b3c4d5e01",
        "symptoms": "Fever (38.6°C), headache, body pain for 2 days",
        "image_result": "RDT Cassette: HRP2 line positive; Blood smear: P. falciparum ring-form trophozoites visible",
        "weight_kg": 58,
    },
    {   # Bafoussam, 23 F, medium zone: negative test
        "patient_id": "f6b8d0e2-7a9c-4b1d-9465-6f7a8b9c0d06",
        "symptoms": "Fever (37.9°C), headache, sore throat",
        "image_result": "RDT Cassette: control line only, HRP2 negative",
        "weight_kg": 60,
    },
    {   # Garoua, 3-year-old boy, high zone: severe malaria in an under-five
        "patient_id": "c9e1a3b5-0d2f-4e4a-8798-9c0d1e2f3a09",
        "symptoms": "Fever (40.3°C), persistent vomiting, convulsions this morning",
        "image_result": "RDT Cassette: HRP2 line strongly positive",
        "weight_kg": 13,
    },
    {   # Bertoua, 52 M: temperature never recorded at the visit
        "patient_id": "d4f6b8c0-5e7a-4f9b-b243-4d5e6f7a8b04",
        "symptoms": "Feels feverish, body pain",
        "image_result": "RDT Cassette: HRP2 line positive",
    },
]


if __name__ == "__main__":
    print("\n=======================================================")
    print("   AI MALARIA DIAGNOSIS AGENT - CAMEROON FIELD TEST")
    print("   Meterless Nightshift + Zetaris + H-MEM Engine")
    print("=======================================================\n")

    for case in DEMO_CASES:
        diagnose_patient(**case)

    print("\n[VERIFICATION] H-MEM persistent memory after the session:")
    for case in DEMO_CASES:
        print(f"\n--- {case['patient_id']} ---\n{get_patient_context(case['patient_id'])}")
    print()
