# Clean up the leadline codebase before the first commit (per _cleanup.md)
Progress: 100/100 · Updated: 2026-11-15

## Context
- Why: this folder is a copy of `junction-26`. It still holds a dead prototype, unused files, Venus (the training
  engine, which ships as its own project), training runs, and setup docs that point at the old layout.
- System today: `frontend/` (Next.js) calls the Leadline service (`leadline/serve.py` → `db.py` → `profiles.py`,
  `runtime.py`). `profiles.py:21` imports `venus`; ranking jobs run the bundled agent in `leadline/agent/` (a copy of
  `venus/venus/agent/` plus the Leadline-only fallback fix in `core.py`). `app/ingest` pulls Cala data and
  `scripts/seed_db.py` builds `leadline/data/leadline.db`.
- Result: no prototype, unused files or Venus in the repo. The app runs from one root `.venv` on the bundled agent.
  `leadline/data/leadline.db` is committed as demo data. `.gitignore` keeps out only secrets, caches and build output.
  READMEs match the real setup. Every test suite, the frontend build and the smoke run pass as they did at the start.
- Rule for every phase: **no changes in what the app does**. Only delete unused code, fix comments, docs, paths and
  ignore rules. If a step would change what the app does, stop and ask.
- Defaults chosen (change them if wrong):
  - The demo DB stays at `leadline/data/leadline.db` and is committed (not moved to another folder).
  - The `frontend` `lint` script is removed, not replaced with a new eslint setup. A new setup could bring lint
    errors that tempt code changes.
  - The failing Venus test (`_cleanup.md` 3.3) is not fixed. Fixing it changes `venus/runner.py`, and `venus/` is
    deleted in Phase 9.
  - The `_cleanup.md` 6.3 import fix is made in the test (`test_runtime.py`), not in `runtime.load_agent`, so the
    app's code doesn't change.
  - Root `AGENTS.md` stays. `venus/.gitignore` and `venus/AGENTS.md` are not merged: they go with `venus/`.

## Phase 1: Baseline environment and checks (weight 8) [x]
- Why: the leadline tests need `venus`, `test_smoke_app.py` needs `venus/.venv`, and the frontend has no
  `node_modules`. Without a baseline, a later failure can't be told apart from one that was already there.
- Fits in: every later Verify step compares against these numbers. `git init` lets `/checkpoint` review each phase
  with `git diff HEAD`.
- Files: none in the repo (creates `venus/.venv`, `frontend/node_modules`, `.git`).
- Actions: `python3 -m venv venus/.venv && venus/.venv/bin/pip install -e venus -r leadline/requirements.txt -r
  app/requirements.txt`. Run `cd frontend && npm install`. Run `git init` (no commit without asking). Run all suites
  and write the numbers in PLAN_LOG.md.
- Verify: `(cd leadline && ../venus/.venv/bin/python -m pytest -q tests)` → 283 passed, 1 skipped (seen today).
  `(cd venus && .venv/bin/python -m pytest -q tests)` → 385 passed, 1 failed. `venus/.venv/bin/python -m pytest -q
  app/tests` → 44 passed. `(cd frontend && npx tsc --noEmit && npm run build)` → exit 0.
  `LEADLINE_SMOKE=1 venus/.venv/bin/python -m pytest -q tests/integration/test_smoke_app.py` → passes. Any failure is
  logged as "already there" and not fixed.
- Risks: the smoke run hasn't been run since the last UI fixes and may already fail. If it does, log it and ask
  before going on. pip/npm need the network.

## Phase 2: Delete the old FastAPI prototype (weight 12) [x]
- Why: `app/api/` and `app/web/` were replaced by `leadline/` + `frontend/`. Their tests and scripts point at code
  nobody runs.
- Fits in: uses the Phase 1 baseline. Removes the only users of `venus_adapter` outside `leadline/`, which makes
  Phase 9 smaller. `app/ingest`, `app/envload.py` and `app/contracts/` stay (`test_match_plugin.py:43` reads
  `app/contracts/venus_request.example.json`).
- Files: delete `app/api/`, `app/web/`, `app/tests/test_smoke.py`, `app/tests/test_live_mode.py`, `app/STATUS.md`,
  `tests/integration/test_live_path.py` (it tests `api.venus_adapter`). Edit `scripts/live_check.sh`: drop steps 4–5
  (start `api.main`), step 8 (`cala-leads/`, which doesn't exist) and the unused `$PORT`/server code. Rewrite
  `app/README.md` to cover only `app/ingest` (the Cala pull), `envload.py` and `contracts/`.
- Actions: delete the files, change the script and rewrite the README.
- Verify: `venus/.venv/bin/python -m pytest -q app/tests` → all pass (44 minus the removed tests). `grep -rnE
  "api\.main|venus_adapter|app/web" --include=*.py --include=*.sh --include=*.md app scripts tests leadline` →
  nothing (`submission.md` is deleted in Phase 10). `bash -n scripts/live_check.sh` → exit 0. Leadline tests still
  283 passed, 1 skipped.
- Risks: something reads `app/fixtures/` or `app/api/` by path at runtime. The grep and the smoke run in Phase 6 would
  show it.

## Phase 3: Delete unused frontend files and the broken lint script (weight 10) [x]
- Why: 8 shadcn components, `simulator.ts` and `normalize.ts` are imported nowhere. `npm run lint` calls `next lint`,
  which this Next version no longer has.
- Fits in: frontend only. Comments in `frontend/src/lib/cala/client.ts:6,38` and `leadline/db.py:35` name the deleted
  files and must be reworded (comments only; `EUR_PER` values stay as they are).
- Files: delete `frontend/src/components/ui/{badge,card,progress,scroll-area,separator,slider,tabs,tooltip}.tsx`,
  `frontend/src/lib/cala/simulator.ts`, `frontend/src/lib/cala/normalize.ts`. Edit comments in `client.ts` and
  `db.py`. Remove the `lint` line from `frontend/package.json`.
- Actions: grep for imports first (`components/ui/<name>`, `cala/simulator`, `cala/normalize`, `./simulator`,
  `./normalize`). Delete only files with zero importers.
- Verify: `(cd frontend && npx tsc --noEmit && npm run build)` → exit 0. The grep for the deleted names in
  `frontend/src` finds only the reworded comments or nothing. Leadline tests still pass.
- Risks: a dynamic import or a re-export through an index file. The build would fail. The npm packages these
  components used stay in `package.json` (see PLAN_LOG "Noticed").

## Phase 4: Delete the draft strategies (weight 4) [x]
- Why: the 8 `leadline/strategies/*-draft-*.json` files are training leftovers. The agent loads strategies from
  `leadline/agent/strategies/` (`core.py:173`), which holds only the two defaults.
- Fits in: `scripts/inject_agent.sh` exports only validated strategies. The drafts are named only in
  `leadline/runs/*/ledger.json`, which is deleted in Phase 10. The two `*-default.json` files stay.
- Files: delete `leadline/strategies/*-draft-*.json` (8 files).
- Actions: grep for `draft-2026` outside `leadline/runs/` first, then delete.
- Verify: `ls leadline/strategies` → only the two defaults. Leadline tests → 283 passed, 1 skipped.
- Risks: a test globs `leadline/strategies/`. The test run would show it.

## Phase 5: Fix .gitignore (weight 7) [x]
- Why: `.gitignore` hides `leadline/agent/`, which the app needs on a fresh clone. It lists folders that don't exist,
  and it doesn't ignore the training runs.
- Fits in: needed before any commit. Phase 9 depends on `leadline/agent/` being tracked, because it becomes the only
  copy of the engine. The demo DB must stay tracked (your choice).
- Files: `.gitignore`.
- Actions: remove `leadline/agent/` and its comment. Remove the `backend/*`, `frontend/.cala-cache/` and
  `frontend/.leadline-data/` entries. Add `leadline/runs/` for now (removed in Phase 10). Keep `.env`, `*.env`,
  `app/data/`, `.venus_cache/`, `.venv/`, `dist/`, `*.egg-info/`. Don't add `*.db`.
- Verify: `git check-ignore -v .env venus/.env app/data/cache .venus_cache leadline/runs venus/.venv` → each is
  matched. `git check-ignore leadline/agent/leadline_agent/core.py leadline/data/leadline.db` → exit 1 (not
  ignored). `git status --porcelain | grep -E "\.env$|cache|/runs/|\.venv"` → nothing.
- Risks: `/lib/` or `build/` hiding real source (`frontend/src/lib` is safe because `/lib/` is anchored to the
  root). Check with `git status --porcelain --ignored | grep '^!!'`, which lists every ignored path.

## Phase 6: Root README and full check before the detach (weight 9) [x]
- Why: the root README describes the old repo. Phases 7–9 are the risky part, so everything before them must be
  proven to still run.
- Fits in: uses Phases 2–5. Phase 8 changes only the setup block of this README (`.venv` paths).
- Files: `README.md` (root). `AGENTS.md` stays as it is.
- Actions: rewrite `README.md`: what Leadline is, the folders (`frontend/`, `leadline/`, `app/ingest`, `contracts/`,
  `scripts/`, `tests/`, `venus/` for now), setup, starting the service
  (`venus/.venv/bin/python leadline/serve.py --db leadline/data/leadline.db --port 8765 --env-file .env`) and the
  frontend, and a note that the demo DB is committed demo data.
- Verify: run the README's start command and the frontend. The service answers on :8765 and the frontend page loads.
  Then the full baseline: leadline, app and venus tests, `tsc` + build, and the `LEADLINE_SMOKE=1` smoke run → same
  results as Phase 1, apart from the tests deleted on purpose.
- Risks: the README start command differs from what `serve.py` takes. Running it shows this.

## Phase 7: Point Leadline at the bundled agent instead of venus (weight 18) [x]
- Why: `profiles.py:21` (`from venus import load_plugin, run_case`) is the only runtime use of `venus`. Venus can't
  be removed until it is gone.
- Fits in: `serve` → `db` → `profiles` loads at start. `runtime.load_agent` (`runtime.py:22`) already loads
  `leadline_agent` from `LEADLINE_AGENT_DIR` or `leadline/agent`. Unblocks Phases 8–9.
- Files: new `leadline/engine.py`. Edit `leadline/profiles.py:21`, `leadline/tests/{test_profiles,test_db,
  test_build_cases,test_prefilter,test_match_plugin}.py` (import lines only), and `leadline/tests/test_runtime.py`
  (test isolation only).
- Actions:
  1. **Gate first.** Compare `venus/venus/{plugin,runner,fake,errors,cala}.py` with
     `leadline/agent/leadline_agent/` (they differ by about 260–300 lines today). Trace the paths `profiles.py` uses
     (`load_plugin`, `run_case`) and the names the 5 tests use. If anything on those paths behaves differently
     (inputs, outputs, errors, fallback), stop and ask before switching.
  2. `engine.py` puts the agent root on `sys.path` the way `runtime.load_agent` does and re-exports `load_plugin`,
     `run_case`, `FakeModel`, `fake_text`, `fake_tool_call`, `InputError`, `Cala`, `cala_tools`.
  3. Switch `profiles.py` and the 5 tests to `from engine import ...`.
  4. In `test_load_agent_imports_only_from_injected_agent_root`, use `monkeypatch.delitem(sys.modules, ...)` to
     drop cached `leadline_agent*` modules, so the fake package loads.
- Verify: `(cd leadline && ../venus/.venv/bin/python -m pytest -q tests)` → 283 passed, 1 skipped. Then without venus
  on the path: `(cd leadline && ../.venv/bin/python -m pytest -q tests --ignore tests/test_gate.py)` → 0 failures.
  `grep -n "venus" leadline/profiles.py leadline/engine.py` → nothing.
- Risks: the agent's `run_case`/`load_plugin` may behave differently from venus's (the gate catches this). The
  module cache leaking between tests (seen in the earlier phase 5): if the order matters, the test fails depending on
  order. Run the file alone and the full suite.

## Phase 8: One root .venv, merged .env, updated paths and docs (weight 12) [x]
- Why: start commands, scripts and test headers use `venus/.venv/bin/python` and `--env-file venus/.env`, and both
  go away with `venus/`. `venus/.env` holds keys the root `.env` lacks (newer Cala key, `VENUS_FALLBACK_PROVIDER`,
  `VENUS_MAX_TOKENS`).
- Fits in: must run before Phase 9 deletes `venus/.env`. Uses the root `.venv` (already has
  `leadline/requirements.txt`).
- Files: `.env` (merge), `leadline/README.md`, `leadline/serve.py:4` (docstring), `scripts/smoke_app.py:3`,
  `scripts/seed_db.py:3`, `scripts/live_check.sh`, `tests/integration/test_seed_db.py:4`,
  `tests/integration/test_smoke_app.py:7,18`, `tests/live/conftest.py`, `contracts/README.md:13`, `README.md` setup
  block, `_cleanup.md`.
- Actions: install `app/requirements.txt` into `.venv`. Merge `.env` by **key names only**, never printing values.
  Copy keys missing from root. For keys in both with different values (compared by hash), stop and ask which wins.
  Replace the paths. In `leadline/README.md`, note that `leadline/agent/` is regenerated with `venus export` from the
  Venus project. Remove the Venus items from `_cleanup.md` (3.2, 3.3, egg-info).
- Verify: `grep -rnE "venus/\.venv|venus/\.env" --include=*.py --include=*.sh --include=*.md . | grep -v
  node_modules` → only files deleted in Phase 9. `LEADLINE_SMOKE=1 .venv/bin/python -m pytest -q
  tests/integration/test_smoke_app.py` → passes on the root `.venv`. The `.env` key-name list is the union of both.
- Risks: overwriting a working key. That is why differing keys stop for a question.

## Phase 9: Delete Venus and the training tools (weight 12) [x]
- Why: Venus ships as its own project. After Phases 7–8 nothing the app runs uses it.
- Fits in: the last step of the detach. After it, `leadline/agent/` (tracked since Phase 5) is the only engine copy.
- Files: delete `venus/`, `scripts/train_leadline.py`, `scripts/inject_agent.sh`,
  `tests/integration/test_training_script.py`, `leadline/tests/test_gate.py`, `tests/live/*` except `test_cala.py` +
  `conftest.py`. Edit `tests/live/conftest.py:20` (`venus.envfile` → `leadline_agent.envfile`, same code) and
  `scripts/live_check.sh` (drop the model-probe and venus-test steps).
- Actions: delete, then make the two edits.
- Verify: `.venv/bin/python -c "import sys; sys.path.insert(0,'leadline'); import serve"` → exit 0, and
  `.venv/bin/pip show venus` → not found. `grep -rnE "from venus|import venus" leadline app scripts tests` →
  nothing. Leadline tests → 0 failures (fewer tests, `test_gate.py` is gone). App tests pass. `tsc` + build pass.
  Smoke run passes (a FakeModel rank job on the bundled agent).
- Risks: a hidden `venus` import loaded only on some paths. Start the service on the demo DB and run the smoke run.

## Phase 10: Delete runs and submission.md, final check (weight 8) [x]
- Why: you asked for `leadline/runs/` and `submission.md` to be deleted at the end. The repo must be proven ready for
  its first commit.
- Fits in: after Phase 9 nothing reads `leadline/runs/` (only `train_leadline.py` and Venus training did).
- Files: delete `leadline/runs/`, `submission.md`. Remove the `leadline/runs/` line from `.gitignore`.
- Actions: grep for `leadline/runs` and `submission.md` first, then delete.
- Verify: the full suite on `.venv` (leadline, app), `tsc` + `npm run build`, the `LEADLINE_SMOKE=1` smoke run →
  all pass. `git status --porcelain` lists no `.env`, cache, `.venv` or runs, and does list
  `leadline/data/leadline.db` and `leadline/agent/`.
- Risks: a doc still links `submission.md`. The grep finds it.
