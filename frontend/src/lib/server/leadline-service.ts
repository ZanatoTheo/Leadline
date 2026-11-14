// Server-only client for the local Leadline service (leadline/serve.py, bound to
// 127.0.0.1). The service owns the database: accounts, sessions, founder
// records, intros, market data, and the agent's stored profiles and rankings.
// Every helper returns the frontend's own types; the service builds them.

import type { Deal, FounderProfile, FundClose } from "@/lib/leadline/types";
import type { FounderRecord, Intro } from "@/lib/leadline/match-types";
import type { Role, User } from "./db";

const TIMEOUT_MS = 10_000;

/** A non-2xx answer from the service (status 503 when it can't be reached). */
export class ServiceError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ServiceError";
  }
}

const baseUrl = () => (process.env.LEADLINE_SERVICE_URL ?? "http://127.0.0.1:8765").replace(/\/+$/, "");

/** One JSON call to the service. Never cached: every page load reads the database as it is now. */
export async function svc<T>(method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(baseUrl() + path, {
      method,
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (err) {
    if ((err as Error).name === "TimeoutError") throw new ServiceError(503, "Leadline is taking too long to answer. Try again in a minute. Details: service timeout");
    throw new ServiceError(503, "Leadline is not reachable right now. Try again in a minute. Details: service not reachable");
  }
  if (res.status === 204) return undefined as T;
  let data: { error?: unknown } | null;
  try {
    data = (await res.json()) as { error?: unknown } | null;
  } catch {
    if (res.ok) throw new ServiceError(503, "Leadline sent an answer we couldn't read. Try again in a minute. Details: unreadable service reply");
    data = null;
  }
  if (!res.ok) {
    const message = typeof data?.error === "string" ? data.error : `Leadline service error ${res.status}`;
    throw new ServiceError(res.status, message);
  }
  return data as T;
}

/** Like `svc`, but a 404 is `null`. */
async function svcOrNull<T>(path: string): Promise<T | null> {
  try {
    return await svc<T>("GET", path);
  } catch (err) {
    if (err instanceof ServiceError && err.status === 404) return null;
    throw err;
  }
}

/** `?a=1&b=2`, leaving out empty values. */
export function query(params: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

const seg = encodeURIComponent;

/**
 * Wraps a route handler so a service failure becomes a JSON `{ error }` answer
 * the UI already shows (`postJson` throws `data.error`): 503 when the service
 * is down or failed, its own status otherwise. Other errors are left alone.
 */
export function withService<A extends unknown[]>(handler: (...args: A) => Promise<Response>) {
  return async (...args: A): Promise<Response> => {
    try {
      return await handler(...args);
    } catch (err) {
      if (!(err instanceof ServiceError)) throw err;
      return Response.json({ error: err.message }, { status: err.status >= 500 ? 503 : err.status });
    }
  };
}

// ── Accounts and sessions ──────────────────────────────────────────────────

export const createUser = (u: { role: Role; name: string; email: string; passwordHash: string }) =>
  svc<User>("POST", "/users", u);

export const getUserByEmail = (email: string) => svcOrNull<User>(`/users/by-email${query({ email })}`);

export const getUser = (id: string) => svcOrNull<User>(`/users/${seg(id)}`);

export const createSession = (s: { userId: string; token: string; expiresAt: string }) =>
  svc<void>("POST", "/sessions", s);

export interface SessionInfo {
  user: User;
  profile: FounderProfile | null;
  discoverable: boolean;
}

export const getSession = (token: string) => svcOrNull<SessionInfo>(`/sessions/${seg(token)}`);

export const deleteSession = (token: string) => svc<void>("DELETE", `/sessions/${seg(token)}`);

export const demoUser = (d: { role: Role; email: string; name: string; investorName?: string; persona?: FounderProfile }) =>
  svc<User>("POST", "/demo-users", d);

// ── Founders, funds, intros ────────────────────────────────────────────────

export const putFounder = (userId: string, input: Omit<FounderRecord, "id" | "updatedAt">) =>
  svc<FounderRecord>("PUT", `/users/${seg(userId)}/founder`, input);

export const putInvestorFund = (userId: string, investorName: string) =>
  svc<void>("PUT", `/users/${seg(userId)}/investor-fund`, { investorName });

export const getFounder = (id: string) => svcOrNull<FounderRecord>(`/founders/${seg(id)}`);

export const discoverableFounders = () => svc<FounderRecord[]>("GET", "/founders?discoverable=1");

export const postIntro = (input: Omit<Intro, "id" | "createdAt" | "status">) => svc<Intro>("POST", "/intros", input);

export const listIntros = (f: { founderId?: string; investor?: string } = {}) =>
  svc<Intro[]>("GET", `/intros${query(f)}`);

export const patchIntro = (id: string, a: { userId: string; status: Intro["status"]; passReason?: string }) =>
  svc<Intro>("PATCH", `/intros/${seg(id)}`, a);

// ── Market data (the database's rounds and fund closes; never a live Cala call) ──

export const deals = (f: { sector?: string; region?: string; stage?: string; sinceDays?: number } = {}) =>
  svc<Deal[]>("GET", `/deals${query(f)}`);

export const dealsByInvestor = (name: string, sinceDays?: number) =>
  svc<Deal[]>("GET", `/deals/investor${query({ name, sinceDays })}`);

export const dealsByCompany = (name: string) => svc<Deal[]>("GET", `/deals/company${query({ name })}`);

/** Every round of companies whose description shares 2+ content words with `description`; `sector` is a Sector key. */
export const similarDeals = (description: string, sector?: string) =>
  svc<Deal[]>("GET", `/deals/similar${query({ description, sector })}`);

export const funds = (investor: string) => svc<FundClose[]>("GET", `/funds${query({ investor })}`);

export const fundCloses = (f: { sinceDays?: number; sector?: string } = {}) =>
  svc<FundClose[]>("GET", `/fund-closes${query(f)}`);

export interface ServiceEntity {
  id: string;
  name: string;
  entity_type: string;
}

export const entities = (name: string, limit = 8) => svc<ServiceEntity[]>("GET", `/entities${query({ name, limit })}`);

export interface ServiceStatus {
  mode: "live" | "simulated";
  jobs: { queued: number; running: number; failed: number };
}

export const status = () => svc<ServiceStatus>("GET", "/status");

// ── The agent's stored rankings ────────────────────────────────────────────

export interface RankedMatch {
  key: string; // "investor:<slug>" or "founder:<id>"
  name: string;
  kind: string | null;
  score: number | null; // 0–1
  scoreParts: Record<string, number>;
  confidence: "high" | "medium" | "low" | null;
  reasons: { text: string; evidence: string[] }[];
  rank: number | null;
}

export interface StoredRanking {
  matches: RankedMatch[];
  /** In this user's best N now, but not in the stored ranking yet (a re-rank is queued). `fit` is 0–1. */
  newCandidates: { key: string; name: string; fit: number }[];
  computedAt: string;
}

export interface RankingState {
  status: "building" | "ready" | "failed" | "none";
  /** The last stored ranking; kept while a newer one is building. */
  ranking: StoredRanking | null;
  error?: string;
}

/** Reading it may queue one re-rank job when this user's best N changed. */
export const rankings = (key: string) => svc<RankingState>("GET", `/rankings/${seg(key)}`);

export interface ProfileState {
  status: "building" | "ready" | "failed" | "none";
  error?: string;
}

/** Where the agent's profile of this user stands (the profile itself is not needed by the pages). */
export const profileStatus = (key: string) => svc<ProfileState>("GET", `/profiles/${seg(key)}`);
