// Funding twins: startups most like the founder's, and the path they took.

import type { Deal, FounderProfile, Twin, TwinsResponse } from "./types";
import { slugify } from "./types";
import { terms } from "./conflicts";

const STAGE_ORDER = ["pre-seed", "seed", "series-a", "series-b", "series-c"];

/** "Series A" → "series-a" (best effort for free-text round names). */
export function stageKey(round: string): string {
  const r = round.toLowerCase();
  if (/pre-?seed/.test(r)) return "pre-seed";
  if (/seed/.test(r)) return "seed";
  const m = r.match(/series\s*([a-e])/);
  if (m) return `series-${m[1]}`;
  return r;
}

function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

export function buildTwins(profile: FounderProfile, deals: Deal[], mode: TwinsResponse["mode"]): TwinsResponse {
  const mine = terms(`${profile.oneLiner} ${profile.customers}`);
  const competitors = new Set(profile.competitors.map((c) => c.toLowerCase()));

  const byCompany = new Map<string, Deal[]>();
  for (const d of deals) byCompany.set(d.company, [...(byCompany.get(d.company) ?? []), d]);

  const twins: Twin[] = [...byCompany.entries()]
    .filter(([company]) => company.toLowerCase() !== profile.startupName.toLowerCase())
    .map(([company, rounds]) => {
      const description = rounds.find((r) => r.companyDescription)?.companyDescription ?? "";
      return {
        company,
        description,
        sharedTerms: [...terms(description)].filter((t) => mine.has(t)),
        rounds: [...rounds].sort((a, b) => a.announced.localeCompare(b.announced)),
      };
    })
    .filter((t) => t.sharedTerms.length >= 2)
    // Twins further along the path teach more; competitors stay but sink.
    .sort(
      (a, b) =>
        Number(competitors.has(a.company.toLowerCase())) - Number(competitors.has(b.company.toLowerCase())) ||
        b.sharedTerms.length - a.sharedTerms.length ||
        b.rounds.length - a.rounds.length,
    )
    .slice(0, 6);

  // Who led rounds on the twins' paths.
  const leads = new Map<string, { twin: string; round: string }[]>();
  for (const t of twins) {
    for (const r of t.rounds) {
      for (const l of r.leadInvestors) leads.set(l, [...(leads.get(l) ?? []), { twin: t.company, round: r.round }]);
    }
  }
  const pathLeads = [...leads.entries()]
    .map(([name, rounds]) => ({ name, slug: slugify(name), rounds }))
    .sort((a, b) => new Set(b.rounds.map((r) => r.twin)).size - new Set(a.rounds.map((r) => r.twin)).size);

  // Benchmarks at the founder's stage.
  const atStage = twins.flatMap((t) => t.rounds.filter((r) => stageKey(r.round) === profile.stage));
  const amounts = atStage.map((r) => r.amountEurM).filter((a): a is number => a != null);
  const nextStage = STAGE_ORDER[STAGE_ORDER.indexOf(profile.stage) + 1];
  const gaps: number[] = [];
  for (const t of twins) {
    const cur = t.rounds.find((r) => stageKey(r.round) === profile.stage);
    const next = t.rounds.find((r) => stageKey(r.round) === nextStage);
    if (cur && next) {
      gaps.push((new Date(next.announced).getTime() - new Date(cur.announced).getTime()) / (30.44 * 24 * 3600 * 1000));
    }
  }

  return {
    mode,
    twins,
    pathLeads,
    sameStage: {
      count: atStage.length,
      minEurM: amounts.length ? Math.min(...amounts) : null,
      maxEurM: amounts.length ? Math.max(...amounts) : null,
      medianEurM: median(amounts),
    },
    monthsToNext: gaps.length ? Math.round(median(gaps)!) : null,
    reachedNext: gaps.length,
  };
}
