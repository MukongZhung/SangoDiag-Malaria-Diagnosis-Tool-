# AI Malaria Diagnosis Agent for Rural Cameroon

An autonomous, grounded clinical AI agent designed for frontline healthcare workers and community health posts in rural Cameroon. Combines **Zetaris Federated SQL Data**, **Meterless Nightshift (NVIDIA Nemotron)**, and **Meterless H-MEM Persistent Memory Engine** to deliver accurate, localized, WHO-compliant malaria diagnosis and treatment recommendations.

---

## 🏆 Hackathon Alignment & Track Compliance

| Layer / Track | Technology | Implementation & Role |
| :--- | :--- | :--- |
| **Track 1: Fragmented Data (Data Layer)** | **Zetaris** | Dynamically federates distributed S3 patient records (`patients.csv`, `clinical_visits.csv`) and regional disease surveillance (`regional_epidemiology.csv`) using zero-ETL REST API SQL (`run_sql`). |
| **Track 2: Grounded Reasoning (Power Layer)** | **Meterless Nightshift** | Routes reasoning to **`nvidia/nemotron-3.5-lightning-30b-a3b`** for rapid SQL generation and **`nvidia/nemotron-3-super-120b-a12b`** for clinical diagnosis and dosage calculation. |
| **Build Rule (Engine Layer)** | **Meterless H-MEM** | Implemented in `agent/engine_h_mem.py`. Provides persistent, zero-loss longitudinal clinical memory across consultations using local SQLite (`h_mem.db`). Verified via `tests/test_engine.py`. |

---

## 🏗️ Architecture Overview

```text
       Frontline Healthcare Worker / Android Field App
                              │
                    [ Presenting Case ]
         (Patient ID, Symptoms, RDT / Microscopy Result)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      THE AGENT LOOP                         │
│                      (agent/main.py)                        │
├─────────────────────────────────────────────────────────────┤
│  1. Memory Recall (H-MEM)   ──► Retrieves prior sessions   │
│                                 from agent/engine_h_mem.py  │
│                                                             │
│  2. Reasoning & Tool Call   ──► Meterless Nightshift        │
│                                 nvidia/nemotron-3.5-lightning│
│                                                             │
│  3. Data Layer Execution    ──► Zetaris SQL REST API        │
│                                 agent/tools_zetaris.py      │
│                                 (Cross-joins S3 & local db) │
│                                                             │
│  4. Grounded Synthesis      ──► Meterless Nightshift        │
│                                 nvidia/nemotron-3-super     │
│                                                             │
│  5. Memory Update (H-MEM)   ──► Appends consultation note   │
│                                 into persistent h_mem.db    │
└─────────────────────────────────────────────────────────────┘
```

---

## 📂 Repository Structure

```text
├── agent/
│   ├── __init__.py
│   ├── llm.py            # Power Layer: Meterless Nightshift API client (NVIDIA Nemotron)
│   ├── tools_zetaris.py  # Data Layer: Zetaris REST SQL tool with UUID Request IDs
│   ├── engine_h_mem.py   # Build Layer: H-MEM Persistent Memory Engine (SQLite)
│   └── main.py           # Orchestration Agent Loop with tool calling
├── synthetic_data/
│   ├── patients.csv              # Patient demographic & family history
│   ├── clinical_visits.csv       # Clinical vitals (temp, body pain)
│   └── regional_epidemiology.csv # Endemicity zones (Buea, Limbe, Douala, Yaoundé, etc.)
├── tests/
│   ├── __init__.py
│   └── test_engine.py    # Pytest suite verifying H-MEM persistence
├── app/                  # Companion Native Android Field Diagnostic Station (Compose)
├── requirements.txt      # Python dependencies
├── .env.example          # Template environment configurations
└── README.md             # Project documentation
```

---

## 🚀 How to Run in 5 Minutes

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/YOUR_USERNAME/malaria-agent.git
cd malaria-agent
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and set your credentials:
```bash
cp .env.example .env
```
Key variables:
- `METERLESS_BASE_URL`: e.g. `https://runtime.meterless.ai/v1`
- `METERLESS_RUNTIME_TOKEN`: Your Meterless runtime bearer token
- `METERLESS_MODEL`: `nvidia/nemotron-3.5-lightning-30b-a3b`
- `ZETARIS_API_KEY`: Your Zetaris API key
- `ZETARIS_ORG_ID`: `1`
- `ZETARIS_BASE_URL`: `http://localhost:8888/api/v1.0`

*(Note: The system contains an autonomous local high-fidelity fallback, so it runs completely out of the box even without live external credentials!)*

### 3. Run the Clinical Agent Simulation
```bash
python agent/main.py
```

### 4. Run the Engine Verification Test
```bash
pytest tests/test_engine.py
```

---

## 🔬 Clinical Protocol Grounding

The agent references official Cameroon Ministry of Public Health (MINSANTE) guidelines:
1. **Uncomplicated *P. falciparum*:** Artemether 20mg / Lumefantrine 120mg (Coartem) standard 6-dose weight-adjusted regimen taken with milk or fatty meal.
2. **Supportive Care:** Paracetamol 1g PO QDS for temperature > 38.5°C; oral rehydration salts (ORS).
3. **Severe Malaria Triage:** Patients exhibiting prostration, persistent emesis, impaired consciousness, or respiratory distress are flagged for emergency parenteral Artesunate transfer to regional referral hospitals (e.g. Buea or Limbe Regional Hospital).

---

## 🔒 Security & Privacy

- Zero hardcoded API keys; all sensitive tokens are loaded from `os.environ`.
- Every Zetaris request includes a fresh UUID `X-Request-ID` and scoped headers.
- H-MEM engine isolates clinical memory locally within device boundary for privacy.
