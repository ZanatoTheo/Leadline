# Leadline — AI-Powered Fundraising Intelligence

> Built for a global hackathon. All investor data shown is **synthetic demonstration data** and does not represent real investment activity.

## Overview

Leadline answers the question every founder needs answered:

**"Which investors are most likely to lead my round, why, when should I approach them, and how can I reach them?"**

It goes beyond investor databases by profiling investor *behaviour*, detecting portfolio conflicts, mapping introduction paths, and providing an AI Fundraising Copilot grounded in real intelligence.

---

## Quick Start

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

For AI Copilot features with real OpenAI responses:
```bash
cp .env.example .env.local
# Add your OPENAI_API_KEY to .env.local
```

---

## Application Pages

| Route | Description |
|-------|-------------|
| `/` | Public landing page with interactive investor preview |
| `/onboarding` | Multi-step founder onboarding with AI analysis simulation |
| `/dashboard` | Fundraising intelligence dashboard with KPIs and charts |
| `/investors` | Ranked investor discovery with filters and scoring |
| `/investors/[id]` | Full investor DNA profile with score breakdown and evidence |
| `/syndicate` | Interactive co-investment relationship graph (React Flow) |
| `/simulator` | Fundraising scenario simulator with real-time parameter changes |
| `/copilot` | AI Fundraising Copilot with investor research and outreach drafting |
| `/alerts` | Fundraising Momentum Engine alerts and activity feed |
| `/investor-workspace` | Investor-side startup discovery workspace |

---

## Architecture

### Tech Stack
- **Framework**: Next.js 16 (App Router) + TypeScript
- **Styling**: Tailwind CSS + custom design tokens
- **UI**: shadcn/ui (Radix primitives)
- **Charts**: Recharts
- **Graph**: @xyflow/react (React Flow)
- **Animations**: Framer Motion
- **AI**: Vercel AI SDK + OpenAI (demo mode without key)
- **State**: Zustand

### AI Agent System

| Agent | Responsibility |
|-------|---------------|
| Founder Intelligence | Understands startup, sector, stage, competitors |
| Investor Research | Profiles investor history and behavioural patterns |
| Lead Scoring | Deterministic multi-dimensional scoring (6 factors) |
| Conflict Detection | Portfolio overlap analysis |
| Network Intelligence | Warm introduction path discovery |
| Fundraising Strategy | Scenario simulation and next-best-action |
| Outreach Agent | Personalised investor communications |
| Evidence Verifier | Source tracking and confidence classification |

### Lead Score Dimensions

| Dimension | Weight | Method |
|-----------|--------|--------|
| Historical lead rate | 30% | Deterministic |
| Stage compatibility | 25% | Deterministic |
| Sector fit | 20% | Deterministic + inference |
| Check-size match | 15% | Deterministic |
| Geographic compatibility | 5% | Deterministic |
| Investment activity | 5% | Deterministic |

---

## Data Transparency

All investor and company data is **synthetic demonstration data** created for hackathon purposes. It does not represent:
- Real investment activity
- Real investor behaviour
- Real company information
- Verified relationships

Every claim in the platform includes:
- Source classification
- Confidence level (Verified / Inferred / Unverified / Missing)
- Last verified date

---

## Demo Scenario

The default demo uses **Meridian AI** — a fictional AI-powered customer success platform raising a $12M Series A. Key metrics:
- $2.4M ARR, 142% NRR, 15% MoM growth
- Existing investors: First Round Capital, Y Combinator
- 10 scored investors with realistic synthetic data

---

## Commercial Strategy

**Target segments:**
1. **Founders** — Series A/B raising $5–50M
2. **Investors** — Early-stage funds wanting better deal sourcing

**Pricing model:**
- Founder Basic: $299/mo (discovery + scoring)
- Founder Pro: $799/mo (+ Copilot + syndicate explorer)
- Investor: $1,499/mo (workspace + deal signals)
- Enterprise: Custom (fund-wide deployment)

---

*Built at Junction 2026 · Synthetic data only · Not financial advice*
