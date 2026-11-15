import { entitySearch } from "@/lib/cala/client";
import { withService } from "@/lib/server/leadline-service";

// "BIDRA INNOVATION VENTURES LLC" and "Bidra Innovation Ventures" are one fund: compare names without case,
// punctuation and a trailing company form.
const COMPANY_FORM = /\s+(llc|l\.l\.c\.|ltd|limited|inc|gmbh|ab|as|asa|oy|sa|sas|bv|plc|lp|llp)\.?$/i;
const sameFund = (name: string) => name.toLowerCase().replace(/[.,]/g, "").replace(COMPANY_FORM, "").trim();
const allCaps = (name: string) => name === name.toUpperCase();

/** Fund name autocomplete: organisations and investors in the Leadline database, one entry per fund. */
export const GET = withService(async (request: Request) => {
  const q = new URL(request.url).searchParams.get("q")?.trim() ?? "";
  if (q.length < 2) return Response.json({ funds: [] });
  const entities = await entitySearch(q, ["Organization", "Company", "Investor"], 8);
  // Keep one entry per fund, preferring the plainly written name (it is the one the rounds use).
  const byFund = new Map<string, { id: string; name: string }>();
  for (const e of entities) {
    const key = sameFund(e.name);
    const kept = byFund.get(key);
    if (!kept || (allCaps(kept.name) && !allCaps(e.name))) byFund.set(key, { id: e.id, name: e.name });
  }
  return Response.json({ funds: [...byFund.values()] });
});
