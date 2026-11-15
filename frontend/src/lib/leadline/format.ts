import type { Deal } from "./types";

export function fmtMonth(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });
}

export function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function fmtEur(m: number | null): string {
  if (m == null) return "undisclosed";
  if (m >= 1000) return `€${(m / 1000).toFixed(1)}B`;
  if (m < 1) return `€${Math.round(m * 1000)}K`;
  return `€${Number.isInteger(m) ? m : m.toFixed(1)}M`;
}

export function daysAgoText(days: number): string {
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 60) return `${days} days ago`;
  return `${Math.round(days / 30)} months ago`;
}

/** "Heliora's €1.8M seed" */
export function dealPhrase(d: Deal): string {
  const round = (d.round || "funding round").toLowerCase();
  const amount = d.amountEurM != null ? `${fmtEur(d.amountEurM)} ` : "";
  return `${d.company}'s ${amount}${round}`;
}
