// Cala API client (server-side only).
//
// Two transports share one interface:
//   live       → https://api.cala.ai (needs CALA_API_KEY)
//   simulated  → ./simulator.ts, which returns responses in the same shape
//
// Simulated is the default until CALA_API_KEY is set. Force it with
// CALA_MODE=simulated. The rest of the app never knows which one answered,
// so switching to real data is a config change, not a code change.

import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { simulateEntitySearch, simulateQuery, simulateSearch } from "./simulator";

const CALA_BASE = "https://api.cala.ai/v1";
const CACHE_DIR = path.join(process.cwd(), ".cala-cache");
const CACHE_TTL_MS = 12 * 60 * 60 * 1000;

export interface CalaEntity {
  id: string;
  name: string;
  entity_type: string;
}

/** POST /v1/knowledge/query */
export interface CalaQueryResponse {
  results: Record<string, unknown>[];
  entities: CalaEntity[];
}

export interface CalaOrigin {
  source: { name: string; url: string };
  document: { name: string; url: string };
}

/** POST /v1/knowledge/search */
export interface CalaSearchResponse {
  content: string;
  explainability: { content: string; references: string[] }[];
  context: { id: string; content: string; origins: CalaOrigin[] }[];
  entities: CalaEntity[];
}

/**
 * Structured description of what a query is asking. The live API only sees
 * the natural-language `input`; the simulator uses the hint to pick rows.
 */
export type QueryHint =
  | { kind: "rounds"; sector: string; stage: string; region: string; withinDays: number }
  | { kind: "twins"; description: string; customers: string; sector: string }
  | { kind: "investor"; investor: string; withinDays: number }
  | { kind: "funds"; investor: string }
  | { kind: "fundCloses"; sector: string; withinDays: number }
  | { kind: "company"; company: string };

export type CalaMode = "live" | "simulated";

export function calaMode(): CalaMode {
  if (process.env.CALA_MODE === "simulated") return "simulated";
  return process.env.CALA_API_KEY ? "live" : "simulated";
}

async function cached<T>(key: string, load: () => Promise<T>): Promise<T> {
  const file = path.join(CACHE_DIR, createHash("sha1").update(key).digest("hex") + ".json");
  try {
    const raw = JSON.parse(await readFile(file, "utf8")) as { at: number; data: T };
    if (Date.now() - raw.at < CACHE_TTL_MS) return raw.data;
  } catch {
    // cache miss
  }
  const data = await load();
  await mkdir(CACHE_DIR, { recursive: true });
  await writeFile(file, JSON.stringify({ at: Date.now(), data }));
  return data;
}

async function post<T>(endpoint: string, input: string): Promise<T> {
  return cached(`${endpoint}:${input}`, async () => {
    const res = await fetch(`${CALA_BASE}${endpoint}`, {
      method: "POST",
      headers: {
        "X-API-KEY": process.env.CALA_API_KEY ?? "",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ input }),
    });
    if (!res.ok) {
      throw new Error(`Cala ${endpoint} failed: ${res.status} ${await res.text()}`);
    }
    return (await res.json()) as T;
  });
}

export async function knowledgeQuery(input: string, hint: QueryHint): Promise<CalaQueryResponse> {
  if (calaMode() === "simulated") return simulateQuery(hint);
  return post<CalaQueryResponse>("/knowledge/query", input);
}

export async function knowledgeSearch(input: string, hint: QueryHint): Promise<CalaSearchResponse> {
  if (calaMode() === "simulated") return simulateSearch(hint);
  return post<CalaSearchResponse>("/knowledge/search", input);
}

/** GET /v1/entities?name=… — fuzzy entity search by name. */
export async function entitySearch(name: string, entityTypes: string[] = [], limit = 8): Promise<CalaEntity[]> {
  if (calaMode() === "simulated") return simulateEntitySearch(name, limit);
  const params = new URLSearchParams({ name, limit: String(limit) });
  for (const t of entityTypes) params.append("entity_types", t);
  return cached(`entities:${params}`, async () => {
    const res = await fetch(`${CALA_BASE}/entities?${params}`, {
      headers: { "X-API-KEY": process.env.CALA_API_KEY ?? "" },
    });
    if (!res.ok) throw new Error(`Cala /entities failed: ${res.status}`);
    const data = (await res.json()) as { entities: CalaEntity[] };
    return data.entities ?? [];
  });
}
