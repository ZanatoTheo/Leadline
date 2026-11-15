// Lead-probability ranking.
//
// For each investor in the matching deals:
//   - every round they LED counts fully, decayed by age (half-life ≈ 6 months)
//   - every round they only JOINED counts a quarter as much
// The decayed total maps to a 0–100 index that saturates, so one recent lead
// scores well and several recent leads score very high. Nothing else feeds the
// score: every point is traceable to a listed deal.

import type { Conflict, Deal, RankedInvestor } from "./types";
import { slugify } from "./types";

const DAY = 24 * 60 * 60 * 1000;
const DECAY_DAYS = 260; // e^(-180/260) ≈ 0.5 → ~6-month half-life
const JOIN_WEIGHT = 0.25;
const SATURATION = 1.6;

export function ageDays(iso: string, now = Date.now()): number {
  return Math.max(0, Math.floor((now - new Date(iso).getTime()) / DAY));
}

function recency(iso: string, now: number): number {
  return Math.exp(-ageDays(iso, now) / DECAY_DAYS);
}

export function rankInvestors(deals: Deal[], now = Date.now()): RankedInvestor[] {
  const byName = new Map<string, { led: Deal[]; joined: Deal[] }>();
  const entry = (name: string) => {
    let e = byName.get(name);
    if (!e) byName.set(name, (e = { led: [], joined: [] }));
    return e;
  };
  for (const d of deals) {
    d.leadInvestors.forEach((n) => entry(n).led.push(d));
    d.otherInvestors.forEach((n) => entry(n).joined.push(d));
  }

  const none: Conflict = { level: "none", sources: [] };
  const ranked: RankedInvestor[] = [];
  for (const [name, { led, joined }] of byName) {
    const raw =
      led.reduce((s, d) => s + recency(d.announced, now), 0) +
      joined.reduce((s, d) => s + JOIN_WEIGHT * recency(d.announced, now), 0);
    const score = Math.round(100 * (1 - Math.exp(-raw / SATURATION)));
    const lastLed = led.length ? led.map((d) => d.announced).sort().at(-1)! : null;
    const total = led.length + joined.length;

    ranked.push({
      name,
      slug: slugify(name),
      score,
      ledCount: led.length,
      joinedCount: joined.length,
      lastLed,
      leadShare: total ? led.length / total : 0,
      ledDeals: [...led].sort((a, b) => b.announced.localeCompare(a.announced)),
      joinedDeals: [...joined].sort((a, b) => b.announced.localeCompare(a.announced)),
      conflict: none,
      explanation: explain(led.length, joined.length, lastLed, now),
    });
  }
  return ranked.sort((a, b) => b.score - a.score || b.ledCount - a.ledCount || a.name.localeCompare(b.name));
}

function explain(led: number, joined: number, lastLed: string | null, now: number): string {
  if (!led) return `Joined ${joined} similar round${joined === 1 ? "" : "s"} but never led one in this data.`;
  const when = lastLed ? `most recently ${ageDays(lastLed, now)} days ago` : "";
  const join = joined ? `, joined ${joined} more` : "";
  return `Led ${led} similar round${led === 1 ? "" : "s"} (${when})${join}.`;
}

/** Still active = led a matching round within the window. */
export function isActive(inv: RankedInvestor, months: number, now = Date.now()): boolean {
  return !!inv.lastLed && ageDays(inv.lastLed, now) <= months * 30.5;
}
