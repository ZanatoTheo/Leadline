# Leadline (junction-26/app)

Find investors who actually **lead** rounds like yours — and are still investing today.
Also runs the other way: a fund finds startups that fit how it leads deals.

Built on [Cala](https://docs.cala.ai). Matching is delegated to the Venus engine
through a `cala-leads` plugin; until that plugin exists, a mock (`VENUS_MODE=mock`)
serves fixture results so the whole product works end to end.

## Run it

```bash
cd app
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp ../.env.example ../.env   # optional: needed for live services
.venv/bin/python -m ingest.build_dataset
.venv/bin/uvicorn api.main:app --reload
```

Open http://127.0.0.1:8000. Tests: `.venv/bin/python -m pytest -q`.

The app loads the nearest `.env` from the app folder up through the workspace
root. Values already set in the shell win. A missing `.env` is fine; mock mode
works without API keys.

## Layout

- `ingest/` — thin Cala client (caches every response under `data/cache/`) and the
  dataset builder.
- `api/` — FastAPI app; `venus_adapter.py` is the only place that talks to Venus.
- `web/` — plain HTML/CSS/JS UI, no build step.
- `fixtures/` — mock Venus responses for both directions.
- `tests/` — smoke tests (API starts, `/api/match` returns valid JSON, CSV export).
- `data/` — generated: `dataset.json`, Cala `cache/`, past match `runs/`.

## API

- `GET /health`
  — includes `venus_mode` and `dataset_source` (`cala`, `sample`, or `unknown`).
- `GET /api/companies?q=`, `GET /api/investors?q=` — search for the subject picker.
- `POST /api/match` — match request → match result (see "Data formats" below).
  Venus errors map to 4xx/5xx with `{code, message, path}`.
- `GET /api/export.csv?run_id=` — one row per match.

## Data formats

Top-level dataset: `{"schema_version": "1.0", "companies": [...], "investors": [...],
"rounds": [...], "people": []}`. Field names are the agreed contract with Venus —
don't change them. Unknown facts are `null` or omitted, never guessed. Money always
carries a currency. Cala IDs are kept verbatim.

The builder writes `data/dataset.meta.json` with the source (`cala` or `sample`),
build time, reason, and record counts. `GET /health` reports that source; it
returns `unknown` when the metadata file is missing or invalid. Run
`.venv/bin/python -m ingest.build_dataset --strict` when a Cala dataset is
required. Without `--strict`, the builder warns and falls back to sample data if
Cala cannot be used. To inspect live Cala rows and whether any mentions a lead,
run `.venv/bin/python -m ingest.check_live --n 5`.

## What we found in Cala (checked 2026-11-13)

- Endpoints: `POST /v1/knowledge/query` with `X-API-KEY` auth (no Bearer),
  `GET /v1/entities?name=...&limit=...` (limit 1–100), and
  `POST /v1/entities/{uuid}` (optional `properties` and `relationships` body).
- Cala is an entity graph, not a deals database: there is **no dedicated round
  entity and no native lead-investor field**. Whether a fund led a round only
  appears inside natural-language answers when it appears at all.
- Consequence: `round.investors[].role` is set from explicit mentions only and
  falls back to `"unknown"`. The matching logic (Venus plugin) must treat
  "unknown" leads carefully, not as participants.
- Response row shapes vary with the question asked; the ingestion mapping is
  defensive (missing field → `null`) and must be re-checked when the real key
  is available.

## Venus integration

- Switch: `VENUS_MODE=mock|live` in `.env`. Mock is the default.
- Live mode builds one `venus.Venus(plugins_dir, strategies_dir)` from the
  sibling `../venus` repo (overridable with `VENUS_DIR`, `VENUS_PLUGINS_DIR`,
  `VENUS_STRATEGIES_DIR`; no packaging step needed) and sends
  `{"venus_version": "1", "plugin": "cala-leads", "mode": "run",
  "strategy": "cala-leads-default", "input": {"dataset": ..., "request": ...}}`
  to `.handle()`. The match result is unwrapped from `outputs[0].output`;
  Venus warnings are merged into the result's `warnings`.
- Live mode also needs Venus's own requirements installed
  (`pip install -r ../venus/requirements.txt` — openai, jsonschema).
- Venus errors map to HTTP: `plugin_not_found`/`strategy_not_found` → 404,
  model/budget/timeout upstream errors → 502/503/504, everything else → 400.

### Contract for the `cala-leads` plugin (to be built in `venus/plugins/`)

Everything the plugin author needs is in `contracts/`:

- `match_result.schema.json` — the plugin's **output schema** (the match result
  the UI renders). Put a copy in the plugin dir as `output.schema.json`.
- `venus_request.example.json` — the envelope and `input` shape
  (`{dataset, request}`). The plugin's `input.schema.json` should require both.
- `training_cases.json` — two training cases (one per direction) built from the
  fixtures, with `expected` as must-match / must-reject / top-match assertions
  for the plugin's checker.

The plugin must also ship a **validated strategy** file
(`venus/strategies/cala-leads-default.json`, `status: "validated"`, plugin name
and version matching the manifest) or run mode is refused with
`strategy_not_validated`. Venus loads plugins by directory name under
`plugins/`, so the manifest `name` must be exactly `cala-leads`.

## Secrets

Put credentials only in the root `.env`, copied from `../.env.example`. Keep
`.env` out of source control. The app reads `CALA_API_KEY`; Venus uses
`CONTEXT_DEV_API_KEY` for web tools and the selected provider's model key
(`VERDA_API_KEY` or `NVIDIA_API_KEY`). Keep credentials out of code, the
frontend, logs, and test fixtures.

The model provider and model are a user choice. Set them in the validated Venus
strategy and configure its matching key; the example files do not choose one.
