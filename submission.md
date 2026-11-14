# Leadline: preliminary submission (Junction 2026)

DRAFT by John, 2026-11-13. The owner edits the final text. Statements below match the repo at the time of writing.

## What it is
Leadline finds investors who actually **lead** rounds like yours and are still investing. It also runs the other way: a
fund finds startups that fit how it leads deals. The matching is done by **Venus**, a general-purpose engine that runs
a base model shaped by behavioral tendencies for any task a plugin defines. Leadline is Venus's first task
(`cala-leads` plugin).

## What works now (checked by running it)
- Web app (`app/`): two tabs (startup to investors, investor to startups), search picker, filters, ranked result cards
  with score, lead badge, reasons with sources, "why not these" panel, CSV export, light/dark and phone layout.
- A badge shows where the data comes from (Cala data or sample data), and a strip shows warnings. Live-mode errors
  show a plain message and a "switch to mock" hint.
- Cala ingestion matches Cala's documented API (`X-API-KEY`, `{"input": ...}`, `results`, entity search, entity by
  id). Without a key it writes the sample dataset, warns loudly and records the reason in `data/dataset.meta.json`;
  `--strict` fails instead.
- `.env` is loaded from the app folder up to the workspace root; values set in the shell win.
- Venus engine (`venus/`): plugin and strategy contract, training and run modes, model client with retries and a
  budget, Context.dev web tools, HTTP and in-process serving. 111 tests pass with no network.
- `app` tests: 46 pass with no network.

## What is mock (be honest in the demo)
- Matching results in the demo are **fixtures** (`VENUS_MODE=mock`, shown with a "mock" badge). The `cala-leads`
  plugin and its validated strategy are not finished, so live matching does not run yet.
- Cala ingestion has **not** been run with a real key. The data on screen is the built-in sample dataset.
- No model call has been made against Verda or NVIDIA yet. Verda's docs list no Nemotron or Gemma models, so the
  model choice (NVIDIA Build for Nemotron and Gemma, or Verda's `kimi-k3-1-pro`) is still open.
- Cala has no round entity and no lead-investor field. A lead is recorded only when a row says so; otherwise the
  role is `unknown`.

## Sponsor tech
Cala (data), Context.dev (web search, scrape and news tools inside Venus), Verda and NVIDIA (model providers, keys
pending), FastAPI (serving).

## Demo steps (mock mode, no keys)
1. `cd app && python -m venv .venv && .venv/bin/pip install -r requirements.txt`
2. `.venv/bin/python -m ingest.build_dataset` (warns that it uses the sample dataset)
3. `.venv/bin/uvicorn api.main:app` and open http://127.0.0.1:8000
4. Pick a startup, run a match, open a card's reasons and sources, export the CSV.

## Next for the final (Sun 10:00)
Finish the `cala-leads` plugin and validated strategy, add keys to the root `.env`, run `bash scripts/live_check.sh`,
and switch the demo to `VENUS_MODE=live`.
