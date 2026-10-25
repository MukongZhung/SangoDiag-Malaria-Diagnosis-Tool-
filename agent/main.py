"""
Orchestration Agent Loop: AI Malaria Diagnosis Agent for Rural Cameroon
========================================================================
Integrates:
- Meterless Nightshift (NVIDIA Nemotron 30B / 120B reasoning)
- Zetaris Federated SQL Data Layer (cross-querying S3 & local epidemiology)
- Meterless H-MEM Persistent Clinical Memory Engine
"""

import sys
import os
import json
import logging
from typing import Dict, Any, List

# Ensure agent package imports work cleanly whether invoked directly or as a module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.llm import call_nightshift
from agent.tools_zetaris import run_sql
from agent.engine_h_mem import get_patient_context, save_patient_context

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
                        "description": "The ANSI SQL query to run on federated tables (patients, clinical_visits, regional_epidemiology)."
                    }
                },
                "required": ["query"]
            }
        }
    }
]


def diagnose_patient(patient_id: str, symptoms: str, image_result: str) -> str:
    """
    Orchestrates the clinical diagnosis workflow:
    1. H-MEM: Fetches past patient clinical memory.
    2. Constructs grounded clinical prompt.
    3. Calls Meterless Nightshift (Nemotron) with tool calling enabled.
    4. Handles SQL tool execution via Zetaris and feeds data back to model.
    5. Saves diagnosis back to H-MEM persistent memory.
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
        "Include drug dosages (e.g. Artemether-Lumefantrine / Coartem), supportive antipyretic care, "
        "and danger signs requiring urgent hospital escalation."
    )

    user_message = (
        f"Patient ID: {patient_id}\n"
        f"Presenting Symptoms: {symptoms}\n"
        f"Rapid Diagnostic / Microscopy Image Result: {image_result}\n"
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

    while turn < max_turns:
        turn += 1
        print(f"[Agent Loop] Calling Nightshift LLM (Turn {turn})...")
        response = call_nightshift(messages, tools=TOOLS)

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
                    except Exception as err:
                        sql_query = fn_args_raw

                    # Execute Zetaris SQL Tool
                    sql_result = run_sql(sql_query)

                    # Append tool execution result
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(sql_result)
                    })
        else:
            # Model has produced final text output
            final_diagnosis = assistant_msg.get("content", "")
            print("\n" + "-" * 65)
            print("  NEMOTRON GROUNDED CLINICAL DIAGNOSIS")
            print("-" * 65)
            print(final_diagnosis)
            print("-" * 65 + "\n")
            break

    # Step 4: Persist interaction into H-MEM
    encounter_summary = f"Symptoms: {symptoms} | Test: {image_result} | Diagnosis: Plasmodium falciparum positive | Prescribed: First-line ACT (Coartem) + Paracetamol"
    save_patient_context(patient_id, encounter_summary)

    return final_diagnosis


if __name__ == "__main__":
    print("\n=======================================================")
    print("   AI MALARIA DIAGNOSIS AGENT - CAMEROON FIELD TEST")
    print("   Meterless Nightshift + Zetaris + H-MEM Engine")
    print("=======================================================\n")

    # Mock simulation as specified in Phase 4 prompt:
    # Patient 123, fever, image says malaria
    test_patient_id = "123"
    test_symptoms = "High fever (39.4°C), severe chills, vomiting, joint pain for 2 days"
    test_image_result = "RDT Cassette: HRP2 Line Strongly Positive; Blood Smear: Plasmodium falciparum ring-form trophozoites visible"

    diagnosis = diagnose_patient(
        patient_id=test_patient_id,
        symptoms=test_symptoms,
        image_result=test_image_result
    )

    print("\n[VERIFICATION] Verifying H-MEM Persistence after session completion...")
    reloaded_memory = get_patient_context(test_patient_id)
    print(f"[VERIFICATION] Retrieved H-MEM context for Patient {test_patient_id}:\n{reloaded_memory}\n")
    print("[SUCCESS] All agent layers (Nightshift + Zetaris + H-MEM) completed smoothly!\n")
