# SangoDiag: submission form

## Project

| Field | Value |
|---|---|
| Project name | SangoDiag |
| One-line pitch | A second opinion on malaria for the nurse who works alone in a rural Cameroonian health post. |
| Track | Solving Fragmented Intelligence |
| Team | Biotek-Nexus CM: Mukong Peter Zhung, Yosr Takouti, Tiomela Zangue Jorel, Joram Kirubi, Roniald Nchare Njutap |
| Repository | https://github.com/MukongZhung/SangoDiag-Malaria-Diagnosis-Tool- |
| Demo video | SangoDiag_demo_v2.mp4 (3 min 08, 1080p) |
| Slide deck | SangoDiag_deck.pdf / SangoDiag_deck.pptx (14 slides) |

## Description

**Problem.** In many rural health posts in Cameroon, a nurse works alone: no doctor, lab results that take days, rapid tests not always in stock. Deciding whether a feverish patient needs a test, treatment, the lab or an urgent referral means pulling together facts scattered across a patient register, past visits, district malaria surveillance and what the nurse sees at the bedside.

**What SangoDiag does.** The nurse enters temperature, symptoms, danger signs and the test result. The agent gathers the evidence, decides on ONE next step (do a rapid test, treat per national protocol, send to the lab, look for another cause, or refer urgently) and explains why, citing every source. It never gives drug doses and never recommends an antimalarial before a positive test.

**How the agents work together.**

- **Planner** (Nemotron 3.5 Lightning, fast lane) decides which facts it needs and writes the SQL itself as tool calls.
- **Executor** runs each read-only query on Zetaris; SQL errors go back to the planner so it can fix them.
- **Critic** checks the evidence (village, endemic zone, visit history). If something is missing, the planner revises its plan.
- **Triage rules** turn the evidence into one transparent decision with a likelihood score, so the language model never decides alone.
- **Reporter** (Nemotron 3 Ultra, deep lane) explains the decision for the nurse, citing each query.
- **Critic** rejects reports that cite non-existent queries, give doses, suggest treatment before a test or forget to say "refer"; the reporter rewrites, up to two rounds.
- **H-MEM** recalls the patient's earlier visits and stores today's one. In demo case 5, only memory knows the patient was treated days ago, which changes the decision from "do a rapid test" to "send for microscopy: possible treatment failure".

Every run writes a trace (`logs/run-<id>.jsonl`) with each query, each model call, which model answered and how long it took.

## Sponsor technology explanation

- **Zetaris (data layer).** Patients, clinical visits and district epidemiology are three sources registered on a local Zetaris platform (Docker) as one Lightning database, `SANGODIAG.patients`, `SANGODIAG.clinical_visits` and `SANGODIAG.regional_epidemiology`. The agent queries them through the Zetaris REST API (`POST /sql-editor/sqls/run`, bearer key, org header, a fresh request ID per call, read-only guard). Every query is shown to the nurse and cited as [Q1], [Q2]…
- **Meterless Engine: H-MEM.** A Python port of the reference engine (tiered memory, hybrid ranking, trust ledger, feedback, append-only audit). It powers the follow-up feature: a remembered treatment changes the advice when fever returns. The nurse can mark a memory right or wrong and H-MEM adjusts its trust. Test: it passes the 13 official conformance vectors, plus persistence and patient-isolation tests (`pytest tests/`, 56 tests pass).
- **Meterless Nightshift (primary AI provider).** Every model call goes to Nightshift's OpenAI-compatible endpoint (`http://127.0.0.1:8088/v1`) with `meterless-app` and `meterless-scope` headers and the runtime token from `.env`. The app shows Nightshift's status and lanes, and logs the model Nightshift reports for each call. The NVIDIA key lives in Nightshift's Providers tab, not in the project.
- **NVIDIA Nemotron (through Nightshift).** `nvidia/nemotron-3.5-lightning-30b-a3b` plans and writes SQL with tool calls; `nvidia/nemotron-3-ultra-550b-a55b` writes the nurse-facing explanation. Routes are pinned, so the logs prove which Nemotron model answered.
- **What is unique.** The model writes the queries over Zetaris; transparent rules make the decision; and memory changes care: H-MEM is used as clinical memory, not chat history.

## Run it

- With keys: `cp .env.example .env`, add the Nightshift token and the Zetaris API key, then `python -m agent.main --status` and `streamlit run app.py`.
- Without keys: `SAMPLE_MODE=true` (or `python -m agent.main --case all --offline --local-data`) runs the whole loop on the local CSV copy with a clearly labelled stand-in model. `pytest tests/` runs 56 tests.

## Pre-existing components to declare

- The patient, visit and epidemiology CSV files come from the hackathon's data pack (synthetic data).
- H-MEM is ported from Meterless' open-source reference specification and uses its official conformance vectors (Apache-2.0, see `NOTICE`).
- Optional smear-image model: trained on the public BBBC041 dataset (CC BY-NC-SA 3.0); the images are not included in the repository.
- All project code was written during the build window (first commit 25 October 2026).

## AI and coding tools

Coding tools: Cursor, Google AI Studio, Claude Code. AI-assisted code was reviewed and tested by the team. The product's own AI calls all go through Meterless Nightshift.

## Honest limits

Synthetic data only. The triage rules are a demo protocol, not clinically validated. The optional smear-image model was trained on non-Cameroonian data and can only ask for confirmation, never confirm. Speed depends on Nightshift and the provider's latency.
