# SangoDiag: malaria triage support for nurses in rural Cameroon

In many rural health posts in Cameroon there is a nurse but no doctor, lab results can take days, and rapid tests are not always in stock. SangoDiag gives that nurse a second opinion in about a minute. It reads the patient's record and the village's malaria situation from **Zetaris**, remembers earlier visits with the **Meterless H-MEM** engine, reasons with **NVIDIA Nemotron through Meterless Nightshift**, and returns one next step: test, treat per protocol, send to the lab, look for another cause, or refer. It shows every query and every model call behind that step.

It supports the nurse's decision. It does not diagnose, prescribe doses, or replace a test.

**Open Agent Hackathon 2026.** Main track: 01, Solving Fragmented Intelligence. The answer is built from four separate sources: the patient register, past visits, district surveillance and the nurse's own observations, with an optional smear image. It also fits track 02, because every claim cites the query that produced it.

---

## What the nurse sees

1. She picks the patient, enters temperature, symptoms and danger signs, and the RDT result if there is one. She can add a smear photo.
2. A **memory banner** says whether SangoDiag remembers this patient, and what it remembers.
3. A **decision card** gives the next step, with a malaria likelihood score and a confidence level. When the evidence is thin it says so (abstention).
4. A short explanation written by Nemotron, with sources in brackets: `[Q1]` is a Zetaris query, `[MEM]` is the patient's history, `[NURSE]` is what she entered.
5. **How SangoDiag got here** lists every step: which Nightshift lane ran, which model answered, how long it took, each SQL statement with the rows it returned, and each time the critic sent work back.

She can mark an earlier recommendation as right or wrong. H-MEM adjusts its trust in that record and logs the change.

## The agent loop

```
 nurse intake ──► H-MEM recall ──► PLANNER (Nemotron, fast lane) ──run_sql──► Zetaris
                                        ▲                                       │
                                        └──── CRITIC: evidence complete? ◄──────┘
                                                     │ yes
                                                     ▼
                                    triage RULES (transparent, no LLM)
                                                     │
                                                     ▼
                         REPORTER (Nemotron, deep lane) ◄── CRITIC: citations real?
                                                     │      no doses? test before treat?
                                                     ▼
                                     H-MEM stores today's visit
```

| Step | What happens | Code |
|---|---|---|
| Recall | H-MEM ranks this patient's memories with the canonical formula and injects a `[MEMORY CONTEXT]` block | `agent/engine_h_mem.py` |
| Plan | Nemotron 3.5 Lightning (fast lane) decides which facts it needs and writes the SQL as `run_sql` tool calls | `agent/agent.py` `_plan_round` |
| Execute | Each statement goes to Zetaris over REST; SQL errors go back to the planner so it can fix them | `agent/tools_zetaris.py` |
| Critique 1 | Is the village, the endemic zone and the visit history there? If not, the planner gets the critique and revises (1 round). Still missing: a baseline query, labelled as written by code | `agent/agent.py` `_coverage` |
| Decide | Rules turn the evidence into one next step. Test before treat; any danger sign means referral; fever within 28 days of a treated episode (from H-MEM) means possible treatment failure | `agent/triage.py` |
| Report | Nemotron 3 Super (deep lane) explains the decision for the nurse | `agent/agent.py` `_reporter_system` |
| Critique 2 | Rejects drafts that cite queries that don't exist, give doses, suggest antimalarials before a positive test, or forget to say "refer". The reporter rewrites, up to 2 rounds; after that the rules' own summary is shown instead | `agent/agent.py` `critique_report` |
| Remember | H-MEM stores the nurse's observation (confidence 0.9) and the recommendation (0.6), scoped to this patient | `agent/engine_h_mem.py` |

Every run writes a JSONL trace to `logs/run-<id>.jsonl`.

## How we built it

| Layer | Technology | Where |
|---|---|---|
| Power | **Meterless Nightshift** is the only AI provider: OpenAI-compatible `POST /v1/chat/completions` at `http://127.0.0.1:8088/v1`, `Authorization: Bearer <runtime token>`, `meterless-app: sangodiag`, `meterless-scope: user`, `meterless-ttfb-ms: 240000`. Status comes from `GET /v1/models` (401/403 shows as "token rejected", not "offline") | `agent/llm.py` |
| Models | **NVIDIA Nemotron** as two Nightshift lanes: `nvidia/nemotron-3.5-lightning-30b-a3b` (fast lane, planner and SQL) and a large Nemotron on the deep lane (reporter): `nvidia/nemotron-3-super-120b-a12b` by default, `nvidia/nemotron-3-ultra-550b-a55b` in our recorded runs because our NVIDIA key is not served the Super model (set with `METERLESS_MODEL_DEEP`). The model id Nightshift reports is logged for every call. The NVIDIA key lives only in Nightshift, under Setup > Providers | `agent/llm.py` |
| Build | **Meterless H-MEM**: a Python port of the official reference (tiered records, hybrid ranking, trust ledger, feedback deltas, conflict gate, sleep cycle, dreaming with approval) that passes the official conformance vectors. Stored in a local SQLite file whose audit ledger rejects updates and deletes | `agent/hmem/core.py`, `agent/engine_h_mem.py` |
| Data | **Zetaris** REST: `POST /sql-editor/sqls/run` with a bearer key, `X-Org-ID: 1`, a fresh `X-Request-ID` UUID per request, and body `{queryId, sql, source: "SqlEditor", limit}`. One read-only statement per call, enforced before sending | `agent/tools_zetaris.py` |
| Vision | Smear model served as an HTTP endpoint (`VISION_ENDPOINT_URL`). A local blur and exposure check runs first. The image model can raise suspicion but never confirms malaria on its own | `agent/tools_vision.py` |
| UI | Streamlit nurse screen | `app.py` |
| Coding tools | Cursor, Google AI Studio, Claude Code | |

### Proof that the engine works

```bash
pytest tests/test_engine_conformance.py -v   # official H-MEM vectors: 13/13, plus persistence, append-only ledger, patient isolation
pytest tests/ -v                              # 53 tests: provider contract, Zetaris request shape, rules, critic, full loop
```

The conformance vectors are copied unchanged from `Meterless/engines/hmem/conformance/vectors/vectors.json`. `tests/test_engine_conformance.py` mirrors the official TypeScript runner, check by check. Our embedder gives the same vectors as the reference, number for number.

The feature the engine powers can be seen in demo case 5. An Ebolowa patient treated for malaria comes back with fever. Only H-MEM knows about the earlier treatment, and that memory changes the decision from "do an RDT" to "send for microscopy: possible treatment failure". This is tested in `tests/test_agent.py::test_hmem_changes_the_next_decision`.

## Run it

**Requirements:** Python 3.10+. For live runs you also need Meterless Nightshift with a Nemotron lane, and the Zetaris local platform (Docker, 8 GB RAM, 4 CPUs).

```bash
pip install -r requirements.txt
cp .env.example .env          # add METERLESS_RUNTIME_TOKEN and ZETARIS_API_KEY
python -m agent.main --status # Nightshift: online, both lanes listed; Zetaris: online
streamlit run app.py          # the nurse UI
```

Command line, same agent:

```bash
python -m agent.main --case all                       # live Nightshift + live Zetaris
python -m agent.main --case all --local-data          # live Nightshift, CSV copy instead of Zetaris
python -m agent.main --case all --offline --local-data   # rehearsal, no keys needed
```

**Five-minute judge path without keys:** `pip install -r requirements.txt && python -m agent.main --case all --offline --local-data && pytest tests/`. Setting `SAMPLE_MODE=true` in `.env` does the same for the CLI, the Streamlit UI and the REST API. Rehearsal mode runs the real loop, rules, critic and H-MEM with a scripted stand-in for the model. Every call it makes is labelled `offline-simulator`, never Nemotron.

### Demo cases (`examples/demo_cases.json`)

| Case | Patient | Expected next step |
|---|---|---|
| 1. Clear malaria | Ebolowa, 39.1 C, RDT positive | Treat per national protocol |
| 2. Suspected, untested | Buea, 38.9 C, no test | Do an RDT now |
| 3. Probably not malaria | Bafoussam, cough, RDT negative | Look for another cause |
| 4. Danger signs | Garoua, child of 3, vomits everything, drowsy | Refer urgently |
| 5. Fever is back | Ebolowa again, after case 1 | Send for microscopy (H-MEM) |

### Zetaris setup (data layer)

Follow the hackathon's Start Here lesson (`./preflight.sh`, `docker compose up -d`, `./verify.sh`). Copy the three CSVs into the platform's shared file area, then register them from the SQL Workspace:

```bash
docker compose exec driver mkdir -p /home/zetaris/customer-data/shared/sangodiag
for f in patients clinical_visits regional_epidemiology; do
  docker compose cp synthetic_data/$f.csv driver:/home/zetaris/customer-data/shared/sangodiag/$f.csv
done
```

```sql
CREATE LIGHTNING DATABASE SANGODIAG DESCRIBE BY "SangoDiag malaria data" OPTIONS ()
CREATE LIGHTNING FILESTORE TABLE patients FROM SANGODIAG FORMAT csv OPTIONS (path "file:///home/zetaris/customer-data/shared/sangodiag/patients.csv", header "true")
-- same for clinical_visits and regional_epidemiology
```

Then set `ZETARIS_TABLE_*` in `.env` to `SANGODIAG.patients`, `SANGODIAG.clinical_visits` and `SANGODIAG.regional_epidemiology`, and paste an API key into `ZETARIS_API_KEY`. See `synthetic_data/README.md`.

## Honest limits

- **Synthetic data only.** Patients, visits and zone labels are invented. No real patient data is used.
- **The smear model is a proxy.** It is trained on BBBC041, which is mostly *P. vivax* smears from Brazil and Southeast Asia. Cameroon is mostly *P. falciparum*, and stains, microscopes and phone cameras differ. That is domain shift, and the model must be revalidated on local smears before anyone relies on it. That is why it can only ask for confirmation.
- **The rules are a demo protocol.** They follow WHO's test-before-treat principle and common danger signs, but they have not been clinically validated. Doses are left to the national protocol chart.
- **BBBC041 licence:** CC BY-NC-SA 3.0. Non-commercial use with attribution ("We used image set BBBC041v1, available from the Broad Bioimage Benchmark Collection [Ljosa et al., Nature Methods, 2012]"). Commercial deployment would need other data or permission.
- **Android app** (`app/`): a Compose field prototype. With *Autonomous Field Engine* off in Settings it calls the same agent through `agent/api.py` (`python -m uvicorn agent.api:app --host 0.0.0.0 --port 8000 --ws none`; emulator URL `http://10.0.2.2:8000/`); otherwise, or if the backend is unreachable, it runs an on-device simulation and says so. The main demo is the Streamlit UI.

## Repository

```
agent/
  agent.py           planner / executor / critic / reporter loop, traces
  llm.py             Meterless Nightshift client (fast + deep lanes)
  tools_zetaris.py   run_sql over Zetaris REST, read-only guard, local replica
  tools_vision.py    smear endpoint client + image quality check
  triage.py          transparent triage rules
  engine_h_mem.py    H-MEM wired into the clinical workflow
  hmem/core.py       Meterless H-MEM engine (Python port of the reference)
  main.py            command line
  api.py             REST API for the Android app (same run_case)
app.py               Streamlit nurse UI
examples/            demo cases
synthetic_data/      CSVs for Zetaris (+ README)
tests/               conformance vectors, engine, agent tests
app/                 Android design prototype
```

## Team

| Name | Role |
|---|---|
| Mukong Peter Zhung | Problem owner, field context, pitch |
| Yosr Takouti | Nightshift power layer, H-MEM engine, agent loop, nurse UI |
| Tiomela Zangue Jorel | Zetaris data layer and dataset, REST API and Android integration, demo video, submission |
| Joram Kirubi | Team member |
| Roniald Nchare | Team member |

## References

- Meterless: [Nightshift provider contract](https://github.com/Meterless/Meterless/blob/main/docs/agent-ready/add-meterless-provider.md), [H-MEM spec and conformance suite](https://github.com/Meterless/Meterless/tree/main/engines/hmem) (Apache-2.0, see `NOTICE`)
- WHO, [Malaria fact sheet](https://www.who.int/news-room/fact-sheets/detail/malaria): confirm every suspected case with a parasite test
- Broad Institute, [BBBC041 malaria smear images](https://bbbc.broadinstitute.org/BBBC041)
