# MASTER PRODUCT DEVELOPMENT PROMPT: LEADLINE

## ROLE

Act as a combination of:

1. A world-class startup founder who has built successful B2B SaaS products.
2. A venture capital analyst with deep knowledge of fundraising, investment patterns, venture funds and startup ecosystems.
3. A senior AI engineer specialising in multi-agent systems, knowledge graphs, retrieval-augmented generation (RAG) and autonomous workflows.
4. A principal product designer who creates exceptional SaaS experiences.
5. A senior full-stack engineer who can translate ambitious product concepts into production-quality applications.

Your task is to rethink, differentiate, design and architect Leadline into a genuinely innovative AI-powered venture capital intelligence platform.

Do not simply improve the existing interface. Challenge the product's assumptions, discover opportunities for differentiation and introduce capabilities that create genuine value.

---

# 1. PRODUCT CONTEXT

## Product name: Leadline

Leadline is an AI-powered fundraising intelligence platform connecting startup founders with investors who are genuinely likely to lead their funding rounds.

The problem:

Founders waste months approaching investors who:
- Do not invest in their stage or industry.
- Rarely lead funding rounds.
- Have already invested in competing companies.
- Have incompatible check sizes.
- Are not actively deploying capital.
- Cannot be reached through an effective introduction.

Existing investor databases primarily show who invests in a sector. Leadline should answer a more valuable question:

**Which investors are most likely to lead MY round, why, when should I approach them, and how can I reach them?**

Leadline uses investor histories, portfolio relationships, funding activity, company information and professional connections to provide actionable fundraising intelligence.

Its core philosophy:

"Don't just find investors. Understand them, predict their behaviour and unlock the right relationships."

## Existing product capabilities

Preserve and improve these foundations:

- Company onboarding and competitor classification.
- Investor discovery and lead probability ranking.
- Historical lead-investment analysis.
- Investor check-size matching.
- Portfolio conflict detection.
- Warm introduction mapping.
- Investor intelligence briefs.
- AI-generated introduction requests.
- Fundraising alerts.
- Investor-side discovery of companies likely to raise.
- Source-backed recommendations and transparent confidence levels.

---

# 2. PRODUCT DIFFERENTIATION

Develop the following capabilities into an integrated product.

Do not build disconnected gimmicks. Each feature must improve the founder's ability to raise capital or the investor's ability to discover opportunities.

## A. Investor DNA

Create a behavioural intelligence profile for every investor.

Go beyond their publicly stated investment thesis.

Analyse:
- Historical lead versus follow investments.
- Typical investment stages.
- Check-size patterns.
- Investment frequency.
- Sector preferences.
- Geographical preferences.
- Recurring co-investors.
- Time between investments.
- Patterns in successful and unsuccessful investments.

Generate a behavioural summary explaining how the investor actually makes investment decisions.

Distinguish observed facts from inferred behavioural patterns.

## B. Hidden Syndicate Intelligence

Create an investor relationship graph.

Identify:
- Funds that repeatedly co-invest.
- Investors who frequently follow particular lead investors.
- Investors who participate in similar funding rounds.
- Potential syndicate partners.
- Investors with strong historical relationships.

For each recommended investor, show the likely supporting investors who may participate if that investor leads the round.

The goal is to help founders understand the potential composition of their funding round before approaching investors.

## C. Raise Simulator

Build an interactive fundraising scenario simulator.

Allow founders to change:
- Target fundraising amount.
- Funding stage.
- Target sectors.
- Geographic focus.
- Fundraising timeline.
- Competitor exclusions.
- Preferred investor characteristics.

Show how each adjustment changes:
- Number of matching lead investors.
- Number of investors with conflicts.
- Number of warm introduction opportunities.
- Investor check-size compatibility.
- Potential syndicate opportunities.

Explain the trade-offs behind each scenario.

Never present estimated fundraising success as a guaranteed outcome.

## D. Fundraising Copilot

Create an AI agent that helps founders execute their fundraising strategy.

It should:
- Research selected investors.
- Prepare personalised outreach.
- Generate warm introduction requests.
- Prepare investor-specific meeting briefs.
- Generate thoughtful questions for investor meetings.
- Draft post-meeting follow-ups.
- Track conversations and fundraising stages.
- Suggest the next best action.

The agent should use actual investor intelligence from Leadline rather than generic AI-generated messages.

Require user approval before sending external communications.

## E. Evidence Radar

Make trust and transparency a central product capability.

Every important claim must have:
- Source.
- Supporting evidence.
- Last verified date.
- Confidence level.
- Classification: observed, inferred or unverified.

Allow users to inspect why a recommendation was made.

If information is missing, clearly say so.

Never fabricate investor activity, relationships, deal history or contact information.

## F. Advanced Conflict Intelligence

Improve conflict detection beyond simple competitor lists.

Identify:
- Direct competitors.
- Adjacent businesses.
- Overlapping customer segments.
- Similar products or technologies.
- Potential strategic conflicts.
- Portfolio concentration in related markets.

Show the specific portfolio companies behind each conflict.

Allow founders to override incorrect classifications with an explanation.

## G. Fundraising Momentum Engine

Build a system that monitors changes in investor behaviour.

Identify:
- Investors who recently started leading deals.
- Funds becoming active in a particular sector.
- Investors whose historical activity suggests they may be deploying capital again.
- Newly relevant investors.
- Changes in portfolio conflicts.
- Emerging co-investment relationships.

Explain why each investor's ranking has changed.

## H. Opportunity Intelligence

Create an opportunity feed that highlights investors founders might otherwise overlook.

Discover:
- Investors moving into new sectors.
- New funds with relevant investment theses.
- Investors whose portfolio overlaps are low.
- Investors with strong syndicate connections.
- Funds with newly observed lead-investment activity.

The system should favour evidence-backed opportunities over simply recommending famous funds.

---

# 3. CREATE A REAL AI AGENT ARCHITECTURE

AI must perform meaningful work, not just act as a chatbot wrapper.

Design a coordinated agent system.

Consider these specialised agents:

### 1. Founder Intelligence Agent
Understands the startup, business model, sector, stage, competitors and fundraising requirements.

### 2. Investor Research Agent
Investigates investor profiles, historical deals, investment behaviour and fund characteristics.

### 3. Lead Scoring Agent
Evaluates how likely each investor is to lead a particular round.

### 4. Conflict Detection Agent
Analyses portfolio companies and identifies competitive overlaps.

### 5. Network Intelligence Agent
Finds warm introduction paths and historical co-investment relationships.

### 6. Fundraising Strategy Agent
Simulates fundraising strategies and recommends the next best actions.

### 7. Outreach Agent
Creates contextualised investor communications and meeting preparation materials.

### 8. Evidence Verification Agent
Checks claims against available sources, tracks provenance and flags unsupported conclusions.

Define:
- Each agent's responsibilities.
- Inputs and outputs.
- Tools and data access.
- When agents communicate with one another.
- Which tasks should be deterministic rather than LLM-based.
- How conflicting agent conclusions are resolved.
- How hallucinations and unsupported conclusions are prevented.

Use a coordinator/orchestrator to manage complex workflows.

Do not use eight agents simply for architectural decoration. Consolidate agents where appropriate to keep the implementation efficient.

---

# 4. DESIGN THE PRODUCT EXPERIENCE

Create a premium, modern SaaS experience.

The design should feel like a combination of:
- A sophisticated financial intelligence platform.
- A modern AI workspace.
- An enterprise-grade analytics dashboard.

Avoid generic AI landing pages and repetitive dashboard cards.

## Design principles

- Clear visual hierarchy.
- High information density without clutter.
- Excellent typography.
- Thoughtful whitespace.
- Interactive data visualisations.
- Smooth but restrained animations.
- Consistent components.
- Responsive layouts.
- Accessible colour contrast.
- Professional financial-product aesthetics.

Use dark and light themes if practical.

## Required application pages

### Public landing page
- Clear value proposition.
- Interactive investor intelligence preview.
- Product demonstration.
- How it works.
- Features and differentiators.
- Trust and data transparency.
- Call to action.

### Founder onboarding
- Company identification.
- Company profile confirmation.
- Competitor classification.
- Investor and advisor relationships.
- Fundraising requirements.
- AI-generated company intelligence summary.

### Founder dashboard
- Fundraising overview.
- Lead investor recommendations.
- Investor activity.
- Warm introduction opportunities.
- Fundraising momentum.
- Recommended next actions.

### Investor discovery
- Ranked investor list.
- Lead-investment evidence.
- Check-size compatibility.
- Conflict indicators.
- Warm introduction routes.
- Explainable rankings.

### Investor intelligence profile
- Investor DNA.
- Historical deals.
- Co-investment network.
- Portfolio analysis.
- Conflict details.
- Evidence and confidence indicators.

### Hidden Syndicate Explorer
- Interactive investor relationship graph.
- Lead and follow relationships.
- Potential syndicate combinations.
- Historical co-investment evidence.

### Raise Simulator
- Interactive fundraising parameters.
- Scenario comparison.
- Investor pool changes.
- Strategy recommendations.

### Fundraising Copilot
- AI research workspace.
- Investor outreach generation.
- Meeting preparation.
- Follow-up generation.
- Fundraising pipeline.

### Alerts and activity
- Newly relevant investors.
- Investor activity changes.
- Portfolio conflict changes.
- New investment opportunities.

### Investor workspace
- Investment thesis generation.
- Relevant startups.
- Fundraising signals.
- Portfolio conflict checks.
- Co-investor insights.
- Founder introduction opportunities.

---

# 5. MAKE THE DATA AND RECOMMENDATIONS CREDIBLE

Leadline's competitive advantage depends on trustworthy intelligence.

Design a data architecture that supports:
- Company profiles.
- Investor and fund profiles.
- Funding rounds.
- Lead and follow investor relationships.
- Portfolio companies.
- Competitor classifications.
- Professional connections.
- Warm introduction paths.
- Source references.
- Investor behavioural patterns.
- Fundraising scenarios.
- Alerts and activity history.

Every recommendation should have a traceable explanation.

Separate:
1. Verified data.
2. Derived analytical insights.
3. AI-generated inferences.
4. Missing information.

Do not assume that a founder's LinkedIn connections, email contacts or private relationships are accessible without explicit permission and appropriate integrations.

Use publicly accessible information, licensed datasets, authorised APIs and clearly identified demonstration data.

If actual data is unavailable, create realistic synthetic seed data and clearly label it as demonstration data.

Never pretend synthetic records are verified real-world investor information.

---

# 6. TECHNICAL IMPLEMENTATION

Design the architecture for a small team of 2–3 developers building a working hackathon MVP.

Prioritise a web application.

Preferred technology:
- Frontend: Next.js, React and TypeScript.
- Styling: Tailwind CSS.
- UI components: shadcn/ui.
- Backend: Next.js server actions/API routes or a separate Node.js service where justified.
- Database: PostgreSQL.
- ORM: Prisma or Drizzle.
- Authentication: Clerk or an equivalent solution.
- AI: An LLM API with structured outputs and tool calling.
- Retrieval: RAG where appropriate.
- Graph visualisation: React Flow or an equivalent library.
- Charts: Recharts.
- Background jobs: A lightweight queue or scheduled worker.
- Deployment: Vercel or a suitable equivalent.

Do not introduce unnecessary infrastructure.

Design:
- Database schema.
- Entity relationships.
- API endpoints.
- Agent orchestration.
- Data ingestion.
- Source tracking.
- Scoring logic.
- Authentication and authorisation.
- Privacy controls.
- Error handling.

Use deterministic algorithms for measurable calculations such as check-size matching and conflict rules. Use LLMs for contextual research, interpretation and natural-language explanations.

---

# 7. CREATE A DEFENSIBLE INVESTOR MATCHING ALGORITHM

Design an explainable investor lead score.

Potential dimensions:

- Historical lead-investment behaviour.
- Stage compatibility.
- Sector compatibility.
- Check-size compatibility.
- Geographic compatibility.
- Investment activity.
- Competitive conflict.
- Warm introduction strength.
- Historical co-investment patterns.

Propose sensible initial weights, explain why they were chosen and make them configurable.

Clearly separate:
- Match score.
- Conflict status.
- Data confidence.
- Investor activity.

A high match score must not automatically imply high fundraising success probability.

Explain how missing data affects the score.

---

# 8. HACKATHON MVP STRATEGY

Do not attempt to implement every proposed feature.

Design a focused MVP that a team of 2–3 developers can actually complete during a global hackathon.

The MVP must have a complete working user journey:

1. A founder enters their startup details.
2. Leadline generates a company intelligence profile.
3. The system identifies relevant investors.
4. Each investor has an explainable lead score.
5. The platform identifies portfolio conflicts.
6. It discovers potential introduction paths using available data.
7. It generates a personalised fundraising strategy.
8. The founder can generate an investor-specific outreach request.

Prioritise the features with the greatest demonstration impact.

Include at least one genuinely impressive AI-agent workflow and one interactive data visualisation.

For every proposed feature, classify it as:
- Must build for the demo.
- Build if time permits.
- Post-hackathon roadmap.

Avoid building superficial mock buttons that do nothing.

If a capability is simulated, disclose that clearly.

---

# 9. COMMERCIAL STRATEGY

Design Leadline as a real commercial SaaS business.

Investigate:
- Primary customer segments.
- Founder willingness to pay.
- Investor willingness to pay.
- Pricing models.
- Subscription tiers.
- Potential data licensing costs


Never list claude as a co author
 do not make it look like AI, no neon gradient feeling. 2