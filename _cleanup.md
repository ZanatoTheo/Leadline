# Cleanup before the first commit

This folder is a copy of `junction-26` with the planning files, caches, build output, logs and venus's own `.git`
left out (2026-11-14). The items below are still in it. Delete or keep each one, then run the checks at the end.
Every path is relative to this folder.

## 1. Safe to delete (nothing uses them)

| Path | What it is | Checked how |
|---|---|---|
| `app/api/`, `app/web/` | First prototype: a FastAPI app and a static page. `leadline/` + `frontend/` replaced it. | No file outside `app/` imports or links them. |
| `app/tests/test_smoke.py`, `app/tests/test_live_mode.py` | Tests for that prototype. Delete them together with `app/api/`. | They import `api.main`. |
| `app/STATUS.md` | Status notes for the prototype (2026-11-13). | Not linked. |
| `app/README.md` | Describes the prototype. Rewrite it to cover only `app/ingest` (the Cala pull), or delete it. | Only file left with a `junction-26` path. |
| `leadline/strategies/*-draft-*.json` (8 files) | Training drafts. Only `leadline-match-default.json` and `leadline-profile-default.json` are used. | `inject_agent.sh` exports only validated strategies; the drafts are named only in `leadline/runs/*/ledger.json`. |
| `frontend/src/lib/cala/simulator.ts`, `frontend/src/lib/cala/normalize.ts` | Old fake-data and convert helpers. | Only named in comments (`client.ts:6`, `db.py:35`). If you delete them, update those two comments. |
| `frontend/src/components/ui/{badge,card,progress,scroll-area,separator,slider,tabs,tooltip}.tsx` | Unused shadcn components. | No import anywhere in `frontend/src`. |
| `submission.md` | Hackathon write-up. | Keep it if you want it in the repo; nothing reads it. |

## 2. Keep, but don't commit (add to `.gitignore`)

| Path | Why |
|---|---|
| `.env`, `venus/.env` | Real keys. Already matched by `.env` / `*.env` in `.gitignore`. Check with `git status` before the first commit. |
| `app/data/cache/`, `.venus_cache/cala/` | Cala replies already paid for. They let `scripts/seed_db.py` rebuild the dataset without new Cala calls. Already ignored. |
| `leadline/data/leadline.db` | The demo DB: demo accounts (Sam on Bidra, Alex/Carbonlens), sessions, the matched Bidra intro, stored rankings. **Not ignored yet**: add `leadline/data/*.db`, unless you decide to ship it as demo data. |
| `leadline/runs/` (9 runs, 512 KB) | Training run records (ledgers, training.jsonl). Only `scripts/train_leadline.py` and Venus training write or read them. Add `leadline/runs/`, or delete it. |

## 3. Change before the first commit

1. **`.gitignore`**
   - Remove `leadline/agent/` from the ignore list and commit the folder, so a fresh clone runs without exporting from Venus. It also holds the Leadline-only fallback fix (`core.py` `FALLBACK_CODES` + `model_bad_reply`, `output_invalid`). That fix is lost when `scripts/inject_agent.sh` runs again, so either repeat it after each inject or move it into Venus.
   - Add `leadline/data/*.db`, `leadline/runs/` (see 2) and `dist/`.
   - Remove the entries for folders that don't exist here (`backend/`, `frontend/.cala-cache/`, `frontend/.leadline-data/`).

2. **`frontend/package.json` `lint`**: runs `next lint`, which this Next version no longer has. Change it to `eslint .` (add an eslint config) or remove the script.
3. **`README.md`** (root): rewrite for this repo: what Leadline is, the three folders, setup, how to start the service and the frontend. Start command from `leadline/README.md`:
   `.venv/bin/python leadline/serve.py --db leadline/data/leadline.db --port 8765 --env-file .env`
4. **`AGENTS.md`** (root): only the Next.js note that `next dev` re-adds. Keep or delete; `frontend/` will re-create its own.

## 4. Set up and check (after the cleanup)

```bash
cd ~/Projects/leadline
python3 -m venv .venv && .venv/bin/pip install -r leadline/requirements.txt -r app/requirements.txt
(cd frontend && npm install)
(cd leadline && ../.venv/bin/python -m pytest -q tests)          # 2026-11-15: 276 passed, 2 skipped (without test_gate.py)
.venv/bin/python -m pytest -q app/tests                          # 2026-11-15: 36 passed
(cd tests/integration && ../../.venv/bin/python -m pytest -q)    # 2026-11-15: 34 passed, 1 skipped
(cd frontend && npx tsc --noEmit && npm run build)
LEADLINE_SMOKE=1 .venv/bin/python -m pytest -q tests/integration/test_smoke_app.py   # 2026-11-15: 3 passed
git status   # confirm no .env, caches or runs are listed (leadline/data/leadline.db is committed as demo data)
```

## 5. Open items carried over

- **Bug 12 (thin data)**: 20 seeded rounds, so no breakouts, empty Funding twins and Next twins, and "Pace unknown" for most funds. The fix is a Cala data pull (costs credits; get a call estimate first).
- **Standalone Leadline** (only if `leadline/` is ever shipped without `venus/`): `leadline/profiles.py:21` imports `venus` at startup. Switch it to the bundled `leadline_agent` (`load_plugin`, `run_case` exist in `leadline/agent/leadline_agent/plugin.py` and `runner.py`), and make the 7 test files that import `venus` skip without it.

## 6. Extra phase: detach the Venus training engine

Venus ships as its own project. This phase leaves only the exported agent (`leadline/agent/leadline_agent`) here, with
Leadline still running and passing its tests. Research done 2026-11-14; nothing below is applied yet, except a new
`.venv` at this folder's root with `leadline/requirements.txt` installed. When this phase is done, the Venus items in
section 3 (venus test, `venus/.gitignore`, `venus/AGENTS.md`) and `venus/venus.egg-info` in section 1 no longer apply.

### What depends on venus/ today
| Kind | Where | Needed by the running app? |
|---|---|---|
| Runtime import | `leadline/profiles.py:21` `from venus import load_plugin, run_case` (loaded at start: serve → db → profiles) | **Yes**: the only one |
| Unit tests | `leadline/tests/` test_profiles, test_db, test_build_cases, test_prefilter, test_match_plugin (`load_plugin`, `FakeModel`, `fake_text`, `InputError`, `Cala`, `cala_tools`) | No (tests) |
| Training-only tests | `leadline/tests/test_gate.py` (`venus.gate`, `venus.strategy`); `test_runtime.py:156` already `importorskip`s `venus.agent` | No |
| Training/tooling | `scripts/train_leadline.py`, `scripts/inject_agent.sh`, `tests/integration/test_training_script.py`, `tests/live/*` except `test_cala.py`, `venus/tools/models_probe.py` (via `scripts/live_check.sh`) | No |
| Prototype | `app/api/venus_adapter.py` (lazy `import venus`) | No (already on the delete list in `_cleanup.md`) |
| Paths | `venus/.venv/bin/python` and `--env-file venus/.env` in `leadline/README.md`, `leadline/serve.py:4`, `scripts/smoke_app.py:46`, `scripts/seed_db.py:3`, `scripts/live_check.sh`, `tests/integration/*` headers and `test_smoke_app.py:18`, `tests/live/conftest.py` | Start commands only |

The agent copy already has every name used: `plugin.load_plugin` (default `runtime_only=False` still loads the
checker and gate hook, so full plugins work), `runner.run_case`, `fake.FakeModel/fake_text/fake_tool_call`,
`errors.InputError`, `cala.Cala/cala_tools`.

### Changes (all in ~/Projects/leadline)
1. **New `leadline/engine.py`**: puts the agent root on `sys.path` the way `runtime.load_agent`
   (`leadline/runtime.py:21`) does (`LEADLINE_AGENT_DIR`, else `leadline/agent`) and re-exports the names above.
2. **`profiles.py:21`** → `from engine import load_plugin, run_case`. The 5 unit tests import the same names from
   `engine` instead of `venus` (one-line edits each).
3. **Import-order fix (needed)**: once `engine` is imported, the real `leadline_agent` sits in `sys.modules`, and
   `test_load_agent_imports_only_from_injected_agent_root` (`tests/test_runtime.py:31`), which loads a fake
   `leadline_agent` from a temp root, would get the cached one and fail (the phase 5 leak again). Fix in
   `runtime.load_agent`: before importing, drop cached `leadline_agent*` modules whose file is outside the requested
   root. That is also correct behaviour for `LEADLINE_AGENT_DIR` pointing elsewhere.
4. **Delete (training engine)**: `venus/`, `scripts/train_leadline.py`, `scripts/inject_agent.sh`,
   `tests/integration/test_training_script.py`, `leadline/tests/test_gate.py`, `tests/live/` except `test_cala.py`
   (keep it only if its conftest no longer needs `venus.envfile`; `leadline_agent.envfile` can replace it). In
   `scripts/live_check.sh` drop the model-probe and venus-test steps.
5. **Paths and env**: `venus/.venv/bin/python` → `.venv/bin/python`; `--env-file venus/.env` → `.env`. Merge
   `venus/.env` into the root `.env` (newer Cala key, `VENUS_FALLBACK_PROVIDER`, `VENUS_MAX_TOKENS`) comparing key
   names only, never printing values. Update `leadline/README.md` and the root README setup block
   (`python3 -m venv .venv && .venv/bin/pip install -r leadline/requirements.txt -r app/requirements.txt`).
6. **`.gitignore`**: stop ignoring `leadline/agent/` (it is now the only copy of the engine; it also carries the
   Leadline-only fallback fix). Note in `leadline/README.md` that it is regenerated from the Venus project with
   `venus export` when the agent is retrained.
7. Update `_cleanup.md`: remove the Venus-specific items (venus test fix, venus/.gitignore merge, egg-info).

### Verification
- Proof Venus is gone: `.venv/bin/python -c "import sys; sys.path.insert(0,'leadline'); import serve"` with no
  `venus` package installed, and `grep -rn "from venus\|import venus" leadline app scripts tests` → only the
  deleted/prototype files.
- `cd leadline && ../.venv/bin/python -m pytest -q tests` (was 284 passed; expect fewer after `test_gate.py` goes,
  0 failures). `.venv/bin/python -m pytest -q app/tests`.
- `cd frontend && npm install && npx tsc --noEmit && npm run build`.
- Start the service on the demo DB (`.venv/bin/python leadline/serve.py --db leadline/data/leadline.db --port 8765
  --env-file .env`) and the frontend, then a FakeModel rank job via the existing smoke run
  (`LEADLINE_SMOKE=1 .venv/bin/python -m pytest -q tests/integration/test_smoke_app.py`), which proves a job runs on
  the bundled agent.

### Effort
About 35-45 min: steps 1-3 ~15 min, 4-7 ~10 min, checks ~15 min (npm install + build dominate).
