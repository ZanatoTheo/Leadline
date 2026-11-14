// Simulated Cala responses.
//
// Produces data in exactly the shape of Cala's /knowledge/query and
// /knowledge/search responses so the real parsing path is exercised.
// All companies, funds and publishers are FICTIONAL. Source URLs point at
// example.com. Dates are relative to today so recency, fund timing and alerts
// behave like a live feed. The generator is seeded, so results are stable.
//
// The universe is company-centric: each company raises a sequence of rounds
// over time, funds have vehicles (Fund I, II…) with close dates, and funds have
// habitual co-investors. That's what powers twins, timing and round building.

import { terms } from "@/lib/leadline/conflicts";
import type { CalaEntity, CalaQueryResponse, CalaSearchResponse, QueryHint } from "./client";

// ── Deterministic randomness ────────────────────────────────────────────────

function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function uuidFrom(text: string): string {
  let h1 = 0x811c9dc5;
  let h2 = 0x01000193;
  for (let i = 0; i < text.length; i++) {
    h1 = Math.imul(h1 ^ text.charCodeAt(i), 16777619);
    h2 = Math.imul(h2 ^ text.charCodeAt(i), 2246822519);
  }
  const hex = (n: number) => (n >>> 0).toString(16).padStart(8, "0");
  const a = hex(h1) + hex(h2) + hex(h1 ^ h2) + hex(Math.imul(h1, h2));
  return `${a.slice(0, 8)}-${a.slice(8, 12)}-4${a.slice(13, 16)}-a${a.slice(17, 20)}-${a.slice(20, 32)}`;
}

// ── Fictional universe ──────────────────────────────────────────────────────

type Sector = "climate" | "fintech" | "ai" | "health" | "saas" | "industrial";
type Stage = "pre-seed" | "seed" | "series-a" | "series-b";
type Region = "nordics" | "uk" | "dach" | "france" | "benelux" | "iberia";

interface Vehicle {
  name: string;
  sizeEurM: number;
  closedDaysAgo: number;
}

interface Fund {
  name: string;
  sectors: Sector[];
  stages: Stage[];
  leadRate: number;
  activity: number;
  friends: string[]; // habitual co-investors when this fund leads
  vehicles: Vehicle[];
}

const FUNDS: Fund[] = [
  { name: "Northwind Climate Partners", sectors: ["climate", "industrial"], stages: ["seed", "series-a"], leadRate: 0.8, activity: 3,
    friends: ["Granite Ridge Ventures", "Saltwater VC"], vehicles: [{ name: "Northwind Climate Fund I", sizeEurM: 80, closedDaysAgo: 1520 }] },
  { name: "Fjord Ventures", sectors: ["climate", "saas", "industrial"], stages: ["pre-seed", "seed"], leadRate: 0.7, activity: 3,
    friends: ["Larchmont Angels", "Saltwater VC"], vehicles: [{ name: "Fjord Ventures Fund II", sizeEurM: 60, closedDaysAgo: 210 }, { name: "Fjord Ventures Fund I", sizeEurM: 25, closedDaysAgo: 1650 }] },
  { name: "Alder Capital", sectors: ["climate", "health", "industrial"], stages: ["seed"], leadRate: 0.6, activity: 2,
    friends: ["Kestrel Capital", "Larchmont Angels"], vehicles: [{ name: "Alder Capital Fund I", sizeEurM: 45, closedDaysAgo: 900 }] },
  { name: "Kestrel Capital", sectors: ["climate", "ai", "industrial"], stages: ["seed", "series-a"], leadRate: 0.5, activity: 2,
    friends: ["Polar Light Capital", "Granite Ridge Ventures"], vehicles: [{ name: "Kestrel Capital II", sizeEurM: 150, closedDaysAgo: 400 }] },
  { name: "Polar Light Capital", sectors: ["climate", "industrial"], stages: ["series-a", "series-b"], leadRate: 0.7, activity: 2,
    friends: ["Kestrel Capital", "Granite Ridge Ventures"], vehicles: [{ name: "Polar Light Fund III", sizeEurM: 120, closedDaysAgo: 95 }, { name: "Polar Light Fund II", sizeEurM: 70, closedDaysAgo: 1400 }] },
  { name: "Saltwater VC", sectors: ["climate", "fintech"], stages: ["pre-seed", "seed"], leadRate: 0.3, activity: 3,
    friends: ["Larchmont Angels"], vehicles: [{ name: "Saltwater VC Fund II", sizeEurM: 35, closedDaysAgo: 720 }] },
  { name: "Ember Fund", sectors: ["climate"], stages: ["pre-seed", "seed"], leadRate: 0.55, activity: 2,
    friends: ["Granite Ridge Ventures", "Larchmont Angels"], vehicles: [{ name: "Ember Fund II", sizeEurM: 40, closedDaysAgo: 20 }, { name: "Ember Fund I", sizeEurM: 15, closedDaysAgo: 1300 }] },
  { name: "Granite Ridge Ventures", sectors: ["climate", "saas", "industrial"], stages: ["seed", "series-a"], leadRate: 0.15, activity: 3,
    friends: ["Saltwater VC"], vehicles: [{ name: "Granite Ridge IV", sizeEurM: 300, closedDaysAgo: 600 }] },
  { name: "Quayside Ventures", sectors: ["fintech"], stages: ["seed", "series-a"], leadRate: 0.75, activity: 3,
    friends: ["Tidewater Partners", "Wren Capital"], vehicles: [{ name: "Quayside Fund III", sizeEurM: 110, closedDaysAgo: 330 }] },
  { name: "Copperleaf Capital", sectors: ["fintech", "saas"], stages: ["seed"], leadRate: 0.6, activity: 2,
    friends: ["Wren Capital"], vehicles: [{ name: "Copperleaf Fund I", sizeEurM: 50, closedDaysAgo: 1100 }] },
  { name: "Marlow & Co Ventures", sectors: ["fintech"], stages: ["series-a", "series-b"], leadRate: 0.7, activity: 2,
    friends: ["Quayside Ventures"], vehicles: [{ name: "Marlow & Co Fund II", sizeEurM: 200, closedDaysAgo: 150 }] },
  { name: "Tidewater Partners", sectors: ["fintech", "ai"], stages: ["pre-seed", "seed"], leadRate: 0.35, activity: 3,
    friends: ["Wren Capital"], vehicles: [{ name: "Tidewater Partners I", sizeEurM: 30, closedDaysAgo: 800 }] },
  { name: "Helix Seed Fund", sectors: ["health", "ai"], stages: ["pre-seed", "seed"], leadRate: 0.7, activity: 3,
    friends: ["Juniper Seed", "Larchmont Angels"], vehicles: [{ name: "Helix Seed Fund II", sizeEurM: 55, closedDaysAgo: 260 }] },
  { name: "Juniper Seed", sectors: ["health"], stages: ["seed", "series-a"], leadRate: 0.6, activity: 2,
    friends: ["Ironbark Partners"], vehicles: [{ name: "Juniper Seed I", sizeEurM: 40, closedDaysAgo: 1250 }] },
  { name: "Ironbark Partners", sectors: ["health", "saas"], stages: ["series-a", "series-b"], leadRate: 0.65, activity: 2,
    friends: ["Juniper Seed"], vehicles: [{ name: "Ironbark Partners III", sizeEurM: 180, closedDaysAgo: 520 }] },
  { name: "Lumen Fund", sectors: ["ai"], stages: ["pre-seed", "seed"], leadRate: 0.75, activity: 3,
    friends: ["Vireo Ventures", "Tidewater Partners"], vehicles: [{ name: "Lumen Fund II", sizeEurM: 70, closedDaysAgo: 120 }] },
  { name: "Vireo Ventures", sectors: ["ai", "saas"], stages: ["seed", "series-a"], leadRate: 0.6, activity: 3,
    friends: ["Halcyon Ventures"], vehicles: [{ name: "Vireo Ventures I", sizeEurM: 90, closedDaysAgo: 950 }] },
  { name: "Halcyon Ventures", sectors: ["ai"], stages: ["series-a", "series-b"], leadRate: 0.7, activity: 2,
    friends: ["Vireo Ventures", "Bluepeak Ventures"], vehicles: [{ name: "Halcyon Ventures II", sizeEurM: 250, closedDaysAgo: 380 }] },
  { name: "Oakline Ventures", sectors: ["saas", "industrial"], stages: ["seed", "series-a"], leadRate: 0.65, activity: 3,
    friends: ["Wren Capital", "Bluepeak Ventures"], vehicles: [{ name: "Oakline Ventures III", sizeEurM: 130, closedDaysAgo: 700 }] },
  { name: "Wren Capital", sectors: ["saas", "fintech"], stages: ["pre-seed", "seed"], leadRate: 0.4, activity: 2,
    friends: ["Copperleaf Capital"], vehicles: [{ name: "Wren Capital I", sizeEurM: 20, closedDaysAgo: 1700 }] },
  { name: "Bluepeak Ventures", sectors: ["saas", "ai"], stages: ["series-a", "series-b"], leadRate: 0.6, activity: 2,
    friends: ["Oakline Ventures"], vehicles: [{ name: "Bluepeak Growth II", sizeEurM: 400, closedDaysAgo: 450 }] },
  { name: "Larchmont Angels", sectors: ["climate", "fintech", "ai", "health", "saas"], stages: ["pre-seed", "seed"], leadRate: 0.05, activity: 4,
    friends: [], vehicles: [] },
];

const FUND_BY_NAME = new Map(FUNDS.map((f) => [f.name, f]));

const INDUSTRY: Record<Sector, string> = {
  climate: "Climate tech",
  fintech: "Fintech",
  ai: "Artificial intelligence",
  health: "Healthcare",
  saas: "B2B software",
  industrial: "Manufacturing",
};

const DESCRIPTIONS: Record<Exclude<Sector, "industrial">, string[]> = {
  climate: [
    "Battery storage optimisation software for commercial solar sites",
    "Carbon removal verification using satellite and soil data",
    "Heat-pump installation marketplace for homeowners",
    "Long-duration grid energy storage using iron-air cells",
    "Low-carbon cement additives for concrete producers",
    "Charging management software for electric delivery fleets",
    "Electrolyser components for green hydrogen production",
    "Soil-carbon measurement for regenerative farms",
    "Reusable packaging logistics for e-commerce brands",
    "Building energy retrofits planned with digital twins",
    "Methane leak detection for gas networks using drones",
    "Industrial heat recovery systems for food processors",
  ],
  fintech: [
    "Embedded payroll API for European marketplaces",
    "Cash-flow forecasting for small manufacturers",
    "Cross-border B2B payments for freelancers",
    "Anti-money-laundering monitoring for neobanks",
    "Revenue-based financing for SaaS companies",
    "Spend management cards for construction firms",
    "Open-banking credit scoring for thin-file borrowers",
    "Automated VAT reconciliation for online sellers",
  ],
  ai: [
    "Domain-specific language models for legal contracts",
    "Computer vision quality inspection for factories",
    "AI agents that automate insurance claims handling",
    "Evaluation and monitoring platform for LLM applications",
    "Speech AI for multilingual customer support",
    "Synthetic training data generation for robotics",
    "AI copilots for industrial maintenance engineers",
    "Document understanding for mortgage underwriting",
  ],
  health: [
    "Remote monitoring for heart-failure patients",
    "AI triage for primary care clinics",
    "Digital therapeutics for chronic back pain",
    "Clinical trial recruitment using hospital records",
    "At-home fertility diagnostics",
    "Scheduling software for physiotherapy practices",
    "Mental health support platform for employers",
  ],
  saas: [
    "Procurement workflow software for mid-market companies",
    "Field-service scheduling for installers and technicians",
    "Customer success platform for B2B subscription businesses",
    "Compliance automation for ISO and SOC 2 audits",
    "Inventory planning for multi-site retailers",
    "Contract lifecycle management for sales teams",
    "Workforce rostering for hospitals and care homes",
  ],
};

const NAME_HEADS = [
  "Volt", "Terra", "Grid", "Helio", "Aero", "Fern", "Nimbus", "Quanta", "Orbit", "Sable", "Lumo",
  "Vanta", "Cobalt", "Arbor", "Pulse", "Mira", "Tessel", "Ondo", "Brio", "Kilo", "Zephyr",
  "Corvo", "Lyra", "Nox", "Pallas", "Rivo", "Solace", "Tundra", "Umber", "Vesta", "Wisp",
];
const NAME_TAILS = ["ly", "ia", "io", "ra", "flow", "base", "works", "loop", "metrics", "nest", "ware", "stack"];
const REGIONS: Region[] = ["nordics", "uk", "dach", "france", "benelux", "iberia"];
const PUBLISHERS = ["EU Startup Wire", "Seedline Weekly", "Climate Capital Digest", "Fintech Ledger", "Northbeam Tech News"];

const STAGE_LABEL: Record<Stage, string> = { "pre-seed": "Pre-seed", seed: "Seed", "series-a": "Series A", "series-b": "Series B" };
const NEXT_STAGE: Record<Stage, Stage | null> = { "pre-seed": "seed", seed: "series-a", "series-a": "series-b", "series-b": null };
const AMOUNT_RANGE: Record<Stage, [number, number]> = { "pre-seed": [0.3, 1.2], seed: [1, 4], "series-a": [5, 15], "series-b": [15, 40] };

export interface SimRound {
  company: string;
  description: string;
  sector: Sector;
  stage: Stage;
  region: Region;
  amountEurM: number;
  daysAgo: number;
  lead: string[];
  others: string[];
  publisher: string;
}

// ── Story data for the default demo persona ────────────────────────────────
// Persona: Carbonlens, Scope 3 emissions software for mid-size manufacturers,
// raising a €1.5M climate seed. These hand-placed companies make the demo
// show twins with clear paths, a conflict, portfolio synergies and timing.

type StoryRound = [Stage, number /*€M*/, number /*days ago*/, string[] /*lead*/, string[] /*others*/];
interface StoryCompany {
  name: string;
  description: string;
  sector: Sector;
  region: Region;
  rounds: StoryRound[];
}

const STORY: StoryCompany[] = [
  // Funding twins
  { name: "Tracely", description: "Supplier emissions tracking and Scope 3 reporting software for manufacturers", sector: "climate", region: "dach",
    rounds: [["seed", 2.2, 190, ["Northwind Climate Partners"], ["Saltwater VC", "Larchmont Angels"]]] },
  { name: "Emitrace", description: "Carbon accounting and emissions reporting for logistics companies", sector: "climate", region: "nordics",
    rounds: [["seed", 1.6, 820, ["Fjord Ventures"], ["Larchmont Angels"]], ["series-a", 7.5, 260, ["Polar Light Capital"], ["Kestrel Capital", "Fjord Ventures"]]] },
  { name: "Ledgerleaf", description: "Supplier sustainability data and Scope 3 emissions platform for retailers", sector: "climate", region: "benelux",
    rounds: [["pre-seed", 0.6, 980, ["Ember Fund"], []], ["seed", 2.4, 640, ["Alder Capital"], ["Kestrel Capital"]], ["series-a", 9, 120, ["Polar Light Capital"], ["Granite Ridge Ventures"]]] },
  { name: "Factorly", description: "Energy and emissions monitoring software for factories and manufacturers", sector: "climate", region: "dach",
    rounds: [["seed", 1.9, 700, ["Fjord Ventures"], ["Saltwater VC"]], ["series-a", 8, 300, ["Kestrel Capital"], ["Polar Light Capital", "Granite Ridge Ventures"]]] },
  { name: "Carbonomy", description: "Product carbon footprint and emissions calculations for manufacturers", sector: "climate", region: "france",
    rounds: [["seed", 1.3, 450, ["Alder Capital"], ["Larchmont Angels", "Kestrel Capital"]]] },
  { name: "Scopewise", description: "Automated Scope 3 emissions estimates from procurement data", sector: "climate", region: "uk",
    rounds: [["pre-seed", 0.5, 540, ["Ember Fund"], ["Larchmont Angels"]], ["seed", 2, 210, ["Fjord Ventures"], ["Saltwater VC", "Larchmont Angels"]]] },

  // Fresh rounds that become signals
  { name: "Gridwise Thermal", description: "Thermal battery systems that store cheap renewable power as industrial heat", sector: "climate", region: "nordics",
    rounds: [["seed", 2.6, 37, ["Northwind Climate Partners"], ["Granite Ridge Ventures"]]] },
  { name: "Heliora", description: "Energy management software for cold-storage warehouses", sector: "climate", region: "nordics",
    rounds: [["seed", 1.8, 4, ["Fjord Ventures"], ["Larchmont Angels", "Saltwater VC"]]] },
  { name: "Kelpworks", description: "Seaweed-based biomaterials replacing plastic films", sector: "climate", region: "france",
    rounds: [["seed", 1.4, 11, ["Ember Fund"], ["Granite Ridge Ventures"]]] },

  // Manufacturers in investor portfolios (potential customers → "why you")
  { name: "Alumetal", description: "Mid-size manufacturer of recycled aluminium components for carmakers", sector: "industrial", region: "dach",
    rounds: [["seed", 3, 400, ["Fjord Ventures"], ["Saltwater VC"]]] },
  { name: "Voltpack", description: "Contract manufacturer of battery packs for e-bike brands", sector: "industrial", region: "benelux",
    rounds: [["seed", 2.5, 300, ["Fjord Ventures"], ["Larchmont Angels"]]] },
  { name: "Insulo", description: "Manufacturer of bio-based insulation panels for construction", sector: "industrial", region: "nordics",
    rounds: [["seed", 2.1, 610, ["Kestrel Capital"], ["Fjord Ventures"]]] },
  { name: "Printforge", description: "Precision parts manufacturer using 3D metal printing", sector: "industrial", region: "dach",
    rounds: [["series-a", 11, 500, ["Polar Light Capital"], ["Kestrel Capital"]]] },
  { name: "Thermobloc", description: "Manufacturer of modular heat pumps for apartment blocks", sector: "industrial", region: "france",
    rounds: [["series-a", 14, 200, ["Polar Light Capital"], ["Granite Ridge Ventures"]]] },
  { name: "Robochef", description: "Factory robotics for mid-size food manufacturers", sector: "industrial", region: "iberia",
    rounds: [["seed", 1.7, 350, ["Alder Capital"], ["Larchmont Angels"]]] },
  { name: "Steelcycle", description: "Manufacturer of low-carbon steel profiles from scrap", sector: "industrial", region: "nordics",
    rounds: [["series-a", 9, 680, ["Northwind Climate Partners"], ["Polar Light Capital"]]] },
];

function pickWeighted<T>(items: T[], weight: (t: T) => number, rnd: () => number): T {
  const total = items.reduce((s, t) => s + weight(t), 0);
  let r = rnd() * total;
  for (const t of items) {
    r -= weight(t);
    if (r <= 0) return t;
  }
  return items[items.length - 1];
}

let universe: SimRound[] | null = null;

export function simUniverse(): SimRound[] {
  if (universe) return universe;
  const rnd = mulberry32(20261114);
  const rounds: SimRound[] = [];
  const pub = () => PUBLISHERS[Math.floor(rnd() * PUBLISHERS.length)];

  for (const c of STORY) {
    for (const [stage, amount, daysAgo, lead, others] of c.rounds) {
      rounds.push({ company: c.name, description: c.description, sector: c.sector, stage, region: c.region,
        amountEurM: amount, daysAgo, lead, others, publisher: pub() });
    }
  }

  const used = new Set(STORY.map((c) => c.name));
  const sectors: Exclude<Sector, "industrial">[] = ["climate", "fintech", "ai", "health", "saas"];
  const startStages: Stage[] = ["pre-seed", "seed", "series-a"];

  for (let i = 0; i < 180; i++) {
    const sector = sectors[i % sectors.length];
    let name = "";
    do {
      name = NAME_HEADS[Math.floor(rnd() * NAME_HEADS.length)] + NAME_TAILS[Math.floor(rnd() * NAME_TAILS.length)];
    } while (used.has(name));
    used.add(name);
    const description = DESCRIPTIONS[sector][Math.floor(rnd() * DESCRIPTIONS[sector].length)];
    const region = REGIONS[Math.floor(rnd() * REGIONS.length)];

    let stage: Stage | null = pickWeighted(startStages, (s) => (s === "seed" ? 5 : s === "pre-seed" ? 3 : 2), rnd);
    let daysAgo = 15 + Math.floor(Math.pow(rnd(), 1.2) * 1100);
    let previous: string[] = [];

    while (stage && daysAgo >= 0) {
      const candidates = FUNDS.filter((f) => f.sectors.includes(sector) && f.stages.includes(stage!));
      if (!candidates.length) break;
      const lead = pickWeighted(candidates, (f) => f.leadRate * f.activity * (previous.includes(f.name) ? 0.3 : 1), rnd);
      const others = new Set<string>();
      for (const friend of lead.friends) {
        const f = FUND_BY_NAME.get(friend);
        if (f && f.stages.includes(stage) && rnd() < 0.6) others.add(friend);
      }
      for (const p of previous) if (p !== lead.name && rnd() < 0.4) others.add(p);
      for (const f of candidates) if (f !== lead && rnd() < 0.12) others.add(f.name);
      const [lo, hi] = AMOUNT_RANGE[stage];

      rounds.push({
        company: name, description, sector, stage, region,
        amountEurM: Math.round((lo + rnd() * (hi - lo)) * 10) / 10,
        daysAgo, lead: [lead.name], others: [...others].slice(0, 3), publisher: pub(),
      });

      previous = [lead.name, ...others];
      if (rnd() > 0.55) break;
      daysAgo -= 380 + Math.floor(rnd() * 260);
      stage = NEXT_STAGE[stage];
      if (daysAgo < 14) break;
    }
  }
  universe = rounds;
  return rounds;
}

// ── Selection per query ─────────────────────────────────────────────────────

const REGION_FILTER: Record<string, Region[]> = { europe: REGIONS, nordics: ["nordics"], uk: ["uk"], dach: ["dach"] };

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function selectRounds(hint: QueryHint): SimRound[] {
  const all = simUniverse();
  switch (hint.kind) {
    case "rounds": {
      const regions = REGION_FILTER[hint.region] ?? REGIONS;
      return all
        .filter((r) => r.sector === hint.sector && r.stage === hint.stage && regions.includes(r.region))
        .filter((r) => r.daysAgo <= hint.withinDays);
    }
    case "investor":
      return all
        .filter((r) => r.lead.includes(hint.investor) || r.others.includes(hint.investor))
        .filter((r) => r.daysAgo <= hint.withinDays);
    case "twins": {
      const mine = terms(`${hint.description} ${hint.customers}`);
      const byCompany = new Map<string, SimRound[]>();
      for (const r of all) byCompany.set(r.company, [...(byCompany.get(r.company) ?? []), r]);
      return [...byCompany.values()]
        .map((rs) => ({ rs, overlap: [...terms(rs[0].description)].filter((t) => mine.has(t)).length }))
        .filter((x) => x.overlap >= 2 && x.rs[0].sector !== "industrial")
        .sort((a, b) => b.overlap - a.overlap)
        .slice(0, 8)
        .flatMap((x) => x.rs);
    }
    case "company":
      return all.filter((r) => r.company.toLowerCase() === hint.company.toLowerCase());
    default:
      return [];
  }
}

export function simulateEntitySearch(name: string, limit: number): CalaEntity[] {
  const q = name.toLowerCase().trim();
  if (!q) return [];
  return FUNDS.filter((f) => f.name.toLowerCase().includes(q))
    .slice(0, limit)
    .map((f) => ({ id: uuidFrom(f.name), name: f.name, entity_type: "Organization" }));
}

function sortedByDate(rounds: SimRound[]) {
  return [...rounds].sort((a, b) => a.daysAgo - b.daysAgo);
}

function docUrl(r: SimRound): string {
  return `https://example.com/simulated/${r.publisher.toLowerCase().replace(/[^a-z]+/g, "-")}/${r.company.toLowerCase().replace(/\s+/g, "-")}-${r.stage}`;
}

function entitiesFor(rounds: SimRound[]): CalaEntity[] {
  const seen = new Map<string, CalaEntity>();
  for (const r of rounds) {
    seen.set(r.company, { id: uuidFrom(r.company), name: r.company, entity_type: "Company" });
    for (const f of [...r.lead, ...r.others]) seen.set(f, { id: uuidFrom(f), name: f, entity_type: "Organization" });
  }
  return [...seen.values()];
}

interface SimFundClose {
  investor: string;
  vehicle: Vehicle;
}

function selectFundCloses(hint: QueryHint): SimFundClose[] {
  if (hint.kind === "funds") {
    return (FUND_BY_NAME.get(hint.investor)?.vehicles ?? []).map((vehicle) => ({ investor: hint.investor, vehicle }));
  }
  if (hint.kind === "fundCloses") {
    return FUNDS.filter((f) => f.sectors.includes(hint.sector as Sector)).flatMap((f) =>
      f.vehicles.filter((v) => v.closedDaysAgo <= hint.withinDays).map((vehicle) => ({ investor: f.name, vehicle })),
    );
  }
  return [];
}

function fundUrl(c: SimFundClose): string {
  return `https://example.com/simulated/fund-news/${c.vehicle.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

// ── Response builders ───────────────────────────────────────────────────────

export function simulateQuery(hint: QueryHint): CalaQueryResponse {
  if (hint.kind === "funds" || hint.kind === "fundCloses") {
    const closes = selectFundCloses(hint);
    return {
      results: closes.map((c) => ({
        investor: c.investor,
        fund_name: c.vehicle.name,
        fund_size: `€${c.vehicle.sizeEurM}M`,
        close_date: isoDaysAgo(c.vehicle.closedDaysAgo),
      })),
      entities: closes.map((c) => ({ id: uuidFrom(c.investor), name: c.investor, entity_type: "Organization" })),
    };
  }
  const rounds = sortedByDate(selectRounds(hint));
  return {
    results: rounds.map((r) => ({
      company: r.company,
      company_description: r.description,
      industry: INDUSTRY[r.sector],
      round_type: STAGE_LABEL[r.stage],
      amount: `€${r.amountEurM}M`,
      announced_date: isoDaysAgo(r.daysAgo),
      lead_investors: r.lead,
      other_investors: r.others,
    })),
    entities: entitiesFor(rounds),
  };
}

export function simulateSearch(hint: QueryHint): CalaSearchResponse {
  if (hint.kind === "funds" || hint.kind === "fundCloses") {
    const closes = selectFundCloses(hint);
    const context = closes.map((c) => ({
      id: uuidFrom(`ctx:fund:${c.vehicle.name}`),
      content: `${c.investor} closes ${c.vehicle.name} at €${c.vehicle.sizeEurM}M.`,
      origins: [{
        source: { name: "Fund Close Monitor", url: "https://example.com/simulated" },
        document: { name: `${c.investor} closes €${c.vehicle.sizeEurM}M ${c.vehicle.name}`, url: fundUrl(c) },
      }],
    }));
    const explainability = closes.map((c, i) => ({
      content: `${c.investor} closed ${c.vehicle.name} at €${c.vehicle.sizeEurM}M on ${isoDaysAgo(c.vehicle.closedDaysAgo)}.`,
      references: [context[i].id],
    }));
    return { content: explainability.map((e) => `- ${e.content}`).join("\n"), explainability, context, entities: [] };
  }

  const rounds = sortedByDate(selectRounds(hint));
  const context = rounds.map((r) => ({
    id: uuidFrom(`ctx:${r.company}:${r.stage}`),
    content: `${r.company} – €${r.amountEurM}m (${STAGE_LABEL[r.stage]}). ${r.description}.`,
    origins: [{
      source: { name: r.publisher, url: "https://example.com/simulated" },
      document: { name: `${r.company} raises €${r.amountEurM}M ${STAGE_LABEL[r.stage]} round`, url: docUrl(r) },
    }],
  }));
  const explainability = rounds.map((r, i) => ({
    content: `${r.company} raised €${r.amountEurM}M in a ${STAGE_LABEL[r.stage]} round led by ${r.lead.join(" and ")} on ${isoDaysAgo(r.daysAgo)}.`,
    references: [context[i].id],
  }));
  return {
    content: explainability.map((e) => `- ${e.content}`).join("\n"),
    explainability,
    context,
    entities: entitiesFor(rounds),
  };
}
