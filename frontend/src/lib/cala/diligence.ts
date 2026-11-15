// Due diligence for investors: everything Leadline knows (its database of Cala facts) about a
// startup, framed as "should we invest?". Server-side only.

import type { Deal } from "@/lib/leadline/types";
import { stageLabel } from "@/lib/leadline/types";
import type { CompanyDiligence, DiligencePoint, FounderRecord, Intro, StartupDiligence } from "@/lib/leadline/match-types";
import { ageDays, rankInvestors } from "@/lib/leadline/rank";
import { stageKey } from "@/lib/leadline/twins";
import { fmtEur, fmtMonth } from "@/lib/leadline/format";
import { refreshCalaMode } from "./client";
import { agentMatch, computeFit, founderKey, investorKey } from "./match";
import { getComparableDeals, getCompanyRounds, getInvestorRounds, getSimilarCompanies, getTwins } from "./leadline";

const STAGE_ORDER = ["pre-seed", "seed", "series-a", "series-b", "series-c"];

function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

const sum = (xs: (number | null)[]) => xs.reduce<number>((a, b) => a + (b ?? 0), 0);

export async function startupDiligence(
  founder: FounderRecord,
  investor: string,
  intro: Intro | null,
): Promise<StartupDiligence> {
  const p = founder.profile;
  const [fit, twins, comparable] = await Promise.all([
    Promise.all([
      agentMatch(investorKey(investor), founderKey(founder.id)),
      agentMatch(founderKey(founder.id), investorKey(investor)),
    ]).then(([match, theirs]) =>
      computeFit(p, investor, match, undefined, { viewer: "investor", score: theirs?.score ?? null }),
    ),
    getTwins(p),
    getComparableDeals(p),
  ]);

  // Market: how much money flows into rounds like this one.
  const amounts = comparable.map((d) => d.amountEurM).filter((a): a is number => a != null);
  const twinsFundedLast24m = twins.twins.filter((t) => t.rounds.some((r) => ageDays(r.announced) <= 730)).length;

  // Who else is likely to want to lead this round.
  const otherLeads = rankInvestors(comparable)
    .filter((i) => i.name !== investor && i.ledCount > 0)
    .slice(0, 5)
    .map((i) => ({ name: i.name, ledCount: i.ledCount, lastLed: i.lastLed }));

  // Named competitors that raised.
  const competitors = new Set(p.competitors.map((c) => c.toLowerCase()));
  const competitorRounds = twins.twins
    .filter((t) => competitors.has(t.company.toLowerCase()))
    .flatMap((t) => t.rounds)
    .sort((a, b) => b.announced.localeCompare(a.announced));

  const strengths: DiligencePoint[] = [];
  const risks: DiligencePoint[] = [];
  const stage = stageLabel(p.stage).toLowerCase();
  const nextStage = STAGE_ORDER[STAGE_ORDER.indexOf(p.stage) + 1];

  // Precedent: did companies like this go on to raise again?
  const graduated = twins.twins.filter((t) => t.rounds.some((r) => stageKey(r.round) === nextStage));
  if (graduated.length) {
    const g = graduated[0];
    const next = g.rounds.find((r) => stageKey(r.round) === nextStage)!;
    strengths.push({
      text: `${graduated.length} of ${twins.twins.length} similar startups raised their next round after ${stage}${
        twins.monthsToNext ? `, in about ${twins.monthsToNext} months` : ""
      }. For example, ${g.company} raised ${fmtEur(next.amountEurM)} ${next.round} led by ${next.leadInvestors.join(", ")}.`,
      sources: next.sources,
    });
  } else if (twins.twins.length) {
    risks.push({ text: `None of the ${twins.twins.length} similar startups has raised a round after ${stage} yet.`, sources: [] });
  }

  // Round size vs precedent.
  const { minEurM, maxEurM, medianEurM } = twins.sameStage;
  if (minEurM != null && maxEurM != null) {
    if (p.raiseEurM > maxEurM) {
      risks.push({ text: `Raising ${fmtEur(p.raiseEurM)}, above every similar ${stage} (${fmtEur(minEurM)}–${fmtEur(maxEurM)}).`, sources: [] });
    } else if (p.raiseEurM < minEurM) {
      risks.push({ text: `Raising ${fmtEur(p.raiseEurM)}, below similar ${stage} rounds (${fmtEur(minEurM)}–${fmtEur(maxEurM)}). Runway may be short.`, sources: [] });
    } else {
      strengths.push({ text: `${fmtEur(p.raiseEurM)} is in line with similar ${stage} rounds (median ${fmtEur(medianEurM)}).`, sources: [] });
    }
  }

  // Fit with this fund.
  if (fit.portfolioTwins.length) {
    strengths.push({
      text: `You already know this space: it looks like your ${fit.portfolioTwins.map((t) => t.company).join(" and ")}.`,
      sources: fit.portfolioTwins.flatMap((t) => t.rounds.at(-1)?.sources ?? []),
    });
  }
  if (fit.synergies.length) {
    strengths.push({
      text: `${fit.synergies.length} of your portfolio companies (${fit.synergies.slice(0, 3).map((s) => s.company).join(", ")}) look like their customers: you can help them land first deals.`,
      sources: fit.synergies.flatMap((s) => s.sources).slice(0, 3),
    });
  }
  if (fit.conflict.level !== "none") {
    risks.push({ text: fit.conflict.reason ?? "Possible conflict with your portfolio.", sources: fit.conflict.sources });
  }

  // Competition.
  for (const r of competitorRounds.slice(0, 2)) {
    risks.push({
      text: `Competitor ${r.company} raised ${fmtEur(r.amountEurM)} ${r.round} in ${fmtMonth(r.announced)}, led by ${r.leadInvestors.join(", ")}.`,
      sources: r.sources,
    });
  }
  if (twinsFundedLast24m >= 5) {
    risks.push({ text: `Crowded space: ${twinsFundedLast24m} similar startups raised in the last 2 years.`, sources: [] });
  }
  if (otherLeads.length) {
    risks.push({
      text: `Competition for the lead: ${otherLeads.slice(0, 3).map((o) => o.name).join(", ")} lead rounds like this regularly.`,
      sources: [],
    });
  }

  return {
    mode: await refreshCalaMode(),
    founder: {
      id: founder.id,
      profile: p,
      founderName: founder.founderName,
      email: intro?.status === "accepted" ? founder.email : undefined,
    },
    intro,
    fit,
    twins,
    market: {
      rounds: comparable.length,
      totalEurM: Math.round(sum(amounts) * 10) / 10,
      medianEurM: median(amounts),
      twinsFundedLast24m,
    },
    otherLeads,
    competitorRounds,
    strengths,
    risks,
  };
}

export async function companyDiligence(company: string, investor: string): Promise<CompanyDiligence | null> {
  const [rounds, portfolioRounds] = await Promise.all([
    getCompanyRounds(company),
    getInvestorRounds(investor).catch(() => [] as Deal[]),
  ]);
  if (!rounds.length) return null;
  const sorted = [...rounds].sort((a, b) => a.announced.localeCompare(b.announced));
  const last = sorted.at(-1)!;
  const description = sorted.find((r) => r.companyDescription)?.companyDescription ?? "";
  const industry = sorted.find((r) => r.industry)?.industry ?? "";

  const backerMap = new Map<string, { led: number; joined: number }>();
  for (const r of sorted) {
    for (const l of r.leadInvestors) backerMap.set(l, { ...(backerMap.get(l) ?? { led: 0, joined: 0 }), led: (backerMap.get(l)?.led ?? 0) + 1 });
    for (const o of r.otherInvestors) backerMap.set(o, { ...(backerMap.get(o) ?? { led: 0, joined: 0 }), joined: (backerMap.get(o)?.joined ?? 0) + 1 });
  }
  const backers = [...backerMap.entries()].map(([name, v]) => ({ name, ...v })).sort((a, b) => b.led - a.led || b.joined - a.joined);

  const portfolio = new Set(portfolioRounds.map((d) => d.company.toLowerCase()));
  const similarDeals = await getSimilarCompanies(description, industry).catch(() => [] as Deal[]);
  const byCompany = new Map<string, Deal[]>();
  for (const d of similarDeals) if (d.company !== company) byCompany.set(d.company, [...(byCompany.get(d.company) ?? []), d]);
  const similar = [...byCompany.entries()]
    .map(([c, rs]) => ({
      company: c,
      description: rs[0].companyDescription,
      rounds: [...rs].sort((a, b) => a.announced.localeCompare(b.announced)),
      inYourPortfolio: portfolio.has(c.toLowerCase()),
    }))
    .sort((a, b) => Number(b.inYourPortfolio) - Number(a.inYourPortfolio) || b.rounds.length - a.rounds.length)
    .slice(0, 6);

  const monthsSinceLast = Math.round(ageDays(last.announced) / 30.44);
  const raisingSoon = monthsSinceLast >= 12;
  const youBacked = backerMap.has(investor);

  const strengths: DiligencePoint[] = [];
  const risks: DiligencePoint[] = [];
  const lastStage = stageKey(last.round);
  const nextStage = STAGE_ORDER[STAGE_ORDER.indexOf(lastStage) + 1];
  const graduated = similar.filter((s) => s.rounds.some((r) => stageKey(r.round) === nextStage));

  if (raisingSoon) {
    strengths.push({ text: `${monthsSinceLast} months since their ${last.round}: companies usually raise again around now. Good time to reach out.`, sources: last.sources });
  } else {
    risks.push({ text: `Raised ${last.round} only ${monthsSinceLast} months ago; probably not raising yet.`, sources: last.sources });
  }
  const inPortfolio = similar.filter((s) => s.inYourPortfolio);
  if (inPortfolio.length) {
    strengths.push({ text: `Similar to your ${inPortfolio.map((s) => s.company).join(", ")}: you know this market.`, sources: [] });
  }
  if (graduated.length) {
    const g = graduated[0];
    const next = g.rounds.find((r) => stageKey(r.round) === nextStage)!;
    strengths.push({
      text: `${graduated.length} similar startups raised a ${next.round} after ${last.round}, e.g. ${g.company} (${fmtEur(next.amountEurM)}, led by ${next.leadInvestors.join(", ")}).`,
      sources: next.sources,
    });
  }
  const strongLead = backers.find((b) => b.led > 0);
  if (strongLead && !youBacked) {
    risks.push({ text: `${strongLead.name} led before and may want to lead again (insiders often take the next round).`, sources: [] });
  }
  if (youBacked) strengths.push({ text: "You're already an investor: this is a follow-on decision.", sources: [] });
  risks.push({ text: "Not on Leadline yet: no founder profile or intro channel. Reach out directly.", sources: [] });

  return {
    mode: await refreshCalaMode(),
    company,
    description,
    industry,
    rounds: sorted,
    backers,
    monthsSinceLast,
    raisingSoon,
    youBacked,
    similar,
    strengths,
    risks,
  };
}
