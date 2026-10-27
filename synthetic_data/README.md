# Synthetic data

Everything in this folder is invented for the demo. None of it describes a real patient.

| File | Rows | What it holds |
|---|---|---|
| `patients.csv` | 6 | patient id, village, family history of malaria |
| `clinical_visits.csv` | 6 | one earlier visit per patient: temperature, body pain |
| `regional_epidemiology.csv` | 6 | village, endemic zone (High / Medium / Low), active cases |

The villages are real towns in Cameroon (Buea, Limbe, Douala, Yaoundé, Bamenda, Kumba), but the zone labels and case counts are illustrative, not surveillance figures.

## How it reaches the agent

- **Live:** the three files sit in an S3 bucket that Zetaris can reach and are registered there as tables. Set `ZETARIS_TABLE_*` in `.env` to the names they were registered under.
- **Local copy:** with "Local copy of the CSV files" selected (UI) or `--local-data` (CLI), `agent/tools_zetaris.py` loads the same files into an in-memory SQLite under the same table names, so the same SQL runs. Results from this mode are labelled `local-replica` everywhere.

## Licence

The synthetic files are released with the project. The optional smear images (BBBC041, Broad Bioimage Benchmark Collection) are **not** included here; they are CC BY-NC-SA 3.0, see the main README.
