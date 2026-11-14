# STATUS — Leadline app (2026-11-13)

## What works (verified end to end)

- `python -m ingest.build_dataset` writes `data/dataset.json`. Without a
  `CALA_API_KEY` it writes the built-in sample dataset (6 companies, 7 investors,
  7 rounds); with a key it queries Cala and maps rows defensively.
- API: `/health`, `/api/companies?q=`, `/api/investors?q=`, `/api/match`,
  `/api/export.csv?run_id=` — all exercised against a live uvicorn server.
- Both directions return ranked, sourced match lists with candidate names
  attached; CSV export produces one row per match with the top reason.
- UI: two tabs, Cala search picker, inline startup form, filters, result cards
  (score bar, lead badge, active badge + last lead date, confidence, reasons
  with clickable sources), "Why not these?" panel with plain-language labels,
  loading/partial/error/empty states, mock badge, light/dark + mobile layout.
- 7 pytest smoke tests pass in ~0.6 s, no network.

## What's mocked

- **All matching.** `VENUS_MODE=mock` (default) serves
  `fixtures/mock_startup_to_investors.json` / `mock_investor_to_startups.json`.
  The fixtures use sample-dataset IDs; picking a different subject in mock mode
  still returns the fixture (request is echoed into the result).
- Live Cala ingestion path is written but untested (no key at build time).

## The Venus gap (important)

- The `cala-leads` plugin is **not yet built**; the user is building it now.
  This side is ready: `contracts/` holds the output JSON Schema, an example
  envelope and training cases; the adapter builds a real `venus.Venus` from
  `../venus` (verified: with an empty plugins dir, live mode returns
  `plugin_not_found` → HTTP 404). Live mode needs `pip install -r
  ../venus/requirements.txt` in this venv.

## Open questions

- Does Cala ever name the round lead? Its docs show no round entity or lead
  field; answers may name a lead in text. Ingestion only sets `role` from
  explicit mentions, else `"unknown"` — needs a check with a real key.
- Cala query-row shapes vary by question; the mapping is defensive but should
  be verified against real responses (README has notes).
- Should mock mode return per-subject fixtures so the demo looks right for any
  picked company? Currently one fixture per direction.

## Not done (by design)

- No auth/sign-up, no competitor conflict check, no investor brief page, no
  alerts, no warm-intro paths — the Leadline walkthrough's later steps are out
  of scope for this fallback.
