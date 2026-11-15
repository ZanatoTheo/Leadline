// The two-sided engine: how well a founder fits an investor (and vice versa),
// an investor's thesis read from the market data, and startups that look like
// their breakouts. Server-side only. Founder/investor scores come from the
// agent's stored rankings when the pair is ranked.

import type { Deal, FounderProfile } from "@/lib/leadline/types";
import { slugify, stageLabel } from "@/lib/leadline/types";
import type {
  Breakout,
  DiscoverResponse,
  FitReport,
  InvestorThesis,
  NextTwin,
  PortfolioTwin,
} from "@/lib/leadline/match-types";
import { checkConflict } from "@/lib/leadline/conflicts";
import { assessTiming } from "@/lib/leadline/timing";
import { coInvestors, findSynergies, portfolioFromDeals } from "@/lib/leadline/synergy";
import { stageKey } from "@/lib/leadline/twins";
import { ageDays } from "@/lib/leadline/rank";
import { fmtEur } from "@/lib/leadline/format";
import { getFounder, listIntros } from "@/lib/server/db";
import * as service from "@/lib/server/leadline-service";
import { refreshCalaMode } from "./client";
import { getCompanyRounds, getFunds, getInvestorRounds, getSimilarCompanies, getTwins, otherSideNote, withoutFactIds } from "./leadline";

const STAGE_ORDER = ["pre-seed", "seed", "series-a", "series-b", "series-c"];
const later = (a: string, b: string) => STAGE_ORDER.indexOf(stageKey(a)) > STAGE_ORDER.indexOf(stageKey(b));

function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function amounts(deals: Deal[]): number[] {
  return deals.map((d) => d.amountEurM).filter((a): a is number => a != null);
}

type InvestorData = Awaited<ReturnType<typeof investorData>>;

async function investorData(investor: string) {
  const [rounds, funds] = await Promise.all([
    getInvestorRounds(investor).catch(() => [] as Deal[]),
    getFunds(investor).catch(() => []),
  ]);
  const led = rounds.filter((d) => d.leadInvestors.includes(investor));
  return { rounds, led, funds, portfolio: portfolioFromDeals(rounds), timing: assessTiming(led, funds) };
}

// ── Fit report ─────────────────────────────────────────────────────────────

export const founderKey = (founderId: string) => `founder:${founderId}`;
export const investorKey = (investor: string) => `investor:${slugify(investor)}`;

/** What `computeFit` uses from the agent's stored match. */
export type AgentMatch = Pick<service.RankedMatch, "score" | "scoreParts" | "reasons">;

/**
 * The agent's stored match for `candidateKey` in `subjectKey`'s ranking,
 * or null when that pair isn't ranked (or the service can't say).
 */
export async function agentMatch(subjectKey: string, candidateKey: string): Promise<AgentMatch | null> {
  try {
    const state = await service.rankings(subjectKey);
    return state.ranking?.matches.find((m) => m.key === candidateKey) ?? null;
  } catch {
    return null;
  }
}

// A reason that mentions a limit or a gap is shown without the green check.
const CAUTION = /\b(not|no|never|cannot|can't|isn't|aren't|only|above|below|outside|edge|unlikely|low|loosely|weak|later)\b/i;
const PART_NAMES: Record<string, string> = {
  stage: "stage", sector: "sector", geography: "region", check_size: "check size", lead_activity: "lead activity",
};

/** The agent's reasons as fit lines: the first sentence is the label, the rest the detail. */
function agentPoints(reasons: AgentMatch["reasons"]): FitReport["points"] {
  return reasons
    .map((r) => withoutFactIds(r.text).trim())
    .filter(Boolean)
    .map((text) => {
      const m = text.match(/^(.+?[.!?])\s+(?=[A-Z0-9€$£"'])([\s\S]+)$/);
      return { label: m ? m[1] : text, detail: m ? m[2] : "", good: !CAUTION.test(text), sources: [] };
    });
}

/** "Fits on stage, sector and region" from the agent's strongest score parts. */
function agentHeadline(parts: Record<string, number>): string {
  const strong = Object.entries(parts)
    .filter(([, v]) => v >= 0.8)
    .sort((a, b) => b[1] - a[1])
    .map(([k]) => PART_NAMES[k] ?? k.replace(/_/g, " "));
  if (!strong.length) return "Ranked by the Leadline agent from both profiles";
  return `Fits on ${strong.length === 1 ? strong[0] : `${strong.slice(0, -1).join(", ")} and ${strong.at(-1)}`}`;
}

/**
 * `agent`, when the agent ranked this pair, gives the score and the first fit lines (its reasons); the
 * rule-based points follow them.
 * `preloaded` is the investor's data when the caller already has it (one load for many founders).
 * `other` is the other side's agent score for the same pair (`viewer` is who sees this card); with an agent
 * score, the first line says the score is the viewer's agent's view and what the other side's agent gave.
 */
export async function computeFit(
  profile: FounderProfile,
  investor: string,
  agent: AgentMatch | null = null,
  preloaded?: Promise<InvestorData>,
  other?: { viewer: "founder" | "investor"; score: number | null },
): Promise<FitReport> {
  const agentScoreValue = agent?.score ?? null;
  const [data, twins] = await Promise.all([preloaded ?? investorData(investor), getTwins(profile).catch(() => null)]);
  const { led, portfolio, timing } = data;

  const portfolioNames = new Set(portfolio.map((p) => p.company.toLowerCase()));
  const portfolioTwins: PortfolioTwin[] = (twins?.twins ?? [])
    .filter((t) => portfolioNames.has(t.company.toLowerCase()))
    .map((t) => ({ company: t.company, description: t.description, rounds: t.rounds }));

  const atStage = led.filter((d) => stageKey(d.round) === profile.stage);
  const checks = amounts(atStage);
  const minEurM = checks.length ? Math.min(...checks) : null;
  const maxEurM = checks.length ? Math.max(...checks) : null;
  const raiseFits =
    minEurM != null && maxEurM != null && profile.raiseEurM > 0
      ? profile.raiseEurM >= minEurM * 0.7 && profile.raiseEurM <= maxEurM * 1.3
      : null;

  const conflict = checkConflict(profile, portfolio);
  const synergies = findSynergies(profile, portfolio, conflict.company ? [conflict.company] : []);

  // Score: each part is visible in `points`, nothing hidden.
  let score = 0;
  const twinBrokeOut = portfolioTwins.some((t) => t.rounds.some((r) => later(r.round, profile.stage)));
  if (portfolioTwins.length) score += twinBrokeOut ? 30 : 22;
  score += Math.min(25, atStage.length * 8);
  score += raiseFits === true ? 15 : raiseFits === null ? 6 : 0;
  score += Math.min(15, synergies.length * 5);
  score += timing.status === "deploying" ? 15 : timing.status === "steady" ? 8 : 0;
  if (conflict.level === "possible") score -= 15;
  if (conflict.level === "direct") score = Math.min(score, 20);
  score = Math.max(0, Math.min(100, score));
  if (agentScoreValue != null) score = Math.round(100 * Math.max(0, Math.min(1, agentScoreValue)));

  // "seed", "pre-seed", but "Series A" keeps its capitals.
  const stageName = stageLabel(profile.stage);
  const stage = /^series\b/i.test(stageName) ? stageName : stageName.toLowerCase();
  const points: FitReport["points"] = [];

  if (portfolioTwins.length) {
    const t = portfolioTwins.find((x) => x.rounds.some((r) => later(r.round, profile.stage))) ?? portfolioTwins[0];
    const next = t.rounds.filter((r) => later(r.round, profile.stage)).at(-1);
    points.push({
      label: `Looks like your ${portfolioTwins.map((x) => x.company).join(" and ")}`,
      good: true,
      detail: next
        ? `${t.company} went on to raise ${fmtEur(next.amountEurM)} ${next.round} led by ${next.leadInvestors.join(", ")}.`
        : `Same problem space and customer type as a company you already backed.`,
      sources: (next ?? t.rounds.at(-1))?.sources ?? [],
    });
  } else {
    points.push({ label: "No look-alike in their portfolio", good: false, detail: "A newer space for them.", sources: [] });
  }

  points.push({
    label: atStage.length ? `Leads ${stage} rounds (${atStage.length} in 3 years)` : `Hasn't led a ${stage} round recently`,
    good: atStage.length > 0,
    detail: atStage[0]
      ? `Latest: ${atStage[0].company}, ${fmtEur(atStage[0].amountEurM)}, ${atStage[0].announced.slice(0, 7)}.`
      : "Their leads are at other stages.",
    sources: atStage[0]?.sources ?? [],
  });

  if (raiseFits !== null) {
    points.push({
      label: raiseFits ? `${fmtEur(profile.raiseEurM)} fits their check` : `${fmtEur(profile.raiseEurM)} is outside their usual check`,
      good: raiseFits,
      detail: `Their ${stage} leads range ${fmtEur(minEurM)}–${fmtEur(maxEurM)}.`,
      sources: [],
    });
  }

  points.push({
    label: conflict.level === "none" ? "No portfolio conflict" : `Conflict: ${conflict.company}`,
    good: conflict.level === "none",
    detail: conflict.reason ?? "No company in their portfolio does the same thing for the same customers.",
    sources: conflict.sources,
  });

  if (synergies.length) {
    points.push({
      label: `${synergies.length} portfolio compan${synergies.length === 1 ? "y is" : "ies are"} potential customers`,
      good: true,
      detail: synergies.slice(0, 3).map((s) => s.company).join(", "),
      sources: synergies.flatMap((s) => s.sources).slice(0, 3),
    });
  }

  points.push({
    label: { deploying: "Deploying now", slowing: "Slowing down", steady: "Steady pace", unknown: "Pace unknown" }[
      timing.status
    ],
    good: timing.status === "deploying",
    detail: timing.headline,
    sources: timing.latestFund?.sources ?? [],
  });

  const fromAgent = agent?.reasons.length ? agentPoints(agent.reasons) : [];
  let headline: string;
  if (fromAgent.length) {
    points.unshift(...fromAgent); // the agent's reasons first, then the rule-based lines
    if (other) {
      const otherName = other.viewer === "investor" ? profile.startupName : investor;
      points.unshift({
        label: `${score} is your agent's view`,
        good: false,
        detail: otherSideNote(otherName, other.score),
        sources: [],
      });
    }
    headline = [
      ...(conflict.level === "direct" ? [`Backs your competitor ${conflict.company}`] : []),
      agentHeadline(agent!.scoreParts ?? {}),
    ].join(" · ");
  } else {
    const good = points.filter((p) => p.good).map((p) => p.label);
    headline = (
      conflict.level === "direct" ? [`Backs your competitor ${conflict.company}`, ...good.slice(0, 2)] : good.slice(0, 3)
    ).join(" · ");
  }

  return {
    investor,
    score,
    headline: headline || (agentScoreValue != null ? "Ranked by the Leadline agent from both profiles" : "Weak fit on Cala evidence"),
    portfolioTwins,
    stage: { ledAtStage: atStage.length, minEurM, maxEurM, medianEurM: median(checks), raiseFits },
    conflict,
    synergies,
    timing,
    points,
  };
}

// ── Investor thesis, read from Cala ────────────────────────────────────────

const MAX_BREAKOUT_CHECKS = 20;

export async function buildThesis(investor: string): Promise<InvestorThesis> {
  const { rounds, led, timing } = await investorData(investor);
  const joined = rounds.length - led.length;

  const stageCounts = new Map<string, number>();
  for (const d of led) stageCounts.set(d.round, (stageCounts.get(d.round) ?? 0) + 1);
  const stages = [...stageCounts.entries()].map(([stage, n]) => ({ stage, led: n })).sort((a, b) => b.led - a.led);

  const industryCounts = new Map<string, number>();
  for (const d of rounds) if (d.industry) industryCounts.set(d.industry, (industryCounts.get(d.industry) ?? 0) + 1);
  const industries = [...industryCounts.entries()]
    .map(([industry, count]) => ({ industry, count }))
    .sort((a, b) => b.count - a.count);

  const mainStage = stages[0]?.stage;
  const mainChecks = amounts(led.filter((d) => d.round === mainStage));

  // Breakouts: companies that raised a later-stage round after this investor came in.
  const entries = new Map<string, Deal>();
  for (const d of [...rounds].sort((a, b) => a.announced.localeCompare(b.announced))) {
    if (!entries.has(d.company)) entries.set(d.company, d);
  }
  // Oldest bets first: they've had time to break out. Rounds they led first.
  const candidates = [...entries.values()]
    .filter((d) => ageDays(d.announced) > 180)
    .sort(
      (a, b) =>
        Number(b.leadInvestors.includes(investor)) - Number(a.leadInvestors.includes(investor)) ||
        a.announced.localeCompare(b.announced),
    )
    .slice(0, MAX_BREAKOUT_CHECKS);
  const histories = await Promise.all(candidates.map((d) => getCompanyRounds(d.company).catch(() => [] as Deal[])));
  const breakouts: Breakout[] = [];
  candidates.forEach((entry, i) => {
    const after = histories[i].filter((r) => r.announced > entry.announced && later(r.round, entry.round));
    if (after.length) {
      breakouts.push({
        company: entry.company,
        description: entry.companyDescription,
        entry,
        later: after.sort((a, b) => a.announced.localeCompare(b.announced)),
      });
    }
  });

  return {
    investor,
    mode: await refreshCalaMode(),
    roundsLed: led.length,
    roundsJoined: joined,
    leadShare: rounds.length ? led.length / rounds.length : 0,
    stages,
    industries: industries.slice(0, 6),
    typicalLeadCheck: {
      minEurM: mainChecks.length ? Math.min(...mainChecks) : null,
      maxEurM: mainChecks.length ? Math.max(...mainChecks) : null,
      medianEurM: median(mainChecks),
    },
    breakouts,
    timing,
    coInvestors: coInvestors(investor, led).map((c) => ({ name: c.name, together: c.together })),
  };
}

// ── Discovery: Leadline founders + startups like their breakouts ──────────

export async function discover(investor: string): Promise<DiscoverResponse> {
  const [thesis, state, built, mine, rounds, mode] = await Promise.all([
    buildThesis(investor),
    service.rankings(investorKey(investor)),
    service.profileStatus(investorKey(investor)).catch(() => null),
    listIntros({ investor }),
    getInvestorRounds(investor).catch(() => [] as Deal[]),
    refreshCalaMode(),
  ]);
  const portfolio = new Set(rounds.map((d) => d.company.toLowerCase()));

  // Startups that look like their breakouts and are early enough to lead.
  const seen = new Set<string>();
  const nextTwins: NextTwin[] = [];
  for (const b of thesis.breakouts.slice(0, 4)) {
    const similar = await getSimilarCompanies(b.description, b.entry.industry || "").catch(() => [] as Deal[]);
    const byCompany = new Map<string, Deal[]>();
    for (const d of similar) byCompany.set(d.company, [...(byCompany.get(d.company) ?? []), d]);
    for (const [company, rs] of byCompany) {
      const key = company.toLowerCase();
      if (portfolio.has(key) || seen.has(key)) continue;
      const sorted = [...rs].sort((a, b) => a.announced.localeCompare(b.announced));
      const last = sorted.at(-1)!;
      const lastStage = stageKey(last.round);
      if (!["pre-seed", "seed"].includes(lastStage) || ageDays(last.announced) > 730) continue;
      seen.add(key);
      const months = Math.round(ageDays(last.announced) / 30.44);
      nextTwins.push({
        company,
        description: last.companyDescription,
        looksLike: b.company,
        rounds: sorted,
        lastRound: last,
        monthsSinceLast: months,
        raisingSoon: months >= 12,
        backers: [...new Set(sorted.flatMap((r) => [...r.leadInvestors, ...r.otherInvestors]))],
      });
    }
  }
  nextTwins.sort((a, b) => Number(b.raisingSoon) - Number(a.raisingSoon) || a.monthsSinceLast - b.monthsSinceLast);

  // Founders on Leadline: the agent's ranking for this fund (opted-in founders
  // only), plus anyone with an intro to or from this fund.
  const scores = new Map(
    (state.ranking?.matches ?? [])
      .filter((m) => m.key.startsWith("founder:") && m.score != null)
      .map((m) => [m.key.slice("founder:".length), m] as const),
  );
  const ids = [...new Set([...scores.keys(), ...mine.map((i) => i.founderId)])];
  const records = (await Promise.all(ids.map((id) => getFounder(id)))).filter((f) => f !== null);
  const data = investorData(investor);
  const founders = (
    await Promise.all(
      records.map(async (f) => ({
        founder: { id: f.id, profile: f.profile, founderName: f.founderName },
        fit: await computeFit(f.profile, investor, scores.get(f.id) ?? null, data, {
          viewer: "investor",
          score: (await agentMatch(founderKey(f.id), investorKey(investor)))?.score ?? null,
        }),
        intro: mine.filter((i) => i.founderId === f.id).sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0],
      })),
    )
  )
    // The agent's ranked founders first (its scores), then founders known only through an intro (heuristic scores).
    .sort((a, b) => Number(scores.has(b.founder.id)) - Number(scores.has(a.founder.id)) || b.fit.score - a.fit.score);

  // No ranking stored yet (a fund just picked): say the agent is working, or that it failed, rather than
  // "nobody fits". Only while a profile or rank job really runs; otherwise the normal empty text stays.
  const ranking = state.ranking
    ? undefined
    : state.status === "failed" || built?.status === "failed"
      ? ("failed" as const)
      : state.status === "building" || built?.status === "building"
        ? ("building" as const)
        : undefined;
  return { mode, ranking, founders, nextTwins: nextTwins.slice(0, 8) };
}
