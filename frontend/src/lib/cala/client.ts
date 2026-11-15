// Cala data, as the app sees it (server-side only).
//
// The TS server no longer calls Cala. Cala facts are pulled by the Leadline
// agent and stored in the Leadline database; every page reads them from the
// local Leadline service (src/lib/server/leadline-service.ts). This file keeps
// the Cala response shapes, the data mode the UI shows, and entity search.

import * as service from "@/lib/server/leadline-service";

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
 * the natural-language `input`.
 */
export type QueryHint =
  | { kind: "rounds"; sector: string; stage: string; region: string; withinDays: number }
  | { kind: "twins"; description: string; customers: string; sector: string }
  | { kind: "investor"; investor: string; withinDays: number }
  | { kind: "funds"; investor: string }
  | { kind: "fundCloses"; sector: string; withinDays: number }
  | { kind: "company"; company: string };

export type CalaMode = "live" | "simulated";

// "live" once the database holds facts pulled from Cala; read from the service's
// GET /status and kept for a minute.
const MODE_TTL_MS = 60_000;
let mode: CalaMode = "simulated";
let checkedAt = 0;
let pending: Promise<CalaMode> | null = null;

/** The data mode, re-read from the service when the cached value is over a minute old. Never throws. */
export function refreshCalaMode(): Promise<CalaMode> {
  if (Date.now() - checkedAt < MODE_TTL_MS) return Promise.resolve(mode);
  pending ??= service
    .status()
    .then((s) => (mode = s.mode === "live" ? "live" : "simulated"))
    .catch(() => mode)
    .finally(() => {
      checkedAt = Date.now();
      pending = null;
    });
  return pending;
}

/** The cached data mode (no wait); starts a refresh when it is stale. */
export function calaMode(): CalaMode {
  void refreshCalaMode();
  return mode;
}

/**
 * Names containing `name`: Cala entities in the database first, then companies
 * and investors seen in its rounds. With `entityTypes`, only those types.
 */
export async function entitySearch(name: string, entityTypes: string[] = [], limit = 8): Promise<CalaEntity[]> {
  const hits = await service.entities(name, entityTypes.length ? 50 : limit);
  const wanted = new Set(entityTypes.map((t) => t.toLowerCase()));
  return (wanted.size ? hits.filter((e) => wanted.has(e.entity_type.toLowerCase())) : hits).slice(0, limit);
}
