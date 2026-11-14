// The two-sided engine: how well a founder fits an investor (and vice versa),
// an investor's thesis read from Cala, and startups that look like their
// breakouts. Server-side only.

import type { Deal, FounderProfile } from "@/lib/leadline/types";
import { stageLabel } from "@/lib/leadline/types";
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
import { readDb } from "@/lib/server/db";
import { calaMode } from "./client";
import { getCompanyRounds, getFunds, getInvestorRounds, getSimilarCompanies, getTwins } from "./leadline";

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

async function investorData(investor: string) {
  const [rounds, funds] = await Promise.all([
    getInvestorRounds(investor).catch(() => [] as Deal[]),
    getFunds(investor).catch(() => []),
  ]);
  const led = rounds.filter((d) => d.leadInvestors.includes(investor));
  return { rounds, led, funds, portfolio: portfolioFromDeals(rounds), timing: assessTiming(led, funds) };
}

// ── Fit report ─────────────────────────────────────────────────────────────

export async function computeFit(profile: FounderProfile, investor: string): Promise<FitReport> {
  const [data, twins] = await Promise.all([investorData(investor), getTwins(profile).catch(() => null)]);
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

  const stage = stageLabel(profile.stage).toLowerCase();
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
    label: timing.status === "deploying" ? "Deploying now" : timing.status === "slowing" ? "Slowing down" : "Steady pace",
    good: timing.status === "deploying",
    detail: timing.headline,
    sources: timing.latestFund?.sources ?? [],
  });

  const good = points.filter((p) => p.good).map((p) => p.label);
  const headline = (
    conflict.level === "direct" ? [`Backs your competitor ${conflict.company}`, ...good.slice(0, 2)] : good.slice(0, 3)
  ).join(" · ");

  return {
    investor,
    score,
    headline: headline || "Weak fit on Cala evidence",
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
    mode: calaMode(),
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
  const [thesis, db] = await Promise.all([buildThesis(investor), readDb()]);
  const rounds = await getInvestorRounds(investor).catch(() => [] as Deal[]);
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

  // Founders on Leadline: those who asked for an intro, plus opted-in ones that fit.
  const intros = db.intros.filter((i) => i.investor === investor);
  const candidatesFounders = db.founders.filter((f) => f.discoverable || intros.some((i) => i.founderId === f.id));
  const founders = (
    await Promise.all(
      candidatesFounders.map(async (f) => ({
        founder: { id: f.id, profile: f.profile, founderName: f.founderName },
        fit: await computeFit(f.profile, investor),
        intro: intros.filter((i) => i.founderId === f.id).sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0],
      })),
    )
  )
    .filter((x) => x.intro || x.fit.score >= 40)
    .sort((a, b) => b.fit.score - a.fit.score);

  return { mode: calaMode(), founders, nextTwins: nextTwins.slice(0, 8) };
}
