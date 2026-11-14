// Turns Cala responses into Leadline deals.
//
// knowledge_query rows have no fixed schema (columns depend on the question),
// so fields are found by name patterns. Sources come from knowledge_search:
// each explainability claim references context documents, and a claim is
// attached to a deal when it mentions that company.

import type { Deal, FundClose, Source } from "@/lib/leadline/types";
import type { CalaQueryResponse, CalaSearchResponse } from "./client";

type Row = Record<string, unknown>;

function findKey(row: Row, patterns: RegExp[], exclude?: RegExp): string | undefined {
  const keys = Object.keys(row);
  for (const p of patterns) {
    const k = keys.find((key) => p.test(key) && !(exclude && exclude.test(key)));
    if (k) return k;
  }
  return undefined;
}

function asText(v: unknown): string {
  if (v == null) return "";
  if (Array.isArray(v)) return v.map(asText).filter(Boolean).join(", ");
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    return asText(o.name ?? o.value ?? "");
  }
  return String(v).trim();
}

function asList(v: unknown): string[] {
  if (v == null) return [];
  const parts = Array.isArray(v) ? v.map(asText) : asText(v).split(/,|;|\s+and\s+/i);
  return parts.map((s) => s.trim()).filter((s) => s && !/^(n\/a|none|null|unknown|undisclosed)$/i.test(s));
}

const USD_TO_EUR = 0.92;

export function parseAmountEurM(v: unknown): number | null {
  const text = asText(v);
  if (!text) return null;
  if (typeof v === "number") return v >= 1000 ? v / 1_000_000 : v;
  const m = text.replace(/,/g, "").match(/([€$£])?\s*(\d+(?:\.\d+)?)\s*(k|m|mm|million|b|bn|billion)?/i);
  if (!m) return null;
  let n = parseFloat(m[2]);
  const unit = (m[3] ?? "").toLowerCase();
  if (unit === "k") n /= 1000;
  else if (unit.startsWith("b")) n *= 1000;
  else if (!unit && n >= 1000) n /= 1_000_000;
  if (m[1] === "$") n *= USD_TO_EUR;
  if (m[1] === "£") n *= 1.17;
  return Math.round(n * 100) / 100;
}

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

export function parseDate(v: unknown): string | null {
  const text = asText(v);
  if (!text) return null;
  const iso = text.match(/(\d{4})-(\d{2})(?:-(\d{2}))?/);
  if (iso) return `${iso[1]}-${iso[2]}-${iso[3] ?? "15"}`;
  const mon = text.toLowerCase().match(/([a-z]{3})[a-z]*\.?\s+(\d{4})/);
  if (mon && MONTHS.includes(mon[1])) {
    return `${mon[2]}-${String(MONTHS.indexOf(mon[1]) + 1).padStart(2, "0")}-15`;
  }
  const year = text.match(/\b(20\d{2})\b/);
  if (year) return `${year[1]}-07-01`;
  return null;
}

/** Map every context document to Leadline sources, keyed by context id. */
function sourcesById(search: CalaSearchResponse | null): Map<string, Source[]> {
  const map = new Map<string, Source[]>();
  for (const ctx of search?.context ?? []) {
    map.set(
      ctx.id,
      (ctx.origins ?? []).map((o) => ({
        publisher: o.source?.name ?? "Source",
        title: o.document?.name ?? ctx.content.slice(0, 80),
        url: o.document?.url ?? o.source?.url ?? "",
      })),
    );
  }
  return map;
}

/**
 * Sources for claims that mention `name`. When `date` is given, claims that
 * also mention that date win, so each round of a company gets its own source.
 */
function sourcesFor(
  name: string,
  search: CalaSearchResponse | null,
  byId: Map<string, Source[]>,
  date?: string,
): Source[] {
  const needle = name.toLowerCase();
  const claims = (search?.explainability ?? []).filter((c) => c.content.toLowerCase().includes(needle));
  const dated = date ? claims.filter((c) => c.content.includes(date)) : [];
  const out: Source[] = [];
  const seen = new Set<string>();
  for (const claim of dated.length ? dated : claims) {
    for (const ref of claim.references) {
      for (const s of byId.get(ref) ?? []) {
        if (!seen.has(s.url)) {
          seen.add(s.url);
          out.push(s);
        }
      }
    }
  }
  return out;
}

export function toDeals(query: CalaQueryResponse, search: CalaSearchResponse | null): Deal[] {
  const byId = sourcesById(search);
  const entityId = new Map((query.entities ?? []).map((e) => [e.name.toLowerCase(), e.id]));
  const deals: Deal[] = [];

  for (const row of query.results ?? []) {
    const companyKey = findKey(row, [/^company$/i, /^(company|startup)_?name$/i, /^name$/i, /startup|company|organi[sz]ation/i], /desc|sector|industry/i);
    const company = companyKey ? asText(row[companyKey]) : "";
    if (!company) continue;

    const descKey = findKey(row, [/desc/i, /focus|what/i]);
    const industryKey = findKey(row, [/industry|sector|vertical/i]);
    const roundKey = findKey(row, [/round|series|stage/i], /date|amount|investor/i);
    const amountKey = findKey(row, [/amount|raised|size|funding/i], /date|investor|round_type/i);
    const dateKey = findKey(row, [/date|announced|when/i, /year|month/i]);
    const leadKey = findKey(row, [/lead/i]);
    const othersKey = findKey(row, [/other|participa|co_?invest|follow|backer/i, /investor/i], /lead/i);

    const announced = dateKey ? parseDate(row[dateKey]) : null;
    if (!announced) continue; // ranking depends on dates; skip undated rows

    const leadInvestors = leadKey ? asList(row[leadKey]) : [];
    const otherInvestors = (othersKey ? asList(row[othersKey]) : []).filter((n) => !leadInvestors.includes(n));

    deals.push({
      id: `${company}:${announced}`.toLowerCase(),
      company,
      companyDescription: descKey ? asText(row[descKey]) : "",
      industry: industryKey ? asText(row[industryKey]) : "",
      round: roundKey ? asText(row[roundKey]) : "",
      amountEurM: amountKey ? parseAmountEurM(row[amountKey]) : null,
      announced,
      leadInvestors,
      otherInvestors,
      sources: sourcesFor(company, search, byId, announced),
      calaEntityId: entityId.get(company.toLowerCase()),
    });
  }

  // Dedupe the same round reported twice.
  const unique = new Map<string, Deal>();
  for (const d of deals) if (!unique.has(d.id)) unique.set(d.id, d);
  return [...unique.values()].sort((a, b) => b.announced.localeCompare(a.announced));
}

export function toFundCloses(query: CalaQueryResponse, search: CalaSearchResponse | null): FundClose[] {
  const byId = sourcesById(search);
  const out: FundClose[] = [];
  for (const row of query.results ?? []) {
    const investorKey = findKey(row, [/investor|firm|manager|gp/i]);
    const fundKey = findKey(row, [/fund_?name|vehicle/i, /^fund$/i, /name/i], /size|date/i);
    const sizeKey = findKey(row, [/size|amount|raised/i]);
    const dateKey = findKey(row, [/close|date|announced/i]);
    const fundName = fundKey ? asText(row[fundKey]) : "";
    const closed = dateKey ? parseDate(row[dateKey]) : null;
    if (!fundName || !closed) continue;
    out.push({
      investor: investorKey ? asText(row[investorKey]) : "",
      fundName,
      sizeEurM: sizeKey ? parseAmountEurM(row[sizeKey]) : null,
      closed,
      sources: sourcesFor(fundName, search, byId),
    });
  }
  return out.sort((a, b) => b.closed.localeCompare(a.closed));
}
