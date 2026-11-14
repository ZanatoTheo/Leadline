// Leadline's use of Cala: the questions we ask and how the answers become
// twins, a shortlist, investor briefs and signals. Server-side only.

import type {
  Deal,
  FounderProfile,
  FundClose,
  InvestorBrief,
  RankedInvestor,
  ShortlistResponse,
  Signal,
  SignalsResponse,
  TwinsResponse,
} from "@/lib/leadline/types";
import { regionLabel, sectorLabel, slugify, stageLabel } from "@/lib/leadline/types";
import { checkConflict } from "@/lib/leadline/conflicts";
import { ageDays, rankInvestors } from "@/lib/leadline/rank";
import { buildTwins } from "@/lib/leadline/twins";
import { assessTiming } from "@/lib/leadline/timing";
import { coInvestors, findSynergies, portfolioFromDeals } from "@/lib/leadline/synergy";
import { calaMode, knowledgeQuery, knowledgeSearch, type QueryHint } from "./client";
import { toDeals, toFundCloses } from "./normalize";

const LOOKBACK_DAYS = 540; // 18 months of comparable rounds
const INVESTOR_HISTORY_DAYS = 3 * 365;
const SIGNAL_DAYS = 30;
const ENRICH_TOP_N = 12;

const ROUND_COLUMNS =
  "Return one row per round with columns: company, company_description, industry, round_type, amount, " +
  "announced_date (YYYY-MM-DD), lead_investors, other_investors.";

// ── Questions sent to Cala ──────────────────────────────────────────────────

const ask = {
  comparableRounds: (p: FounderProfile, days: number) =>
    `List ${stageLabel(p.stage)} funding rounds raised by ${sectorLabel(p.sector)} startups in ${regionLabel(p.region)} ` +
    `announced in the last ${Math.round(days / 30)} months. ${ROUND_COLUMNS}`,
  twins: (p: FounderProfile) =>
    `List startups similar to "${p.oneLiner}" (${sectorLabel(p.sector)}${p.customers ? `, selling to ${p.customers}` : ""}) ` +
    `and every funding round each of them has raised. ${ROUND_COLUMNS}`,
  investorRounds: (investor: string) =>
    `List all funding rounds the investor ${investor} participated in during the last 3 years. ${ROUND_COLUMNS}`,
  funds: (investor: string) =>
    `List the venture funds raised by ${investor}. Return columns: investor, fund_name, fund_size, close_date (YYYY-MM-DD).`,
  similar: (description: string, sectorName: string) =>
    `List startups similar to "${description}" (${sectorName}) and every funding round each of them has raised. ${ROUND_COLUMNS}`,
  companyRounds: (company: string) => `List every funding round raised by ${company}. ${ROUND_COLUMNS}`,
  fundCloses: (p: FounderProfile, days: number) =>
    `List venture capital funds investing in ${sectorLabel(p.sector)} startups in ${regionLabel(p.region)} that closed ` +
    `in the last ${Math.round(days / 30)} months. Return columns: investor, fund_name, fund_size, close_date (YYYY-MM-DD).`,
};

async function dealsFor(question: string, hint: QueryHint): Promise<Deal[]> {
  const [rows, search] = await Promise.all([
    knowledgeQuery(question, hint),
    // Sources are a bonus: a failed search still leaves us with the rows.
    knowledgeSearch(question, hint).catch(() => null),
  ]);
  return toDeals(rows, search);
}

async function fundsFor(question: string, hint: QueryHint): Promise<FundClose[]> {
  const [rows, search] = await Promise.all([
    knowledgeQuery(question, hint),
    knowledgeSearch(question, hint).catch(() => null),
  ]);
  return toFundCloses(rows, search);
}

const withinDays = (deals: Deal[], days: number) => deals.filter((d) => ageDays(d.announced) <= days);

export async function getComparableDeals(p: FounderProfile, days = LOOKBACK_DAYS): Promise<Deal[]> {
  const hint: QueryHint = { kind: "rounds", sector: p.sector, stage: p.stage, region: p.region, withinDays: days };
  return withinDays(await dealsFor(ask.comparableRounds(p, days), hint), days);
}

export async function getInvestorRounds(investor: string): Promise<Deal[]> {
  const hint: QueryHint = { kind: "investor", investor, withinDays: INVESTOR_HISTORY_DAYS };
  return withinDays(await dealsFor(ask.investorRounds(investor), hint), INVESTOR_HISTORY_DAYS);
}

export async function getFunds(investor: string): Promise<FundClose[]> {
  return fundsFor(ask.funds(investor), { kind: "funds", investor });
}

/** Startups similar to a description, with all their rounds. */
export async function getSimilarCompanies(description: string, sector: string): Promise<Deal[]> {
  const hint: QueryHint = { kind: "twins", description, customers: "", sector };
  return dealsFor(ask.similar(description, sectorLabel(sector)), hint);
}

export async function getCompanyRounds(company: string): Promise<Deal[]> {
  return dealsFor(ask.companyRounds(company), { kind: "company", company });
}

export async function getTwins(p: FounderProfile): Promise<TwinsResponse> {
  const hint: QueryHint = { kind: "twins", description: p.oneLiner, customers: p.customers, sector: p.sector };
  return buildTwins(p, await dealsFor(ask.twins(p), hint), calaMode());
}

// ── Investor analysis ───────────────────────────────────────────────────────

async function analyseInvestor(p: FounderProfile, inv: RankedInvestor, twinDealIds: Set<string>) {
  const [rounds, funds] = await Promise.all([
    getInvestorRounds(inv.name).catch(() => [] as Deal[]),
    getFunds(inv.name).catch(() => [] as FundClose[]),
  ]);
  const led = rounds.filter((d) => d.leadInvestors.includes(inv.name));
  const portfolio = portfolioFromDeals(rounds);
  const conflict = checkConflict(p, portfolio);
  return {
    rounds,
    led,
    portfolio,
    conflict,
    timing: assessTiming(led, funds),
    synergies: findSynergies(p, portfolio, conflict.company ? [conflict.company] : []),
    coInvestors: coInvestors(inv.name, led),
    twinsLed: led.filter((d) => twinDealIds.has(d.id)),
  };
}

function twinDealIds(twins: TwinsResponse): Set<string> {
  return new Set(twins.twins.flatMap((t) => t.rounds.map((r) => r.id)));
}

export async function buildShortlist(p: FounderProfile): Promise<ShortlistResponse> {
  const [deals, twins] = await Promise.all([getComparableDeals(p), getTwins(p).catch(() => null)]);
  const ranked = rankInvestors(deals);
  const ids = twins ? twinDealIds(twins) : new Set<string>();

  const enriched = await Promise.all(
    ranked.slice(0, ENRICH_TOP_N).map(async (inv) => {
      try {
        const a = await analyseInvestor(p, inv, ids);
        return {
          ...inv,
          conflict: a.conflict,
          twinsLedCount: new Set(a.twinsLed.map((d) => d.company)).size,
          timingStatus: a.timing.status,
          timingHeadline: a.timing.headline,
          synergyCount: a.synergies.length,
        };
      } catch {
        return inv;
      }
    }),
  );
  const investors = [...enriched, ...ranked.slice(ENRICH_TOP_N)];
  const sources = new Set(deals.flatMap((d) => d.sources.map((s) => s.url)));
  return {
    mode: calaMode(),
    fetchedAt: new Date().toISOString(),
    roundsAnalysed: deals.length,
    sourcesCited: sources.size,
    investors,
  };
}

export async function getInvestorBrief(p: FounderProfile, slug: string): Promise<(InvestorBrief & { mode: string }) | null> {
  const [deals, twins] = await Promise.all([getComparableDeals(p), getTwins(p).catch(() => null)]);
  let ranked = rankInvestors(deals);
  let inv = ranked.find((i) => i.slug === slug);

  // Investors reached from a twin's path may not lead at the founder's stage.
  if (!inv && twins) {
    const name = twins.pathLeads.find((l) => l.slug === slug)?.name;
    if (name) {
      const own = await getInvestorRounds(name);
      ranked = [...ranked, ...rankInvestors(own).filter((r) => r.name === name)];
      inv = ranked.find((i) => i.slug === slug);
    }
  }
  if (!inv) return null;

  const a = await analyseInvestor(p, inv, twins ? twinDealIds(twins) : new Set());
  const rank = deals.some((d) => d.leadInvestors.includes(inv!.name) || d.otherInvestors.includes(inv!.name))
    ? rankInvestors(deals).findIndex((i) => i.slug === slug) + 1
    : 0;
  return {
    mode: calaMode(),
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
  const [deals, closes] = await Promise.all([
    getComparableDeals(p, SIGNAL_DAYS),
    fundsFor(ask.fundCloses(p, SIGNAL_DAYS), { kind: "fundCloses", sector: p.sector, withinDays: SIGNAL_DAYS }).catch(
      () => [] as FundClose[],
    ),
  ]);

  const leadSignals = await Promise.all(
    deals.flatMap((deal) =>
      deal.leadInvestors.map(async (investor): Promise<Signal> => {
        const rounds = await getInvestorRounds(investor).catch(() => [] as Deal[]);
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
      const rounds = await getInvestorRounds(fund.investor).catch(() => [] as Deal[]);
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
  return { mode: calaMode(), checkedAt: new Date().toISOString(), signals };
}
