"""
HTTP API for the Android Field App
==================================
Exposes the agent loop over REST so the field app runs the real pipeline
(H-MEM -> Nightshift -> Zetaris -> safety rules -> H-MEM).

Run:
    python -m uvicorn agent.api:app --host 0.0.0.0 --port 8000 --ws none
(--ws none: the API uses no websockets, and it avoids clashes with old `websockets` installs)
Android emulator reaches it at http://10.0.2.2:8000/, a phone on the same Wi-Fi at http://<PC-IP>:8000/
"""

import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent import llm, tools_zetaris
from agent.engine_h_mem import get_patient_context, list_all_memories
from agent.main import run_diagnosis
from agent.tools_zetaris import run_sql

app = FastAPI(title="SangoDiag Malaria Agent API", version="1.0")


class DiagnoseRequest(BaseModel):
    patient_id: str = Field(..., min_length=1)
    symptoms: str = Field(..., min_length=1)
    image_result: str = Field(..., min_length=1)
    weight_kg: Optional[float] = Field(None, gt=0, lt=300)


class SqlRequest(BaseModel):
    query: str = Field(..., min_length=1)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "nightshift": "configured" if llm.METERLESS_RUNTIME_TOKEN else "offline-rules",
        "zetaris": "configured" if tools_zetaris.ZETARIS_API_KEY else "local-synthetic",
        "model": llm.METERLESS_MODEL,
    }


@app.post("/diagnose")
def diagnose(req: DiagnoseRequest) -> dict:
    return run_diagnosis(req.patient_id, req.symptoms, req.image_result, req.weight_kg)


@app.post("/sql")
def sql(req: SqlRequest) -> List[dict]:
    result = run_sql(req.query)
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/memory")
def memories() -> List[dict]:
    return list_all_memories()


@app.get("/memory/{patient_id}")
def memory(patient_id: str) -> dict:
    return {"patient_id": patient_id, "context": get_patient_context(patient_id)}
