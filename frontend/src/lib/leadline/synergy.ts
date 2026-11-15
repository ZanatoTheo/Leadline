// "Why you": portfolio companies that look like the founder's customers.
// The flip side of the conflict check: a reason the investor should care.

import type { CoInvestor, Deal, FounderProfile, PortfolioCompany, Synergy } from "./types";
import { terms } from "./conflicts";

export function findSynergies(profile: FounderProfile, portfolio: PortfolioCompany[], exclude: string[] = []): Synergy[] {
  const wanted = terms(profile.customers);
  if (!wanted.size) return [];
  const skip = new Set([...exclude, ...profile.competitors].map((c) => c.toLowerCase()));
  // Terms that describe what the founder does (not who they sell to). A
  // portfolio company sharing these is a peer, not a customer.
  const product = [...terms(profile.oneLiner)].filter((t) => !wanted.has(t));
  return portfolio
    .filter((p) => !skip.has(p.company.toLowerCase()))
    .filter((p) => {
      const theirs = terms(p.description);
      return !product.some((t) => theirs.has(t));
    })
    .map((p) => ({
      company: p.company,
      description: p.description,
      industry: p.industry,
      matched: [...terms(`${p.description} ${p.industry}`)].filter((t) => wanted.has(t)),
      sources: p.sources,
    }))
    .filter((s) => s.matched.length > 0)
    .sort((a, b) => b.matched.length - a.matched.length);
}

/** Round builder: who usually invests alongside this investor when they lead. */
export function coInvestors(investor: string, ledDeals: Deal[]): CoInvestor[] {
  const counts = new Map<string, Deal[]>();
  for (const d of ledDeals) {
    for (const o of d.otherInvestors) {
      if (o === investor) continue;
      counts.set(o, [...(counts.get(o) ?? []), d]);
    }
  }
  return [...counts.entries()]
    .map(([name, deals]) => ({ name, together: deals.length, of: ledDeals.length, deals }))
    .filter((c) => c.together >= 2 || (ledDeals.length <= 3 && c.together >= 1))
    .sort((a, b) => b.together - a.together)
    .slice(0, 5);
}

/** Unique portfolio companies from an investor's rounds. */
export function portfolioFromDeals(deals: Deal[]): PortfolioCompany[] {
  const map = new Map<string, PortfolioCompany>();
  for (const d of deals) {
    const existing = map.get(d.company);
    if (existing) existing.sources.push(...d.sources.filter((s) => !existing.sources.some((e) => e.url === s.url)));
    else map.set(d.company, { company: d.company, description: d.companyDescription, industry: d.industry, sources: [...d.sources] });
  }
  return [...map.values()];
}
