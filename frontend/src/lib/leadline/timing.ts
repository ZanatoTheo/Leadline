// "Why now": is this investor actively deploying, from fund closes and their
// recent lead pace. Rules are simple and stated so founders can judge them.

import type { Deal, FundClose, Timing } from "./types";
import { ageDays } from "./rank";
import { fmtEur } from "./format";

const QUARTER = 91;

export function assessTiming(ledDeals: Deal[], funds: FundClose[], now = Date.now()): Timing {
  const latestFund = [...funds].sort((a, b) => b.closed.localeCompare(a.closed))[0] ?? null;
  const fundAge = latestFund ? ageDays(latestFund.closed, now) : null;

  const ages = ledDeals.map((d) => ageDays(d.announced, now));
  const leadsLast90 = ages.filter((a) => a <= QUARTER).length;
  const prior = ages.filter((a) => a > QUARTER && a <= 3 * 365).length;
  const avgLeadsPer90 = Math.round((prior / ((3 * 365 - QUARTER) / QUARTER)) * 10) / 10;
  const daysSinceLastLead = ages.length ? Math.min(...ages) : null;

  const reasons: string[] = [];
  if (latestFund && fundAge != null) {
    const months = Math.max(1, Math.round(fundAge / 30.44));
    reasons.push(
      `Closed ${latestFund.fundName}${latestFund.sizeEurM ? ` (${fmtEur(latestFund.sizeEurM)})` : ""} ${months} month${months === 1 ? "" : "s"} ago.`,
    );
  } else {
    reasons.push("No fund close found in Cala.");
  }
  reasons.push(
    `Led ${leadsLast90} round${leadsLast90 === 1 ? "" : "s"} in the last 90 days, against ${avgLeadsPer90} per quarter before that.`,
  );
  if (daysSinceLastLead != null) reasons.push(`Last lead ${daysSinceLastLead} days ago.`);

  const freshFund = fundAge != null && fundAge <= 18 * 30.44;
  const acceleratingPace = leadsLast90 >= 2 && leadsLast90 >= 1.5 * Math.max(avgLeadsPer90, 0.5);
  const oldFund = fundAge != null && fundAge > 4 * 365;
  const quiet = daysSinceLastLead == null || daysSinceLastLead > 270;

  let status: Timing["status"] = "steady";
  let headline = "Investing at their usual pace.";
  if (freshFund) {
    status = "deploying";
    const m = Math.max(1, Math.round(fundAge! / 30.44));
    headline = `New fund ${m} month${m === 1 ? "" : "s"} ago: in deployment mode.`;
  } else if (acceleratingPace) {
    status = "deploying";
    headline = "Leading more rounds than usual right now.";
  } else if (oldFund && (quiet || leadsLast90 === 0)) {
    status = "slowing";
    headline = "Late in an old fund and leading less: may be reserving for follow-ons.";
  } else if (quiet) {
    status = "slowing";
    headline = "Hasn't led a round in 9+ months.";
  } else if (oldFund) {
    headline = "Still leading, but their latest fund is 4+ years old.";
  }

  return { status, headline, latestFund, leadsLast90, avgLeadsPer90, daysSinceLastLead, reasons };
}
