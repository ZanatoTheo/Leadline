// Minimal shared store for the two-sided parts of Leadline: founder profiles
// that investors can see, and intro requests between the two sides.
// A JSON file is enough for a demo; swap for a real database in production.

import { randomUUID } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import type { FounderRecord, Intro } from "@/lib/leadline/match-types";

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

const FILE = path.join(process.cwd(), ".leadline-data", "db.json");

interface Db {
  founders: FounderRecord[];
  intros: Intro[];
  users: User[];
  sessions: Session[];
}

let queue: Promise<unknown> = Promise.resolve();

async function load(): Promise<Db> {
  try {
    const db = JSON.parse(await readFile(FILE, "utf8")) as Partial<Db>;
    return { founders: [], intros: [], users: [], sessions: [], ...db };
  } catch {
    return { founders: [], intros: [], users: [], sessions: [] };
  }
}

/** Serialises read-modify-write so concurrent requests don't clobber each other. */
export function update<T>(fn: (db: Db) => T): Promise<T> {
  const run = queue.then(async () => {
    const db = await load();
    const result = fn(db);
    await mkdir(path.dirname(FILE), { recursive: true });
    await writeFile(FILE, JSON.stringify(db, null, 2));
    return result;
  });
  queue = run.catch(() => {});
  return run;
}

export async function readDb(): Promise<Db> {
  await queue;
  return load();
}

/** Creates or updates the founder record that belongs to `userId`. */
export function upsertFounderForUser(
  userId: string,
  input: Omit<FounderRecord, "id" | "updatedAt">,
): Promise<FounderRecord> {
  return update((db) => {
    const now = new Date().toISOString();
    const user = db.users.find((u) => u.id === userId);
    const existing = user?.founderId ? db.founders.find((f) => f.id === user.founderId) : undefined;
    if (existing) {
      Object.assign(existing, input, { updatedAt: now });
      return existing;
    }
    const record: FounderRecord = { ...input, id: randomUUID(), updatedAt: now };
    db.founders.push(record);
    if (user) user.founderId = record.id;
    return record;
  });
}

/** Sets the fund an investor user represents. */
export function setInvestorFund(userId: string, investorName: string): Promise<void> {
  return update((db) => {
    const user = db.users.find((u) => u.id === userId);
    if (user && user.role === "investor") user.investorName = investorName;
  });
}

export function createIntro(input: Omit<Intro, "id" | "createdAt" | "status">): Promise<Intro> {
  return update((db) => {
    const dup = db.intros.find(
      (i) => i.founderId === input.founderId && i.investor === input.investor && i.status === "pending",
    );
    if (dup) return dup;
    const intro: Intro = { ...input, id: randomUUID(), status: "pending", createdAt: new Date().toISOString() };
    db.intros.push(intro);
    return intro;
  });
}

/**
 * Answer an intro. `by` identifies the caller from their session: only the
 * party the intro was sent TO can answer, and only for their own intros.
 */
export function respondToIntro(
  id: string,
  by: { role: "founder"; founderId: string } | { role: "investor"; investorName: string },
  status: Intro["status"],
  passReason?: string,
): Promise<Intro | null> {
  return update((db) => {
    const intro = db.intros.find((i) => i.id === id);
    if (!intro) return null;
    const recipient = intro.direction === "founder-to-investor" ? "investor" : "founder";
    if (by.role !== recipient) return null;
    if (by.role === "founder" && intro.founderId !== by.founderId) return null;
    if (by.role === "investor" && intro.investor !== by.investorName) return null;
    intro.status = status;
    intro.passReason = status === "passed" ? passReason : undefined;
    intro.respondedAt = new Date().toISOString();
    return intro;
  });
}
