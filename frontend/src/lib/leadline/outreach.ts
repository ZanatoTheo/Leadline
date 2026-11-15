// Outreach draft built only from sourced facts: the investor's real rounds
// (preferring rounds for the founder's twins), portfolio companies that look
// like the founder's customers, and fresh fund news. Each fact used is
// returned with its sources so the founder can check before sending.

import type { Deal, FounderProfile, InvestorBrief, Source, Synergy } from "./types";
import { sectorLabel, stageLabel } from "./types";
import { dealPhrase, fmtEur, fmtMonth } from "./format";

export interface OutreachFact {
  text: string;
  sources: Source[];
}

export interface OutreachDraft {
  subject: string;
  body: string;
  facts: OutreachFact[];
}

function list(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
}

export function draftOutreach(
  profile: FounderProfile,
  brief: InvestorBrief,
  focusDealId?: string,
  founderName?: string,
): OutreachDraft {
  const inv = brief.investor;
  const name = profile.startupName || "our startup";
  const stage = stageLabel(profile.stage).toLowerCase();
  const sector = sectorLabel(profile.sector).toLowerCase();
  const facts: OutreachFact[] = [];

  // 1. Hook: the round that makes us relevant to them.
  const allLed = [...inv.ledDeals, ...brief.twinsLed];
  const focus: Deal | undefined =
    allLed.find((d) => d.id === focusDealId) ??
    [...brief.twinsLed].sort((a, b) => b.announced.localeCompare(a.announced))[0] ??
    inv.ledDeals[0];
  let hook = `I've been following your recent ${sector} investments.`;
  if (focus) {
    const isTwin = brief.twinsLed.some((d) => d.id === focus.id);
    hook = isTwin
      ? `You led ${dealPhrase(focus)} in ${fmtMonth(focus.announced)}. We're tackling a closely related problem, a step behind where they were.`
      : `I saw you led ${dealPhrase(focus)} in ${fmtMonth(focus.announced)}.`;
    facts.push({ text: `Led ${dealPhrase(focus)}, ${fmtMonth(focus.announced)}`, sources: focus.sources });
  }

  // 2. Why you: we can help their portfolio.
  const helps: Synergy[] = brief.synergies.slice(0, 3);
  let why = "";
  if (helps.length) {
    why =
      `${list(helps.map((s) => s.company))} ${helps.length === 1 ? "is" : "are"} exactly the kind of ` +
      `${profile.customers || "company"} we sell to, so we could be useful to your portfolio from day one.`;
    for (const s of helps) facts.push({ text: `Portfolio company: ${s.company} (${s.description})`, sources: s.sources });
  }

  // 3. Why now: fresh fund.
  let now = "";
  const fund = brief.timing.latestFund;
  if (brief.timing.status === "deploying" && fund) {
    now = `Congratulations on closing ${fund.fundName}.`;
    facts.push({ text: `Closed ${fund.fundName}${fund.sizeEurM ? ` (${fmtEur(fund.sizeEurM)})` : ""}`, sources: fund.sources });
  }

  const body = [
    `Hi ${inv.name} team,`,
    "",
    [now, hook].filter(Boolean).join(" "),
    "",
    `I'm the founder of ${name}${profile.location ? `, based in ${profile.location}` : ""}. What we do: ${profile.oneLiner.replace(/\.?$/, ".")}`,
    ...(why ? ["", why] : []),
    "",
    `We're raising a ${fmtEur(profile.raiseEurM)} ${stage} round and would love you to lead it. Would you be open to a 20-minute call in the next couple of weeks? Happy to send our deck first.`,
    "",
    "Best,",
    `${founderName?.trim() || "[Your name]"}, founder of ${name}`,
  ].join("\n");

  return {
    subject: `${name}: ${fmtEur(profile.raiseEurM)} ${stage} in ${sector}`,
    body,
    facts,
  };
}
