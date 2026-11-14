// Accounts and sessions. Each user has exactly one role, and every page group
// and API checks it, so founders and investors only ever see their own side.

import { randomBytes, scryptSync, timingSafeEqual, randomUUID } from "node:crypto";
import { cookies } from "next/headers";
import { readDb, update, type Role, type User } from "./db";
import type { FounderProfile } from "@/lib/leadline/types";
import { DEMO_PERSONA } from "@/lib/leadline/demo";

export const SESSION_COOKIE = "leadline_session";
const SESSION_DAYS = 30;

export function hashPassword(password: string): string {
  const salt = randomBytes(16).toString("hex");
  return `${salt}:${scryptSync(password, salt, 64).toString("hex")}`;
}

function verifyPassword(password: string, stored: string): boolean {
  const [salt, hash] = stored.split(":");
  if (!salt || !hash) return false;
  const a = Buffer.from(hash, "hex");
  const b = scryptSync(password, salt, 64);
  return a.length === b.length && timingSafeEqual(a, b);
}

/** What the browser is allowed to know about the logged-in user. */
export interface SessionUser {
  id: string;
  role: Role;
  name: string;
  email: string;
  investorName: string | null;
  founderId: string | null;
  profile: FounderProfile | null;
  discoverable: boolean;
}

type FullUser = User & { profile: FounderProfile | null; discoverable: boolean };

export async function currentUser(): Promise<FullUser | null> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return null;
  const db = await readDb();
  const session = db.sessions.find((s) => s.token === token && s.expiresAt > new Date().toISOString());
  const user = session && db.users.find((u) => u.id === session.userId);
  if (!user) return null;
  const founder = user.founderId ? db.founders.find((f) => f.id === user.founderId) : undefined;
  return { ...user, profile: founder?.profile ?? null, discoverable: founder?.discoverable ?? true };
}

export function toSessionUser(u: FullUser): SessionUser {
  return {
    id: u.id,
    role: u.role,
    name: u.name,
    email: u.email,
    investorName: u.investorName ?? null,
    founderId: u.founderId ?? null,
    profile: u.profile,
    discoverable: u.discoverable,
  };
}

async function startSession(userId: string): Promise<void> {
  const token = randomBytes(32).toString("hex");
  const expiresAt = new Date(Date.now() + SESSION_DAYS * 24 * 3600 * 1000).toISOString();
  await update((db) => {
    db.sessions = db.sessions.filter((s) => s.expiresAt > new Date().toISOString());
    db.sessions.push({ token, userId, expiresAt });
  });
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_DAYS * 24 * 3600,
  });
}

export async function endSession(): Promise<void> {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  if (token) await update((db) => void (db.sessions = db.sessions.filter((s) => s.token !== token)));
  store.delete(SESSION_COOKIE);
}

export async function signUp(input: { role: Role; name: string; email: string; password: string }): Promise<string | null> {
  const email = input.email.trim().toLowerCase();
  const user = await update((db) => {
    if (db.users.some((u) => u.email === email)) return null;
    const u: User = {
      id: randomUUID(),
      role: input.role,
      name: input.name.trim(),
      email,
      passwordHash: hashPassword(input.password),
      createdAt: new Date().toISOString(),
    };
    db.users.push(u);
    return u;
  });
  if (!user) return "An account with this email already exists.";
  await startSession(user.id);
  return null;
}

export async function logIn(emailRaw: string, password: string): Promise<User | null> {
  const email = emailRaw.trim().toLowerCase();
  const db = await readDb();
  const user = db.users.find((u) => u.email === email);
  if (!user || !user.passwordHash || !verifyPassword(password, user.passwordHash)) return null;
  await startSession(user.id);
  return user;
}

// ── Demo accounts (development only) ───────────────────────────────────────
// One click logs in as a ready-made founder or investor, so demos don't
// depend on typing passwords. Disabled in production unless explicitly enabled.

export const demoLoginEnabled = () =>
  process.env.NODE_ENV !== "production" || process.env.LEADLINE_DEMO_LOGIN === "true";

const DEMO: Record<Role, { email: string; name: string; investorName?: string }> = {
  founder: { email: "demo-founder@leadline.local", name: "Alex" },
  investor: { email: "demo-investor@leadline.local", name: "Sam", investorName: "Fjord Ventures" },
};

export async function logInDemo(role: Role): Promise<User> {
  const d = DEMO[role];
  const user = await update((db) => {
    let u = db.users.find((x) => x.email === d.email);
    if (!u) {
      u = { id: randomUUID(), role, name: d.name, email: d.email, passwordHash: "", investorName: d.investorName, createdAt: new Date().toISOString() };
      db.users.push(u);
    }
    // The demo founder starts with the demo persona, opted in to discovery.
    if (role === "founder" && !u.founderId) {
      const id = randomUUID();
      db.founders.push({ id, profile: DEMO_PERSONA, founderName: d.name, email: d.email, discoverable: true, updatedAt: new Date().toISOString() });
      u.founderId = id;
    }
    return u;
  });
  await startSession(user.id);
  return user;
}

/** For API routes: the logged-in user if they have `role`, else an error Response. */
export async function requireRole(role: Role): Promise<{ user: FullUser } | { error: Response }> {
  const user = await currentUser();
  if (!user) return { error: Response.json({ error: "Please log in." }, { status: 401 }) };
  if (user.role !== role) return { error: Response.json({ error: `This is only for ${role}s.` }, { status: 403 }) };
  return { user };
}

export async function requireUser(): Promise<{ user: FullUser } | { error: Response }> {
  const user = await currentUser();
  if (!user) return { error: Response.json({ error: "Please log in." }, { status: 401 }) };
  return { user };
}
