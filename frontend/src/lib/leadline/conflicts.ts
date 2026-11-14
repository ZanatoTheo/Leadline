// Portfolio conflict check: does this investor already back a competitor?
//
//   direct   → a portfolio company matches a competitor the founder named
//   possible → a portfolio company's description overlaps strongly with the
//              founder's one-liner (shared specific terms), worth checking
//   none     → nothing found in the investor's Cala portfolio

import type { Conflict, FounderProfile, PortfolioCompany } from "./types";

const STOPWORDS = new Set(
  (
    "with from that this into their they your over more than also using based data software platform " +
    "solution solutions tool tools management companies company startup startups system systems service " +
    "services product products help helps business businesses digital online mid size small large make makes " +
    "enable enables provider providers european europe across for and the"
  ).split(" "),
);

export function terms(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .map((t) => (t.length > 4 && t.endsWith("s") ? t.slice(0, -1) : t))
      .filter((t) => (t.length >= 4 || /^\d+$/.test(t)) && !STOPWORDS.has(t)),
  );
}

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

export function checkConflict(profile: FounderProfile, portfolio: PortfolioCompany[]): Conflict {
  const competitors = profile.competitors.map(norm).filter(Boolean);
  const direct = portfolio.find((p) => competitors.includes(norm(p.company)));
  if (direct) {
    return {
      level: "direct",
      company: direct.company,
      reason: `Backs ${direct.company}, which you listed as a competitor.`,
      sources: direct.sources,
    };
  }

  // A possible competitor does what you do AND sells to who you sell to.
  // Doing the same thing for a different customer is a neighbour, not a rival.
  const customers = terms(profile.customers ?? "");
  const product = new Set([...terms(profile.oneLiner)].filter((t) => !customers.has(t)));
  let best: { p: PortfolioCompany; shared: string[] } | null = null;
  for (const p of portfolio) {
    const theirs = terms(`${p.description} ${p.industry ?? ""}`);
    const sharedProduct = [...product].filter((t) => theirs.has(t));
    const sharedCustomers = [...customers].filter((t) => theirs.has(t));
    const isRival = customers.size
      ? sharedProduct.length >= 2 && sharedCustomers.length >= 1
      : sharedProduct.length >= 3;
    const shared = [...sharedProduct, ...sharedCustomers];
    if (isRival && (!best || shared.length > best.shared.length)) best = { p, shared };
  }
  if (best) {
    return {
      level: "possible",
      company: best.p.company,
      reason: `Backs ${best.p.company} ("${best.p.description}"), which overlaps with you on: ${best.shared.join(", ")}.`,
      sources: best.p.sources,
    };
  }
  return { level: "none", sources: [] };
}
