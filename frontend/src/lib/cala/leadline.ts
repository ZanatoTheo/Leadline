// Leadline's market data and the agent's rankings, turned into twins, a
// shortlist, investor briefs and signals. Server-side only. Every fact comes
// from the Leadline database through the local service (never a live Cala call).

import type {
  Deal,
  FounderProfile,
  FundClose,
  InvestorBrief,
  RankedInvestor,
  ShortlistPending,
  ShortlistResponse,
  Signal,
  SignalsResponse,
  TwinsResponse,
} from "@/lib/leadline/types";
import { SECTORS, slugify } from "@/lib/leadline/types";
import { checkConflict } from "@/lib/leadline/conflicts";
import { ageDays, rankInvestors } from "@/lib/leadline/rank";
import { buildTwins } from "@/lib/leadline/twins";
import { assessTiming } from "@/lib/leadline/timing";
import { coInvestors, findSynergies, portfolioFromDeals } from "@/lib/leadline/synergy";
import * as service from "@/lib/server/leadline-service";
import { refreshCalaMode } from "./client";

const LOOKBACK_DAYS = 540; // 18 months of comparable rounds
const INVESTOR_HISTORY_DAYS = 3 * 365;
const SIGNAL_DAYS = 30;

const isSector = (s: string) => SECTORS.some((x) => x.value === s);

/** Thrown while the founder's profile or investor ranking is still being built; the route answers 202. */
export class Pending extends Error {
  constructor(public pending: ShortlistPending) {
    super(pending.message);
    this.name = "Pending";
  }
}

// ── Market data ─────────────────────────────────────────────────────────────

export function getComparableDeals(p: FounderProfile, days = LOOKBACK_DAYS): Promise<Deal[]> {
  return service.deals({ sector: p.sector, stage: p.stage, region: p.region, sinceDays: days });
}

export function getInvestorRounds(investor: string): Promise<Deal[]> {
  return service.dealsByInvestor(investor, INVESTOR_HISTORY_DAYS);
}

export function getFunds(investor: string): Promise<FundClose[]> {
  return service.funds(investor);
}

/** Startups similar to a description, with all their rounds. `sector` counts only when it is a Sector key. */
export async function getSimilarCompanies(description: string, sector: string): Promise<Deal[]> {
  if (!description.trim()) return [];
  return service.similarDeals(description, isSector(sector) ? sector : undefined);
}

export function getCompanyRounds(company: string): Promise<Deal[]> {
  return service.dealsByCompany(company);
}

export async function getTwins(p: FounderProfile): Promise<TwinsResponse> {
  const [deals, mode] = await Promise.all([
    getSimilarCompanies(`${p.oneLiner} ${p.customers}`, p.sector),
    refreshCalaMode(),
  ]);
  return buildTwins(p, deals, mode);
}

// ── Investor analysis ───────────────────────────────────────────────────────

async function analyseInvestor(p: FounderProfile, name: string, twinDealIds: Set<string>) {
  // One investor's failed lookup leaves their row thinner; it never fails the whole page.
  const [rounds, funds] = await Promise.all([
    getInvestorRounds(name).catch(() => [] as Deal[]),
    getFunds(name).catch(() => [] as FundClose[]),
  ]);
  const led = rounds.filter((d) => d.leadInvestors.includes(name));
  const portfolio = portfolioFromDeals(rounds);
  const conflict = checkConflict(p, portfolio);
  return {
    rounds,
    led,
    portfolio,
    conflict,
    timing: assessTiming(led, funds),
    synergies: findSynergies(p, portfolio, conflict.company ? [conflict.company] : []),
    coInvestors: coInvestors(name, led),
    twinsLed: led.filter((d) => twinDealIds.has(d.id)),
  };
}

function twinDealIds(twins: TwinsResponse): Set<string> {
  return new Set(twins.twins.flatMap((t) => t.rounds.map((r) => r.id)));
}

const BUILDING_PROFILE: ShortlistPending = {
  status: "building",
  step: "profile",
  message: "Researching your startup from what you entered and public sources.",
  next: "Then we rank investors for you.",
};
const BUILDING_RANKING: ShortlistPending = {
  status: "building",
  step: "ranking",
  message: "Ranking investors for your round.",
  next: null,
};
const RETRY = "Save your profile again on My startup to retry.";

// The agent cites its evidence by fact id, e.g. "(subj:f3)" or "(bidra:f3, bidra:f2)". Founders can't open those
// ids, so they are dropped from the text shown; the sources stay on the investor brief.
// Fact ids the agent cites ("subj:f5", "cand:f2"), one or more, split by "," or ";".
const ID_LIST = String.raw`[a-z][\w.-]*:[\w.-]+(?:\s*[,;]\s*[a-z][\w.-]*:[\w.-]+)*`;
const FACT_IDS = new RegExp(String.raw`\s*\(\s*${ID_LIST}\s*\)`, "gi"); // "(subj:f5, cand:f2)" -> ""
const FACT_IDS_FIRST = new RegExp(String.raw`\(\s*${ID_LIST}\s*[,;]\s*`, "gi"); // "(subj:f5, roughly" -> "(roughly"
const FACT_IDS_LAST = new RegExp(String.raw`\s*[,;]\s*${ID_LIST}\s*\)`, "gi"); // "roughly; subj:f5)" -> "roughly)"
/** The other side's agent score for the same pair, in words: "Bidra's agent scores this pair 50 from its side." */
export function otherSideNote(otherName: string, otherScore: number | null): string {
  return otherScore != null
    ? `${otherName}'s agent scores this pair ${Math.round(100 * otherScore)} from its side.`
    : `${otherName} hasn't been ranked from its side yet.`;
}

/** Agent text for people: no fact ids, and "the as_of date" (the agent's reference date) said as "today". */
export const withoutFactIds = (text: string) =>
  text
    .replace(FACT_IDS, "")
    .replace(FACT_IDS_FIRST, "(")
    .replace(FACT_IDS_LAST, ")")
    .replace(/\s+([.,;])/g, "$1")
    .replace(/\bthe as_of date\b/g, "today")
    .replace(/\bas_of\b/g, "today");

// Job error codes (from the agent run) in plain words; the raw text stays available as "Details".
const JOB_ERRORS: [RegExp, string][] = [
  [/^(model_bad_reply|model_bad_request|output_invalid)\b/, "the AI model gave an answer we couldn't use"],
  [/^budget_exceeded\b/, "the run reached its usage limit"],
  [/^cala_config/, "the company database (Cala) isn't set up correctly on our side"],
  [/^(model_unavailable|model_auth_failed|model_config_missing|request_timeout)\b/, "the AI model couldn't be reached"],
  [/^cala_/, "the company database (Cala) couldn't be reached"],
  [/^web_/, "the web search couldn't be reached"],
];

/** "<what failed>: <plain reason>. <retry> Details: <raw error>" — ErrorBox shows the details smaller. */
export function plainJobError(what: string, raw: string | undefined, retry: string): string {
  const reason = JOB_ERRORS.find(([re]) => re.test(raw ?? ""))?.[1] ?? "something went wrong on our side";
  return `${what}: ${reason}. ${retry}${raw ? ` Details: ${raw}` : ""}`;
}
const NEW_CANDIDATE = "New on Leadline, not ranked by the agent yet.";

/** An investor's own record (their last 3 years of rounds) as a shortlist row. */
function investorRow(name: string, rounds: Deal[]): RankedInvestor {
  const own = rankInvestors(rounds).find((r) => r.name === name);
  return (
    own ?? {
      name,
      slug: slugify(name),
      score: 0,
      ledCount: 0,
      joinedCount: 0,
      lastLed: null,
      leadShare: 0,
      ledDeals: [],
      joinedDeals: [],
      conflict: { level: "none", sources: [] },
      explanation: "",
    }
  );
}

/**
 * The founder's investors, in the order the agent ranked them from the stored
 * profiles; investors that entered the founder's best N since then follow,
 * marked as not ranked yet. Throws `Pending` (with the running step) until a first ranking is stored, and an
 * error that says how to retry when the profile or ranking job failed.
 */
export async function buildShortlist(p: FounderProfile, founderId: string): Promise<ShortlistResponse> {
  const [state, twins, mode] = await Promise.all([
    service.rankings(`founder:${founderId}`),
    getTwins(p).catch(() => null),
    refreshCalaMode(),
  ]);
  if (!state.ranking) {
    if (state.status === "failed") {
      throw new Error(plainJobError("Building your investor ranking failed", state.error, RETRY));
    }
    // The profile comes first: until it is stored, the ranking can't start. Saving the profile again retries it.
    const profile = await service.profileStatus(`founder:${founderId}`);
    if (profile.status === "failed") {
      throw new Error(plainJobError("Building your profile failed", profile.error, RETRY));
    }
    if (profile.status === "none") {
      // Nothing was ever queued for this founder (a save never reached the service): saving starts it.
      throw new Error("We haven't started researching your startup yet. Save your profile on My startup to start.");
    }
    throw new Pending(profile.status === "ready" ? BUILDING_RANKING : BUILDING_PROFILE);
  }
  const ranked = await Promise.all(
    state.ranking.matches
      .filter((m) => m.key.startsWith("investor:"))
      .sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity))
      .map(async (m) => {
        // The investor's own agent may score this pair differently: say so instead of hiding it.
        const theirs = await service
          .rankings(m.key)
          .then((s) => s.ranking?.matches.find((x) => x.key === `founder:${founderId}`)?.score ?? null)
          .catch(() => null);
        const reasons = withoutFactIds(m.reasons.map((r) => r.text).join(" ")) || "Ranked by the Leadline agent.";
        return {
          name: m.name,
          score: m.score, // null: not stored; the row keeps its own heuristic score
          explanation: m.score != null ? `${reasons} ${otherSideNote(m.name, theirs)}` : reasons,
        };
      }),
  );
  const fresh = state.ranking.newCandidates
    .filter((c) => c.key.startsWith("investor:"))
    .map((c) => ({ name: c.name, score: c.fit, explanation: NEW_CANDIDATE }));
  const ids = twins ? twinDealIds(twins) : new Set<string>();

  const rows = await Promise.all(
    [...ranked, ...fresh].map(async (entry) => {
      const a = await analyseInvestor(p, entry.name, ids);
      return {
        deals: a.rounds,
        investor: {
          ...investorRow(entry.name, a.rounds),
          ...(entry.score != null ? { score: Math.round(100 * entry.score) } : {}),
          explanation: entry.explanation,
          conflict: a.conflict,
          twinsLedCount: new Set(a.twinsLed.map((d) => d.company)).size,
          timingStatus: a.timing.status,
          timingHeadline: a.timing.headline,
          synergyCount: a.synergies.length,
        } satisfies RankedInvestor,
      };
    }),
  );
  const deals = new Map(rows.flatMap((r) => r.deals.map((d) => [d.id, d] as const)));
  const sources = new Set([...deals.values()].flatMap((d) => d.sources.map((s) => s.url)));
  return {
    mode,
    fetchedAt: new Date().toISOString(),
    roundsAnalysed: deals.size,
    sourcesCited: sources.size,
    investors: rows.map((r) => r.investor),
  };
}

/** The investor in the database whose name has this slug, or null. */
async function investorNamed(slug: string): Promise<string | null> {
  const word = slug.split("-").find((w) => w.length >= 2) ?? slug;
  if (!word) return null;
  const hits = await service.entities(word, 50);
  return hits.find((e) => e.entity_type === "Investor" && slugify(e.name) === slug)?.name
    ?? hits.find((e) => slugify(e.name) === slug)?.name
    ?? null;
}

/**
 * "Why them" text from the founder's agent ranking, with the investor agent's score for the same pair, or null
 * when the agent didn't rank this investor for this founder.
 */
async function agentWhyThem(founderId: string, slug: string, name: string): Promise<string | null> {
  const key = `investor:${slug}`;
  const [mine, theirs] = await Promise.all([
    service
      .rankings(`founder:${founderId}`)
      .then((s) => s.ranking?.matches.find((m) => m.key === key) ?? null)
      .catch(() => null),
    service
      .rankings(key)
      .then((s) => s.ranking?.matches.find((m) => m.key === `founder:${founderId}`)?.score ?? null)
      .catch(() => null),
  ]);
  if (!mine || mine.score == null) return null;
  const reasons = withoutFactIds(mine.reasons.map((r) => r.text).join(" "));
  return reasons ? `${reasons} ${otherSideNote(name, theirs)}` : null;
}

export async function getInvestorBrief(
  p: FounderProfile,
  slug: string,
  founderId?: string | null,
): Promise<(InvestorBrief & { mode: string }) | null> {
  const [deals, twins] = await Promise.all([getComparableDeals(p), getTwins(p).catch(() => null)]);
  let ranked = rankInvestors(deals);
  let inv = ranked.find((i) => i.slug === slug);

  // Investors reached from a twin's path, or ranked by the agent from their
  // profile, may not lead at the founder's stage: use their own rounds.
  if (!inv) {
    const name = twins?.pathLeads.find((l) => l.slug === slug)?.name ?? (await investorNamed(slug));
    if (name) {
      const own = await getInvestorRounds(name);
      ranked = [...ranked, ...rankInvestors(own).filter((r) => r.name === name)];
      inv = ranked.find((i) => i.slug === slug);
    }
  }
  if (!inv) return null;

  const [a, why] = await Promise.all([
    analyseInvestor(p, inv.name, twins ? twinDealIds(twins) : new Set()),
    founderId ? agentWhyThem(founderId, slug, inv.name) : Promise.resolve(null),
  ]);
  // The agent's reasons first; the rule-based line from the rounds data stays as its own paragraph.
  if (why) inv = { ...inv, explanation: `${why}\n\nIn the rounds data: ${inv.explanation}` };
  const rank = deals.some((d) => d.leadInvestors.includes(inv!.name) || d.otherInvestors.includes(inv!.name))
    ? rankInvestors(deals).findIndex((i) => i.slug === slug) + 1
    : 0;
  return {
    mode: await refreshCalaMode(),
    investor: { ...inv, conflict: a.conflict },
    rank,
    of: rankInvestors(deals).length,
    twinsLed: a.twinsLed,
    timing: a.timing,
    synergies: a.synergies,
    coInvestors: a.coInvestors,
    portfolio: a.portfolio,
  };
}

// ── Signals ────────────────────────────────────────────────────────────────

/** New rounds and new funds in the founder's space from the last 30 days. */
export async function getSignals(p: FounderProfile): Promise<SignalsResponse> {
  // One history per investor per page load, however many signals name them.
  const histories = new Map<string, Promise<Deal[]>>();
  const roundsOf = (investor: string) => {
    if (!histories.has(investor)) histories.set(investor, getInvestorRounds(investor).catch(() => [] as Deal[]));
    return histories.get(investor)!;
  };
  const [deals, closes] = await Promise.all([
    getComparableDeals(p, SIGNAL_DAYS),
    service.fundCloses({ sinceDays: SIGNAL_DAYS, sector: p.sector }).catch(() => [] as FundClose[]),
  ]);

  const leadSignals = await Promise.all(
    deals.flatMap((deal) =>
      deal.leadInvestors.map(async (investor): Promise<Signal> => {
        const rounds = await roundsOf(investor);
        const portfolio = portfolioFromDeals(rounds.filter((r) => r.company !== deal.company));
        const conflict = checkConflict(p, portfolio);
        return {
          id: `lead:${deal.id}:${slugify(investor)}`,
          kind: "lead",
          deal,
          investor,
          investorSlug: slugify(investor),
          daysAgo: ageDays(deal.announced),
          conflict,
          synergyCount: findSynergies(p, portfolio, conflict.company ? [conflict.company] : []).length,
        };
      }),
    ),
  );

  const fundSignals = await Promise.all(
    closes.map(async (fund): Promise<Signal> => {
      const rounds = await roundsOf(fund.investor);
      const portfolio = portfolioFromDeals(rounds);
      const conflict = checkConflict(p, portfolio);
      return {
        id: `fund:${slugify(fund.fundName)}`,
        kind: "fund",
        fund,
        investor: fund.investor,
        investorSlug: slugify(fund.investor),
        daysAgo: ageDays(fund.closed),
        conflict,
        synergyCount: findSynergies(p, portfolio, conflict.company ? [conflict.company] : []).length,
      };
    }),
  );

  const signals = [...leadSignals, ...fundSignals].sort((a, b) => a.daysAgo - b.daysAgo);
  return { mode: await refreshCalaMode(), checkedAt: new Date().toISOString(), signals };
}
