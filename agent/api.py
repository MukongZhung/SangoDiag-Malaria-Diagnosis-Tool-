"""
HTTP API for the Android field app
==================================
Exposes the same agent as the Streamlit UI (agent.agent.run_case) over REST.

Run:
    python -m uvicorn agent.api:app --host 0.0.0.0 --port 8000 --ws none
Android emulator reaches it at http://10.0.2.2:8000/, a phone on the same Wi-Fi at http://<PC-IP>:8000/

Modes follow the CLI flags: model_mode "live" (Nightshift) or "offline" (simulator),
data_mode "live" (Zetaris REST) or "local" (CSV replica). Defaults come from
SANGODIAG_MODEL_MODE / SANGODIAG_DATA_MODE.
"""

import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from agent import engine_h_mem, llm, tools_zetaris  # noqa: E402
from agent.agent import demo_cases, run_case  # noqa: E402
from agent.main import _load_dotenv  # noqa: E402
from agent.triage import Intake  # noqa: E402


@asynccontextmanager
async def lifespan(_app):
    # Load .env when the server starts, not at import, so importing the API (e.g. in tests) has no side effects
    _load_dotenv()
    yield


app = FastAPI(title="SangoDiag API", version="1.0", lifespan=lifespan)


def _default_model_mode() -> str:
    return os.environ.get("SANGODIAG_MODEL_MODE", "live")


def _default_data_mode() -> str:
    return os.environ.get("SANGODIAG_DATA_MODE", "live")


class DiagnoseRequest(BaseModel):
    patient_id: str = Field(..., min_length=1)
    temperature_c: Optional[float] = Field(None, gt=30, lt=45)
    fever_days: Optional[int] = Field(None, ge=0)
    age_years: Optional[float] = Field(None, ge=0, lt=130)
    pregnant: bool = False
    symptoms: List[str] = []
    danger_signs: List[str] = []
    recent_travel: bool = False
    household_cases: bool = False
    test_result: str = "not_done"
    notes: str = ""
    model_mode: Optional[str] = Field(None, pattern="^(live|offline)$")
    data_mode: Optional[str] = Field(None, pattern="^(live|local)$")


@app.get("/health")
def health(data_mode: Optional[str] = None) -> dict:
    return {
        "nightshift": llm.provider_status(),
        "zetaris": tools_zetaris.status(data_mode or _default_data_mode()),
        "defaults": {"model_mode": _default_model_mode(), "data_mode": _default_data_mode()},
    }


@app.get("/patients")
def patients(data_mode: Optional[str] = None) -> List[dict]:
    return tools_zetaris.list_patients(data_mode or _default_data_mode())


@app.get("/demo-cases")
def cases() -> dict:
    return demo_cases()


@app.post("/diagnose")
def diagnose(req: DiagnoseRequest) -> dict:
    fields = req.model_dump(exclude={"model_mode", "data_mode"})
    result = run_case(
        Intake(**fields),
        model_mode=req.model_mode or _default_model_mode(),
        data_mode=req.data_mode or _default_data_mode(),
    )
    return result.to_dict()


@app.get("/memory/{patient_id}")
def memory(patient_id: str) -> List[dict]:
    return engine_h_mem.patient_ledger(patient_id)
