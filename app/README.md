# app: the Cala pull

Pulls European seed and Series A rounds from the last 3 years from [Cala](https://docs.cala.ai) and caches every
successful reply under `data/cache/`. `scripts/seed_db.py`, `leadline/build_cases.py` and `tests/live/test_cala.py`
read that cache (`ingest.build_dataset.QUERIES` and `ingest.cala_client.CalaClient`), so the Leadline DB can be rebuilt
without new Cala calls. `ingest.build_dataset` itself reads the cache only when `CALA_API_KEY` is set; without it, it
writes the sample dataset.

## Run it

From `app/`, with a Python environment that has `requirements.txt` installed:

```bash
pip install -r requirements.txt
python -m ingest.build_dataset            # data/dataset.json; falls back to sample data without a key
python -m ingest.build_dataset --strict   # exit 1 instead of falling back
python -m ingest.check_live --n 5         # live Cala rows, and whether any names a round lead
python -m pytest -q tests
```

The code loads the nearest `.env` from the app folder up through the workspace root (`envload.py`). Values already
set in the shell win. A missing `.env` is fine; without `CALA_API_KEY` the builder uses sample data.

## Layout

- `ingest/` — thin Cala client (caches every response under `data/cache/`), the dataset builder and `check_live`.
- `envload.py` — the `.env` loader.
- `contracts/` — `match_result.schema.json`, `venus_request.example.json` (read by
  `leadline/tests/test_match_plugin.py`) and `training_cases.json`.
- `fixtures/` — mock match results for both directions (the source of `contracts/training_cases.json`).
- `tests/` — tests for the Cala client, the dataset builder and `envload`.
- `data/` — generated and not committed: `dataset.json`, `dataset.meta.json`, Cala `cache/`.

## Data formats

Top-level dataset: `{"schema_version": "1.0", "companies": [...], "investors": [...],
"rounds": [...], "people": []}`. Unknown facts are `null` or omitted, never guessed. Money always
carries a currency. Cala IDs are kept verbatim.

The builder writes `data/dataset.meta.json` with the source (`cala` or `sample`),
build time, reason, and record counts.

## What we found in Cala (checked 2026-11-13)

- Endpoints: `POST /v1/knowledge/query` with `X-API-KEY` auth (no Bearer),
  `GET /v1/entities?name=...&limit=...` (limit 1–100), and
  `POST /v1/entities/{uuid}` (optional `properties` and `relationships` body).
- Cala is an entity graph, not a deals database: there is **no dedicated round
  entity and no native lead-investor field**. Whether a fund led a round only
  appears inside natural-language answers when it appears at all.
- Consequence: `round.investors[].role` is set from explicit mentions only and
  falls back to `"unknown"`. The matching logic must treat "unknown" leads
  carefully, not as participants.
- Response row shapes vary with the question asked; the ingestion mapping is
  defensive (missing field → `null`).

## Secrets

Put credentials only in the root `.env`, copied from `../.env.example`. Keep
`.env` out of source control. This folder reads `CALA_API_KEY`. Keep credentials
out of code, the frontend, logs, and test fixtures.
