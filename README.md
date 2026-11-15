# Leadline

**Don't guess who'll fund you. Leadline finds the startups that were exactly where you are, shows who backed them, and tells you which of those investors need you right now.**

Built for first-time founders raising their first round. Powered by [Cala](https://cala.ai): every feature depends on Cala's linked companies → funding rounds → investors data, with a source on every claim.

## How it works

1. **Describe your startup once** (`/onboarding`): what you do, who you sell to, stage, region, raise size and competitors.
2. **Funding twins** (`/twins`): the startups most like yours, and every round each raised since, with who led it, how much and when. It also benchmarks your raise against theirs and shows how long they took to reach the next round.
3. **Who to pitch** (`/investors`): investors ranked by how often and how recently they *led* rounds like yours, with badges for twins backed, deployment timing, portfolio fit and conflicts. Sortable by each.
4. **Investor brief** (`/investors/[slug]`), with every point sourced:
   - **Why them**: rounds they led, especially for your twins.
   - **Why now**: fresh fund closes and recent lead pace (deploying, steady or slowing).
   - **Why you**: portfolio companies that look like your customers. You can help their portfolio.
   - **Round builder**: who usually joins when they lead, so you can fill the round.
   - **Conflict check**: whether they back a named competitor, or a company doing the same thing for the same customers.
5. **Signals** (`/alerts`): Leadline re-checks the database every 5 minutes while open and alerts you to new rounds in your space and to funds that just closed.
6. **Outreach** (`/outreach/[slug]`): an email that cites their twin deal, their portfolio fit and their new fund, with each fact's source listed beside it.

## Accounts and roles

Founders and investors are **separate workspaces**. You sign up as one or the other (`/signup`), and log in (`/login`) straight into yours:

- **Founder workspace:** Today, Funding twins, Who to pitch, Intros, Signals, My startup (routes in `src/app/(founder)/`).
- **Investor workspace:** Today, Deal flow and Your thesis (routes in `src/app/(investor)/`).

Both roles land on **Today**: an action list, not a chart dashboard. Every line is something that changed plus the one thing to do about it. Founders see investor invites, replies and pass reasons, new rounds and fund closes in their space, and who to approach next. Investors see intro requests with fit scores, matches, look-alikes of their breakouts likely raising now, and founders who fit but haven't been contacted.

Each route group has a server layout that redirects logged-out users to login, and redirects users of the other role to their own home. Every API checks the session too: data and actions are scoped to the logged-in founder's startup or investor's fund, never to IDs sent from the browser. Passwords are hashed with scrypt, and sessions are httpOnly cookies.

**Demo accounts:** in development, the login page has one-click buttons for a ready-made founder (Alex at Carbonlens) and investor (Sam at Bidra Innovation Ventures). The demo DB (`leadline/data/leadline.db`) already holds both accounts. They're disabled in production unless `LEADLINE_DEMO_LOGIN=true`.

## For investors: Leadline Match

Leadline brings both sides together around the same Cala evidence, with double opt-in.

1. **Pick your fund** (`/investor/setup`): no thesis form. Leadline reads the investor's thesis from their rounds in Cala: what they lead, typical check, sectors, deployment status, co-investors, and **breakouts** (portfolio companies that raised a bigger round after they came in).
2. **Deal flow** (`/investor`):
   - **Intro requests** from founders, each with the founder's note and a **fit card**: look-alikes already in the portfolio (and what happened to them), check-size fit, conflicts, portfolio companies that could be the founder's customers, and timing. Every line is sourced.
   - **Interested** shares contacts. **Pass** takes one click with a reason, which the founder sees.
   - **Due diligence pages**: click any startup to open a full page. Leadline founders (`/investor/startup/[id]`) show reasons to invest, risks to check, fit with your fund, the market (comparable rounds, money raised, median size), how look-alike startups did after this stage, competitors' rounds, other investors likely to compete for the lead, and the intro actions. Startups found in Cala (`/investor/company/[name]`) show funding history, backers, similar companies, and whether they're likely raising soon. Founders are only visible if they opted in or have an intro with your fund.
   - **Discover**: opted-in founders who fit, which the investor can invite, plus **next twins**: startups in Cala that look like the investor's breakouts, flagged "raising soon" 12+ months after their last round.
3. **Founders** request intros from any investor brief (seeing exactly what the investor will see first), get invited by investors if they opt in, and track everything on `/intros`, including a summary of pass reasons.

**Business model:** founders free; investors pay (Leadline Pro, €249 per partner per month on the pricing section) for pre-qualified, sourced deal flow.

Users, sessions, founder records, intros, market data and the agent's profiles and rankings live in the Leadline
service's SQLite database (`leadline/data/leadline.db`). Investors pick which fund they represent; verifying that they
really work there (for example by work-email domain) is not built yet.

## Repo layout

| Folder | What |
|---|---|
| `frontend/` | The Next.js app (pages, API routes, session checks). Reads everything from the Leadline service. |
| `leadline/` | The Leadline service (`serve.py`): the database, the job worker, and the bundled agent in `leadline/agent/` that builds profiles and rankings. See `leadline/README.md`. |
| `leadline/data/leadline.db` | Demo data, committed on purpose: demo accounts, market data, a matched intro, stored rankings. |
| `app/` | The Cala pull (`app/ingest`) and its disk cache. See `app/README.md`. |
| `contracts/` | JSON Schemas made from the frontend's TypeScript types; the service's tests check against them. |
| `scripts/` | `seed_db.py` (rebuild the DB from the cached Cala pull), `smoke_app.py` (offline smoke run), schema generation. |
| `tests/` | Integration tests and live (real-call) tests. |

## Run it

Setup, once:

```bash
python3 -m venv .venv
.venv/bin/pip install -r leadline/requirements.txt -r app/requirements.txt
(cd frontend && npm install)
cp .env.example .env            # add keys only if you want live models, web research or Cala
```

Start the service (binds to 127.0.0.1 only) and the frontend:

```bash
.venv/bin/python leadline/serve.py --db leadline/data/leadline.db --port 8765 --env-file .env
(cd frontend && npm run dev)    # LEADLINE_SERVICE_URL defaults to http://127.0.0.1:8765
```

Add `--fake-model` to the service command to run with offline answers and no web or Cala calls.

Tests:

```bash
(cd leadline && ../.venv/bin/python -m pytest -q tests)
.venv/bin/python -m pytest -q app/tests
(cd tests/integration && ../../.venv/bin/python -m pytest -q)
(cd frontend && npx tsc --noEmit && npm run build)
LEADLINE_SMOKE=1 .venv/bin/python -m pytest -q tests/integration/test_smoke_app.py   # builds and starts the app
```

## Data

Page loads only read the Leadline database; nothing on a page load calls Cala, the web or a model. Market data comes
from a cached Cala pull (`app/ingest`, loaded by `scripts/seed_db.py`). Profiles and rankings are built in the
background by the agent and stored in the database (see "The page-load rule" in `leadline/README.md`). The UI shows
whether the data is live or simulated (`GET /status`).

## Lead index

For each investor in the comparable rounds (same sector, stage and region, last 18 months):

- each round they **led** counts 1, each round they only **joined** counts 0.25
- both decay with age (about a 6-month half-life)
- the total maps to a 0–100 index that saturates

Nothing else feeds the score, so every point traces back to a listed deal (`src/lib/leadline/rank.ts`).

## Code map (`frontend/`)

| Path | What |
|---|---|
| `src/lib/cala/` | Cala shapes and entity search, Leadline queries (twins, shortlist, briefs, signals), due diligence |
| `src/lib/leadline/` | Types, ranking, twins, timing, synergy and round builder, conflict check, outreach draft, client store |
| `src/lib/cala/match.ts` | Fit report, investor thesis and breakouts, next-twins discovery |
| `src/lib/server/db.ts`, `leadline-service.ts` | Founder records and intros, through the client for the local Leadline service |
| `src/app/api/` | `twins`, `shortlist`, `investor`, `signals`, `status`, `founders`, `intros`, `funds`, `thesis`, `discover`, `fit` route handlers |
| `src/app/` | Landing, login and signup, onboarding, today, twins, investors (who to pitch and investor brief), alerts (signals), outreach, intros (founder pages in `(founder)/`); `investor/` for the investor side |

## Not built yet

- Email alerts and notifications (signals and intros are in-app only for now).
- Verifying that an investor actually works at the fund they pick.
- Password reset and email verification.
