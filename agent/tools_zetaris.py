import os
import uuid
import logging
import sqlite3
import csv
import json
from typing import List, Dict, Any, Union
try:
    import requests
except ImportError:
    requests = None
import urllib.request
import urllib.error

logger = logging.getLogger("ZetarisTool")

# Environment configuration
ZETARIS_API_KEY = os.environ.get("ZETARIS_API_KEY", "")
ZETARIS_ORG_ID = os.environ.get("ZETARIS_ORG_ID", "1")
ZETARIS_BASE_URL = os.environ.get("ZETARIS_BASE_URL", "http://localhost:8888/api/v1.0").rstrip("/")

# Federated tables exposed to the LLM (hackathon dataset schema)
TABLE_SCHEMAS = {
    "patients": "patient_id, age, gender, village, family_history_malaria, recent_travel",
    "clinical_visits": "visit_id, patient_id, visit_date, fever_temp_c, body_pain, headache, nausea",
    "regional_epidemiology": "village, endemic_zone, active_cases_this_week, breeding_site_risk",
}


def patient_baseline_sql(patient_id: str) -> str:
    """Patient record + latest visit + village epidemiology, in one federated query."""
    safe_id = str(patient_id).replace("'", "''")
    return (
        "SELECT p.patient_id, p.age, p.gender, p.village, p.family_history_malaria, p.recent_travel, "
        "e.endemic_zone, e.active_cases_this_week, e.breeding_site_risk, "
        "v.visit_date, v.fever_temp_c, v.body_pain, v.headache, v.nausea "
        "FROM patients p "
        "LEFT JOIN regional_epidemiology e ON p.village = e.village "
        "LEFT JOIN clinical_visits v ON p.patient_id = v.patient_id "
        f"WHERE p.patient_id = '{safe_id}' "
        "ORDER BY v.visit_date DESC LIMIT 1;"
    )


def run_sql(query: str) -> Union[List[Dict[str, Any]], Dict[str, str]]:
    """
    Executes a SQL query against Zetaris Federated Data Platform.
    
    1. Sends fresh UUID X-Request-ID and required Zetaris Auth & Org headers.
    2. Target: POST /sql-editor/sqls/run
    3. Returns list of row dicts or error message for self-correction.
    4. Includes local federated fallback to synthetic_data/ for offline/demo execution.
    """
    endpoint = f"{ZETARIS_BASE_URL}/sql-editor/sqls/run"
    request_id = str(uuid.uuid4())

    headers = {
        "Authorization": f"Bearer {ZETARIS_API_KEY}",
        "X-Org-ID": str(ZETARIS_ORG_ID),
        "X-Request-ID": request_id,
        "Content-Type": "application/json"
    }

    payload = {
        "sql": query
    }

    print(f"\n[Zetaris Tool] Executing SQL Query via Request-ID: {request_id}")
    print(f"[Zetaris Tool] Query: {query}")

    if not ZETARIS_API_KEY:
        logger.info("ZETARIS_API_KEY not set. Using local synthetic federation.")
        return _execute_local_synthetic_sql(query)

    try:
        if requests is not None:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, dict) and "data" in result:
                    return result["data"]
                elif isinstance(result, list):
                    return result
                return [result]
            else:
                logger.warning("Zetaris returned HTTP %s. Using local synthetic federation.", response.status_code)
                return _execute_local_synthetic_sql(query)
        else:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(endpoint, data=req_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if isinstance(result, dict) and "data" in result:
                    return result["data"]
                elif isinstance(result, list):
                    return result
                return [result]
    except Exception as e:
        logger.info("Zetaris endpoint unavailable (%s). Using local synthetic federation.", e)
        return _execute_local_synthetic_sql(query)


def _execute_local_synthetic_sql(query: str) -> Union[List[Dict[str, Any]], Dict[str, str]]:
    """
    Executes the SQL query against local synthetic SQLite tables (patients, clinical_visits, regional_epidemiology)
    to enable full end-to-end functionality even without a live remote Zetaris cluster.
    """
    try:
        # Load CSVs from synthetic_data/
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        synthetic_dir = os.path.join(base_dir, "synthetic_data")
        
        conn = sqlite3.connect(":memory:")
        
        # Ingest CSVs into temporary federated SQLite instance
        csv_files = {
            "patients": os.path.join(synthetic_dir, "patients.csv"),
            "clinical_visits": os.path.join(synthetic_dir, "clinical_visits.csv"),
            "regional_epidemiology": os.path.join(synthetic_dir, "regional_epidemiology.csv")
        }

        for table_name, csv_path in csv_files.items():
            if os.path.exists(csv_path):
                with open(csv_path, "r", encoding="utf-8", newline="") as f:
                    reader = csv.reader(f)
                    header = next(reader)
                    placeholders = ",".join(["?"] * len(header))
                    col_defs = ",".join([f'"{col}" TEXT' for col in header])
                    conn.execute(f'CREATE TABLE IF NOT EXISTS "{table_name}" ({col_defs});')
                    for row in reader:
                        # Empty cells (e.g. a temperature not measured) become NULL
                        values = [v if v != "" else None for v in row]
                        conn.execute(f'INSERT INTO "{table_name}" VALUES ({placeholders});', values)
            else:
                logger.warning("Missing synthetic table file: %s", csv_path)

        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        print(f"[Zetaris Local Federation] Query executed successfully. Retrieved {len(rows)} records:")
        for r in rows:
            print(f"  -> {r}")
        return rows

    except Exception as sql_err:
        error_msg = f"SQL Execution Error: {str(sql_err)}"
        print(f"[Zetaris Local Federation] {error_msg}")
        return {"error": error_msg}
