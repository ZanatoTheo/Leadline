# Leadline service

A local HTTP service between the frontend's server code and the Leadline database. It also runs the background
worker that builds profiles and rankings with the bundled agent (`leadline/agent/`).

`leadline/agent/` is the only copy of the run-time engine in this repo. It is exported from the Venus project
(`python -m venus export`, see `leadline/agent/README.md`) when the agent is retrained; re-exporting replaces it. Its
`leadline_agent/core.py` carries a Leadline-only fallback fix (`FALLBACK_CODES` with `model_bad_reply` and
`output_invalid`, tested in `tests/test_agent_fallback.py`) that a fresh export loses, so re-apply it or move it into
Venus first.

## Run

```bash
.venv/bin/python leadline/serve.py --db leadline/data/leadline.db --port 8765 --env-file .env
```

- `--no-worker`: serve reads only; queued jobs wait.
- `--fake-model`: offline answers for every profile and match run; web tools and Cala are off. For smoke runs.
- `--env-file`: KEY=VALUE file; it never overrides a variable that is already set. No key is ever printed.

It binds to **127.0.0.1 only**. It trusts its caller: for example `PATCH /intros/{id}` takes `userId` from the
body, because the TS server has already checked the session cookie. Never expose the port.

Install: `pip install -r leadline/requirements.txt` (the root `.venv`; see the root README).

## Environment

| Variable | Used for |
|---|---|
| `VERDA_API_KEY` (and the base-model settings in the strategy) | the base model of both agents |
| `VENUS_FALLBACK_PROVIDER=anthropic`, `ANTHROPIC_API_KEY` | the fallback model when the primary fails |
| `CONTEXT_DEV_API_KEY` | web research in profile builds |
| `LEADLINE_LIVE_CALA=1`, `CALA_API_KEY` | Cala in profile builds (off unless set; at most `VENUS_CALA_MAX_CALLS`, default 3, per build) |
| `LEADLINE_TOP_N` | candidates sent to the match agent per ranking (default 10) |
| `LEADLINE_AGENT_DIR` | where the injected agent is (default `leadline/agent`) |

## The page-load rule

Page loads only read the database: no endpoint calls Cala, the web or a model. Anything that needs the agent is
queued as a job:

- a new founder record, investor fund or demo account queues **one profile job** (first build only; editing is out
  of scope);
- a finished profile job queues **one rank job for that user only** (nobody else is re-ranked);
- `GET /rankings/{key}` queues one rank job when the user's best N changed (`ranking.needs_rerank`), and returns the
  stored ranking meanwhile.

## Endpoints

Bodies use the frontend's types (`contracts/schemas/*.json`). Errors are `{"error": "..."}` with 400/403/404/409.

| Method and path | Body / query | Returns |
|---|---|---|
| `POST /users` | `{role, name, email, passwordHash}` | `User` (409 if the email exists) |
| `GET /users/by-email` | `?email=` | `User` |
| `GET /users/{id}` | | `User` |
| `POST /sessions` | `{userId, token, expiresAt}` | 204 |
| `GET /sessions/{token}` | | `{user: User, profile: FounderProfile \| null, discoverable}` (404 if missing or expired) |
| `DELETE /sessions/{token}` | | 204 |
| `POST /demo-users` | `{role, email, name, investorName?, persona?}` | `User` (made once) |
| `PUT /users/{id}/founder` | `{profile, founderName, email, discoverable}` | `FounderRecord` |
| `PUT /users/{id}/investor-fund` | `{investorName}` | 204 |
| `GET /founders` | `?discoverable=1` | `FounderRecord[]` |
| `GET /founders/{id}` | | `FounderRecord` |
| `POST /intros` | `{founderId, investor, direction, note}` | `Intro` (a pending duplicate is returned) |
| `GET /intros` | `?founderId=&investor=` | `Intro[]` |
| `PATCH /intros/{id}` | `{userId, status, passReason?}` | `Intro` (403 not the recipient, 409 already answered) |
| `GET /deals` | `?sector=&stage=&region=&sinceDays=` | `Deal[]` |
| `GET /deals/investor` | `?name=&sinceDays=` | `Deal[]` |
| `GET /deals/company` | `?name=` | `Deal[]` |
| `GET /deals/similar` | `?description=&sector=` | `Deal[]` (companies sharing 2+ content words) |
| `GET /funds` | `?investor=` | `FundClose[]` |
| `GET /fund-closes` | `?sector=&sinceDays=` | `FundClose[]` |
| `GET /entities` | `?name=&limit=` | `CalaEntity[]` |
| `GET /status` | | `{mode: "live" \| "simulated", jobs: {queued, running, failed}}` |
| `GET /profiles/{key}` | | `{status, profile?, rating?, version?, updatedAt?, error?}` |
| `GET /rankings/{key}` | | `{status, ranking: {matches, newCandidates, computedAt} \| null, error?}` |

Profile keys are `founder:<founderId>` and `investor:<slug of the fund name>`.

`/founders` returns full `FounderRecord`s (with the founder's email), like the TS server's `readDb()`: the TS API
routes must keep shaping them (`PublicFounder` for investors) before anything reaches a browser.

## Tests

```bash
cd leadline && ../.venv/bin/python -m pytest -q
```
