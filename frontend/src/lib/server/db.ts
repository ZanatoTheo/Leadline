// The two-sided parts of Leadline: founder profiles that investors can see, and
// intro requests between the two sides. They live in the Leadline database,
// behind the local Leadline service (see ./leadline-service.ts), so the agent
// sees every new founder and fund and can build their profiles and rankings.

import type { FounderRecord, Intro } from "@/lib/leadline/match-types";
import * as service from "./leadline-service";
import { ServiceError } from "./leadline-service";

export type Role = "founder" | "investor";

export interface User {
  id: string;
  role: Role;
  name: string;
  email: string;
  passwordHash: string; // "salt:hash" (scrypt); empty for built-in demo users
  founderId?: string; // founder role: their shared founder record
  investorName?: string; // investor role: the fund they represent
  createdAt: string;
}

export interface Session {
  token: string;
  userId: string;
  expiresAt: string;
}

/** Creates or updates the founder record that belongs to `userId`. */
export function upsertFounderForUser(
  userId: string,
  input: Omit<FounderRecord, "id" | "updatedAt">,
): Promise<FounderRecord> {
  return service.putFounder(userId, input);
}

/** Sets the fund an investor user represents. Any service refusal (403 not an investor, 404 no such user) is an
 * error: the only caller already checked the role, so the fund was not saved and the page must say so. */
export async function setInvestorFund(userId: string, investorName: string): Promise<void> {
  await service.putInvestorFund(userId, investorName);
}

/** A new pending intro, or the pending one that already exists between this founder and fund. */
export function createIntro(input: Omit<Intro, "id" | "createdAt" | "status">): Promise<Intro> {
  return service.postIntro(input);
}

/** The intros of one founder and/or one fund, newest first. */
export function listIntros(filter: { founderId?: string; investor?: string } = {}): Promise<Intro[]> {
  return service.listIntros(filter);
}

/** One founder record, or null. */
export function getFounder(id: string): Promise<FounderRecord | null> {
  return id ? service.getFounder(id) : Promise.resolve(null);
}

/** Founders who chose to be visible to investors, most recently updated first. */
export function discoverableFounders(): Promise<FounderRecord[]> {
  return service.discoverableFounders();
}

/**
 * Answer an intro. `by` identifies the caller from their session: only the
 * party the intro was sent TO can answer, and only for their own intros.
 * `userId` (the caller's user id) lets the service check that against its own
 * records. Returns null when the intro is missing or not theirs to answer; an
 * intro that was already answered throws a 409 `ServiceError`, which the route
 * (wrapped in `withService`) returns as is.
 */
export async function respondToIntro(
  id: string,
  by: { role: "founder"; founderId: string } | { role: "investor"; investorName: string },
  status: Intro["status"],
  passReason?: string,
  userId?: string,
): Promise<Intro | null> {
  if (!userId) throw new Error("respondToIntro needs the caller's user id");
  if (!id || !by) return null;
  try {
    return await service.patchIntro(id, { userId, status, passReason: status === "passed" ? passReason : undefined });
  } catch (err) {
    if (err instanceof ServiceError && [400, 403, 404].includes(err.status)) return null;
    throw err;
  }
}
