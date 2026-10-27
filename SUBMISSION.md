# SangoDiag: malaria triage support for nurses in rural Cameroon

**Track:** Solving Fragmented Intelligence

## Problem
In many rural health posts in Cameroon, a nurse works alone: no doctor, lab results that take days, rapid tests not always in stock. Deciding whether a feverish patient needs a test, treatment, the lab or an urgent referral means pulling together facts scattered across a patient register, past visits, district malaria surveillance and what the nurse sees at the bedside.

## What SangoDiag does
SangoDiag gives that nurse a second opinion in about a minute. The nurse enters temperature, symptoms, danger signs and the RDT result. The agent gathers the evidence, decides on ONE next step (do an RDT, treat per national protocol, send to the lab, look for another cause, or refer urgently) and explains why, citing every source. It never gives drug doses and never recommends an antimalarial before a positive test.

## How the agents work together
- **Planner** (Nemotron 3.5 Lightning, fast lane) decides which facts it needs and writes the SQL itself as tool calls.
- **Executor** runs each read-only query on the data layer; SQL errors go back to the planner so it can fix them.
- **Critic** checks the evidence (village, endemic zone, visit history). If something is missing, the planner revises its plan.
- **Triage rules** turn the evidence into one transparent decision with a likelihood score, so the language model never decides alone.
- **Reporter** (Nemotron 3 Ultra, deep lane) explains the decision for the nurse, citing each query.
- **Critic** rejects reports that cite non-existent queries, give doses, suggest treatment before a test or forget to say "refer"; the reporter rewrites, up to two rounds.
- **H-MEM** recalls the patient's earlier visits and stores today's one. In demo case 5, only memory knows the patient was treated days ago, which changes the decision from "do an RDT" to "send for microscopy: possible treatment failure".

Every run writes a trace (logs/run-<id>.jsonl) showing each query, each model call, which model answered and how long it took.

## Sponsor technology
- **Zetaris (data layer):** patients, visits and district epidemiology are three separate sources registered as tables and queried through the Zetaris REST API (`POST /sql-editor/sqls/run`, bearer key, org header, a fresh request ID per call, read-only guard). The demo runs against a live Zetaris platform (the hackathon Docker Compose stack), where the three CSVs are registered as `SANGODIAG.patients`, `SANGODIAG.clinical_visits` and `SANGODIAG.regional_epidemiology` Lightning filestore tables. A local CSV replica is kept only for keyless rehearsal.
- **Meterless H-MEM (engine):** a Python port of the reference engine (tiered memory, hybrid ranking, trust ledger, feedback, append-only audit). It passes the official conformance vectors (13/13) plus persistence and patient-isolation tests.
- **Meterless Nightshift (AI provider):** every model call goes through Nightshift's OpenAI-compatible endpoint, with two NVIDIA Nemotron lanes. The model id Nightshift reports is logged for each call.
- **NVIDIA Nemotron:** nemotron-3.5-lightning-30b-a3b for planning and SQL, nemotron-3-ultra-550b-a55b for the nurse-facing explanation (the deep-lane model is configurable).

## Try it without keys
`pip install -r requirements.txt && python -m agent.main --case all --offline --local-data && pytest tests/` runs the full loop, rules, critics and H-MEM on 5 demo cases with a clearly labelled offline simulator (56 tests pass). `streamlit run app.py` opens the nurse screen. An Android field app calls the same agent through a small REST API.

## Honest limits
Synthetic data only. The triage rules are a demo protocol, not clinically validated. The optional smear-image model is a proxy trained on non-Cameroonian data and can only ask for confirmation, never confirm.

## Team
Mukong Peter Zhung, Yosr Takouti, Tiomela Zangue Jorel, Joram Kirubi, Roniald Nchare.
