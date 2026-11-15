// Shared Leadline types. Everything the UI shows is derived from Cala
// responses (real or simulated) — there is no hand-written investor data.

export type Stage = "pre-seed" | "seed" | "series-a" | "series-b";

export const STAGES: { value: Stage; label: string }[] = [
  { value: "pre-seed", label: "Pre-seed" },
  { value: "seed", label: "Seed" },
  { value: "series-a", label: "Series A" },
  { value: "series-b", label: "Series B" },
];

export const SECTORS = [
  { value: "climate", label: "Climate tech" },
  { value: "fintech", label: "Fintech" },
  { value: "ai", label: "AI / ML" },
  { value: "health", label: "Healthtech" },
  { value: "saas", label: "B2B SaaS" },
] as const;
export type Sector = (typeof SECTORS)[number]["value"];

export const REGIONS = [
  { value: "europe", label: "Europe" },
  { value: "nordics", label: "Nordics" },
  { value: "uk", label: "UK & Ireland" },
  { value: "dach", label: "DACH" },
] as const;
export type Region = (typeof REGIONS)[number]["value"];

export interface FounderProfile {
  startupName: string;
  oneLiner: string;
  sector: Sector;
  stage: Stage;
  location: string;
  region: Region;
  raiseEurM: number;
  competitors: string[];
  /** Who the startup sells to, e.g. "mid-size manufacturers". */
  customers: string;
}

/** A document Cala cites for a claim. */
export interface Source {
  publisher: string;
  title: string;
  url: string;
}

export interface Deal {
  id: string;
  company: string;
  companyDescription: string;
  industry: string;
  round: string;
  amountEurM: number | null;
  announced: string; // ISO date
  leadInvestors: string[];
  otherInvestors: string[];
  sources: Source[];
  calaEntityId?: string;
}

export interface PortfolioCompany {
  company: string;
  description: string;
  industry: string;
  sources: Source[];
}

export interface FundClose {
  investor: string;
  fundName: string;
  sizeEurM: number | null;
  closed: string; // ISO date
  sources: Source[];
}

/** A startup that was where the founder is now, and the rounds it raised. */
export interface Twin {
  company: string;
  description: string;
  sharedTerms: string[];
  rounds: Deal[]; // oldest first
}

export interface TwinsResponse {
  mode: "live" | "simulated";
  twins: Twin[];
  /** Investors who led a round for any twin, most twins first. */
  pathLeads: { name: string; slug: string; rounds: { twin: string; round: string }[] }[];
  /** Twins' rounds at the founder's stage. */
  sameStage: { count: number; minEurM: number | null; maxEurM: number | null; medianEurM: number | null };
  /** Months from the founder's stage to the next round, for twins that made it. */
  monthsToNext: number | null;
  reachedNext: number;
}

/** "unknown": no leads in the data and no fresh fund, so the pace can't be judged. */
export type TimingStatus = "deploying" | "steady" | "slowing" | "unknown";

export interface Timing {
  status: TimingStatus;
  headline: string;
  latestFund: FundClose | null;
  leadsLast90: number;
  avgLeadsPer90: number;
  daysSinceLastLead: number | null;
  reasons: string[];
}

export interface Synergy {
  company: string;
  description: string;
  industry: string;
  matched: string[];
  sources: Source[];
}

export interface CoInvestor {
  name: string;
  together: number;
  of: number;
  deals: Deal[];
}

export interface InvestorBrief {
  investor: RankedInvestor;
  rank: number;
  of: number;
  twinsLed: Deal[];
  timing: Timing;
  synergies: Synergy[];
  coInvestors: CoInvestor[];
  portfolio: PortfolioCompany[];
}

export type ConflictLevel = "none" | "possible" | "direct";

export interface Conflict {
  level: ConflictLevel;
  company?: string;
  reason?: string;
  sources: Source[];
}

export interface RankedInvestor {
  name: string;
  slug: string;
  score: number; // 0–100 lead probability index
  ledCount: number;
  joinedCount: number;
  lastLed: string | null; // ISO date
  leadShare: number; // 0–1
  ledDeals: Deal[];
  joinedDeals: Deal[];
  conflict: Conflict;
  explanation: string;
  /** Filled in for the top of the shortlist. */
  twinsLedCount?: number;
  timingStatus?: TimingStatus;
  timingHeadline?: string;
  synergyCount?: number;
}

export interface ShortlistResponse {
  mode: "live" | "simulated";
  fetchedAt: string;
  roundsAnalysed: number;
  sourcesCited: number;
  investors: RankedInvestor[];
}

/** `/api/shortlist` answers this with HTTP 202 while the agent is still working on the founder's data. */
export interface ShortlistPending {
  status: "building";
  /** The step running now: the founder's profile first, then the investor ranking. */
  step: "profile" | "ranking";
  /** What is happening now, in plain words. */
  message: string;
  /** What comes after this step, or null when it is the last one. */
  next: string | null;
}

export interface Signal {
  id: string;
  kind: "lead" | "fund";
  investor: string;
  investorSlug: string;
  daysAgo: number;
  conflict: Conflict;
  deal?: Deal; // kind = lead
  fund?: FundClose; // kind = fund
  synergyCount?: number;
}

export interface SignalsResponse {
  mode: "live" | "simulated";
  checkedAt: string;
  signals: Signal[];
}

export function slugify(name: string): string {
  return name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

export function stageLabel(stage: string): string {
  return STAGES.find((s) => s.value === stage)?.label ?? stage;
}

export function sectorLabel(sector: string): string {
  return SECTORS.find((s) => s.value === sector)?.label ?? sector;
}

export function regionLabel(region: string): string {
  return REGIONS.find((r) => r.value === region)?.label ?? region;
}
