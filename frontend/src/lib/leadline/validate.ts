import { REGIONS, SECTORS, STAGES, type FounderProfile } from "./types";

/** Parse an untrusted request body into a FounderProfile, or return an error message. */
export function parseProfile(input: unknown): FounderProfile | string {
  if (!input || typeof input !== "object") return "Missing founder profile.";
  const p = input as Record<string, unknown>;
  const str = (v: unknown, max = 300) => (typeof v === "string" ? v.trim().slice(0, max) : "");
  const sector = str(p.sector);
  const stage = str(p.stage);
  const region = str(p.region);
  if (!SECTORS.some((s) => s.value === sector)) return "Unknown sector.";
  if (!STAGES.some((s) => s.value === stage)) return "Unknown stage.";
  if (!REGIONS.some((r) => r.value === region)) return "Unknown region.";
  const raise = Number(p.raiseEurM);
  return {
    startupName: str(p.startupName, 80),
    oneLiner: str(p.oneLiner),
    sector: sector as FounderProfile["sector"],
    stage: stage as FounderProfile["stage"],
    region: region as FounderProfile["region"],
    location: str(p.location, 80),
    raiseEurM: Number.isFinite(raise) && raise > 0 ? raise : 0,
    competitors: Array.isArray(p.competitors)
      ? p.competitors.map((c) => str(c, 80)).filter(Boolean).slice(0, 20)
      : [],
    customers: str(p.customers, 160),
  };
}
