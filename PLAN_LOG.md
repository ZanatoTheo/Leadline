# Plan log

## Open problems
- none (Phase 7 gate resolved 2026-11-15: venus/venus/{plugin,runner,fake,errors,cala,envfile}.py are shims to venus.agent.*,
  which matches leadline/agent/leadline_agent byte for byte except core.py's fallback fix, which profiles.py doesn't use.
  Every name profiles.py and the tests use resolves to venus.agent.*. The earlier 260–300-line diff compared the shims.)

## Noticed, not in scope
- `app/ingest/cala_client.py:25` still has a `try: from envload ... except ImportError` fallback with a comment saying
  "removed once app/envload.py exists". It exists now. Left alone (changing it touches behaviour).
- `app/requirements.txt` lists `fastapi`/`uvicorn`, which only the prototype used. Left as is.
- npm packages used only by the deleted shadcn components (radix etc.) stay in `frontend/package.json`.
- `leadline/strategies/*-default.json` stay. They are the source for retraining in the Venus project.
- Bug 12 (thin data) and the standalone-Leadline note from `_cleanup.md` section 5 stay open.
- Git history: commits made before Phase 9 will hold `venus/`, `leadline/runs/` and `submission.md` in history.
  Squash before pushing if they shouldn't be there.

- `leadline/data/leadline.db-shm` / `-wal` appear when tests run: `leadline/tests/test_jobs_db.py:233` opens the real demo
  DB. The DB itself is unchanged (sha256). Add `*.db-shm` and `*.db-wal` to `.gitignore` (needs your OK: .gitignore is
  not in Phase 8's files).
- `.env.example:1` and `app/.env.example:9-10` still mention `venus/.env` and the prototype's `VENUS_MODE`/`VENUS_STRATEGY`.
- `frontend/.env.example` documents `CALA_API_KEY`/`CALA_MODE`, which the frontend no longer reads (it reads only
  `LEADLINE_SERVICE_URL`, `LEADLINE_DEMO_LOGIN`).
- Login page button says "Investor: Sam at Fjord" (`auth-form.tsx:175`), but the demo investor is Sam at Bidra Innovation
  Ventures (`auth.ts:121`). UI text, not changed (no functional changes).
- `app/fixtures/` is read by nothing now (only the deleted prototype adapter); kept as the source of `contracts/training_cases.json`.
- The Cala types in `frontend/src/lib/cala/client.ts` (`CalaQueryResponse`, `QueryHint`, ...) have no users after Phase 3.
- The demo DB holds 14 failed jobs (`GET /status`).
- `.env`: `VENUS_TRAIN_PROVIDER` differs between root and venus/.env; kept the root value (training only). Backups of
  both files (mode 600) in the session scratchpad.

## Log
- 2026-11-14: plan created (0/100). Leadline tests today with venus on PYTHONPATH and the root .venv: 283 passed,
  1 skipped.
- 2026-11-14 Phase 1 Baseline environment and checks: done (0 → 8/100). git init, branch bulldog/cleanup-until-p8 (no commits).
  Baseline tree snapshot (no commit): 4165331f0deef7ce1a5e2661940e87c401b401c7 (separate index in scratchpad).
  Baseline on venus/.venv: leadline 283 passed 1 skipped; venus 385 passed 1 failed (test_failed_model_reply_still_counts_call_and_reported_usage);
  app 40-41 passed, 3-4 failed, all in app/tests/test_smoke.py (prototype; test_companies_search, test_investors_search,
  test_export_csv, and one flaky); tests/integration 36 passed 1 skipped; tsc 0; npm run build 0; LEADLINE_SMOKE=1 smoke run 3 passed.
  No code diff, so no review.
- 2026-11-14 Phase 2 Delete the old FastAPI prototype: done (8 → 20/100). app tests 36 passed; grep for api.main/venus_adapter/app/web empty; bash -n live_check.sh ok; leadline 283 passed 1 skipped.
  Review fixed: app/README.md scope (European, 3 years), cache only with CALA_API_KEY, install line.
  Found: tests/integration must be run from tests/integration/ (as the headers say); from the repo root `import venus` hits the ./venus folder (was hidden by test_live_path.py's sys.path insert). From its folder: 34 passed 1 skipped.
  Found: tests/integration/test_seed_db.py also imports venus (not in Phase 7/9 file lists; handle in Phase 9).
- 2026-11-14 Phase 3 Delete unused frontend files and the broken lint script: done (20 → 30/100). tsc 0, build 0, grep empty, no lint script; contracts/schemas regenerated (only the client.ts hash in sources.json changed; 22 schemas identical); leadline 283 passed 1 skipped.
  Review: root README.md:64,66,82 still describe simulator.ts/normalize.ts; fixed in Phase 6 (README rewrite).
- 2026-11-14 Phase 4 Delete the draft strategies: done (30 → 34/100). Only the two defaults left; leadline 283 passed 1 skipped. Drafts were named only in their own files, the default strategy's history notes and leadline/runs/. No separate review (8 JSON deletions, grep done).
- 2026-11-14 Phase 5 Fix .gitignore: done (34 → 41/100). check-ignore: .env, venus/.env, app/data/cache, .venus_cache, leadline/runs, .venv, venus/.venv, node_modules ignored; leadline/agent/ and leadline/data/leadline.db tracked; no leaks in git status; leadline/agent (35 files, 456K) has no secrets. No separate review (ignore-rule diff, covered by the checks).
- 2026-11-15 Phase 6 Root README and full check before the detach: done (41 → 50/100). README start commands run on a copy of the demo DB (--no-worker): /status answered, /login and / gave 200, demo DB unchanged (sha256). Full check: leadline 283 passed 1 skipped; venus 385 passed 1 failed (known); app 36 passed; integration (from its folder) 34 passed 1 skipped; tsc 0; build 0; smoke 3 passed.
  Review fixed: the code map's src/app row listed shortlist/signals pages that don't exist (it is alerts).
- 2026-11-15 Phase 7 Point Leadline at the bundled agent instead of venus: done (50 → 68/100). Gate passed (see Open problems note). New leadline/engine.py; profiles.py and 5 tests use it; test_runtime.py fixture `clean_agent_modules` sets aside cached leadline_agent (in the test, not runtime.py). New tests/test_engine.py (failed first: no engine; serve loaded 17 venus modules).
  Verify: venus/.venv 286 passed 1 skipped; root .venv (no venus) without test_gate.py 274 passed 2 skipped; integration 34 passed 1 skipped; smoke 3 passed.
  Review fixed: engine fixed the agent root at import time, before serve.py loads --env-file (LEADLINE_AGENT_DIR from the env file would break runtime.load_agent). Now lazy (module __getattr__); profiles calls engine.load_plugin/run_case at use time; test added (failed first).
  Failed attempt: first full run after the switch had 2 failures (module-cache leak, predicted in the plan); fixed by the fixture.
  Handed to Phase 9 (from review): test_gate.py imports venus (deleted there); test_runtime.py:169 `importorskip("venus.agent")` will skip silently once venus is gone — should use leadline_agent; test_seed_db.py imports venus; test_profiles.py:146 name says "venus" (cosmetic).
- 2026-11-15 Phase 8 One root .venv, merged .env, updated paths and docs: done (68 → 80/100). Root .env got VENUS_FALLBACK_PROVIDER, VENUS_MAX_TOKENS from venus/.env (12 keys, union; values never printed). Paths moved to .venv / .env. _cleanup.md: Venus-only items removed, setup block updated.
  Verify on root .venv (no venus): leadline 276 passed 2 skipped (without test_gate.py); app 36 passed; integration 34 passed 1 skipped; smoke 3 passed; tsc + build 0; demo DB unchanged.
  Review fixed: engine read DEFAULT_AGENT_DIR once at import (now runtime.DEFAULT_AGENT_DIR at call time); new tests: LEADLINE_AGENT_DIR set after import is used, root follows runtime default (failed first); README setup lines 70-71; _cleanup.md commands.
  Review not fixed (not reachable in serve.py): with a missing LEADLINE_AGENT_DIR, engine raises ModuleNotFoundError where load_agent raises AgentLoadError; engine caches names after first use, so changing LEADLINE_AGENT_DIR mid-process isn't followed.
  Note: PLAN.md "Defaults" still points at "_cleanup.md 3.3", now removed from _cleanup.md (the failing venus test goes away with venus/ in Phase 9).
- 2026-11-15 /bulldog-until 8 finished: phases 1-8 done, 80/100. Next: Phase 9 "Delete Venus and the training tools".
- 2026-11-15 Phase 9 Delete Venus and the training tools: done (80 → 92/100). Deleted venus/ (identical copy with git history in ~/Projects/junction-26/venus), train_leadline.py, inject_agent.sh, test_training_script.py, test_gate.py, tests/live/* except test_cala.py + conftest.py. conftest loads .env via leadline_agent.envfile; live_check.sh drops the Venus steps; READMEs updated (leadline/README.md now explains leadline/agent as the only engine copy and the fallback fix — the Phase 8 note I had missed).
  Found and fixed: 3 test_agent_fallback.py tests started skipping (they used Venus's toy plugin fixture) → copied the 4 fixture files to leadline/tests/fixtures/toy_plugin/. Failed attempt: a sed with `#` in the replacement; redone with Edit.
  Review fixed: the new test_runtime AgentError test could pass on a cached fake package and errored without leadline/agent → uses clean_agent_modules, skips without the agent, asserts the class module and file; stale comments in app/requirements.txt, leadline/requirements.txt, .env.example:1; 5 skip reasons naming inject_agent.sh. (Comment/message-only edits outside the phase list, made because this phase's deletions made them wrong.)
- 2026-11-15 Phase 10 Delete runs and submission.md, final check: done (92 → 100/100). Deleted leadline/runs/ and submission.md (nothing read them). .gitignore: removed leadline/runs/ and the dead venus/runs/ lines, added *.db-shm / *.db-wal (the logged ignore fix).
  Final check on root .venv, no venus installed: import serve ok; no venus imports; leadline 277 passed 1 skipped (dist export test); app 36 passed; integration 14 passed 1 skipped (also from repo root now); live 1 skipped; bash -n live_check ok; tsc + build 0; smoke 3 passed; service /status answered; demo DB unchanged; git status: no .env, caches, .venv, runs or DB side files; leadline/data/leadline.db and leadline/agent/ listed; env templates hold no secrets. No separate review for Phase 10 (deletions + ignore lines, covered by the checks).
