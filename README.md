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
5. **Signals** (`/alerts`): Leadline re-checks Cala every 5 minutes while open and alerts you to new rounds in your space and to funds that just closed.
6. **Outreach** (`/outreach/[slug]`): an email that cites their twin deal, their portfolio fit and their new fund, with each fact's source listed beside it.

## Accounts and roles

Founders and investors are **separate workspaces**. You sign up as one or the other (`/signup`), and log in (`/login`) straight into yours:

- **Founder workspace:** Today, Funding twins, Who to pitch, Intros, Signals, My startup (routes in `src/app/(founder)/`).
- **Investor workspace:** Today, Deal flow and Your thesis (routes in `src/app/(investor)/`).

Both roles land on **Today**: an action list, not a chart dashboard. Every line is something that changed plus the one thing to do about it. Founders see investor invites, replies and pass reasons, new rounds and fund closes in their space, and who to approach next. Investors see intro requests with fit scores, matches, look-alikes of their breakouts likely raising now, and founders who fit but haven't been contacted.

Each route group has a server layout that redirects logged-out users to login, and redirects users of the other role to their own home. Every API checks the session too: data and actions are scoped to the logged-in founder's startup or investor's fund, never to IDs sent from the browser. Passwords are hashed with scrypt, and sessions are httpOnly cookies.

**Demo accounts:** in development, the login page has one-click buttons for a ready-made founder (Carbonlens) and investor (Fjord Ventures). They're disabled in production unless `LEADLINE_DEMO_LOGIN=true`.

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

Users, sessions, founder records and intros live in `frontend/.leadline-data/db.json` (gitignored); swap for a real database before launch. Investors pick which fund they represent; verifying that they really work there (for example by work-email domain) is not built yet.

## Run it

```bash
cd frontend
npm install
cp .env.example .env.local   # add CALA_API_KEY for live data
npm run dev
```

## Data: live vs simulated

All investor data comes through `src/lib/cala/client.ts`, which talks to Cala's `/v1/knowledge/query` (structured rows) and `/v1/knowledge/search` (sources behind each claim).

- **With `CALA_API_KEY`**: live Cala data, cached for 12 hours in `frontend/.cala-cache/`.
- **Without a key** (or `CALA_MODE=simulated`): `src/lib/cala/simulator.ts` returns responses in Cala's exact shape. Every company, fund and publisher in it is fictional, source links point to example.com, and the UI shows a "simulated data" label.

The same parser (`src/lib/cala/normalize.ts`) handles both, so going live is a config change.

## Lead index

For each investor in the comparable rounds (same sector, stage and region, last 18 months):

- each round they **led** counts 1, each round they only **joined** counts 0.25
- both decay with age (about a 6-month half-life)
- the total maps to a 0–100 index that saturates

Nothing else feeds the score, so every point traces back to a listed deal (`src/lib/leadline/rank.ts`).

## Code map

| Path | What |
|---|---|
| `src/lib/cala/` | Cala client, simulator, response parser, Leadline queries |
| `src/lib/leadline/` | Types, ranking, twins, timing, synergy and round builder, conflict check, outreach draft, client store |
| `src/lib/cala/match.ts` | Fit report, investor thesis and breakouts, next-twins discovery |
| `src/lib/server/db.ts` | JSON-file store for founder records and intros |
| `src/app/api/` | `twins`, `shortlist`, `investor`, `signals`, `status`, `founders`, `intros`, `funds`, `thesis`, `discover`, `fit` route handlers |
| `src/app/` | Landing, onboarding, twins, shortlist, investor brief, signals, outreach, intros; `investor/` for the investor side |

## Not built yet

- Email alerts and notifications (signals and intros are in-app only for now).
- Verifying that an investor actually works at the fund they pick.
- Password reset and email verification.
- Live Cala responses haven't been tested yet: the parser finds fields by name pattern, so check it once a key is added.
- Live mode makes about 2 Cala calls per investor checked (rounds and funds, each with a sources search), cached for 12 hours.
