"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  ExternalLink,
  Gauge,
  GitBranch,
  Handshake,
  Loader2,
  ShieldAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  Conflict,
  Deal,
  FounderProfile,
  ShortlistPending,
  ShortlistResponse,
  Source,
  TimingStatus,
} from "@/lib/leadline/types";
import { useLeadline } from "@/lib/leadline/store";
import { dealPhrase, fmtMonth } from "@/lib/leadline/format";
import { useSession } from "./session";

/** True once the persisted store has loaded from localStorage. */
export function useHydrated(): boolean {
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    if (useLeadline.persist.hasHydrated()) setHydrated(true);
    return useLeadline.persist.onFinishHydration(() => setHydrated(true));
  }, []);
  return hydrated;
}

/**
 * The logged-in founder's profile, sending them to onboarding if they have
 * none yet. Prefers the local copy (updated instantly on save) when it
 * belongs to the same account, else the server's.
 */
export function useRequiredProfile(): FounderProfile | null {
  const session = useSession();
  const hydrated = useHydrated();
  const accountId = useLeadline((s) => s.accountId);
  const local = useLeadline((s) => s.profile);
  const router = useRouter();
  const profile = hydrated && accountId === session.id ? (local ?? session.profile) : session.profile;
  useEffect(() => {
    if (hydrated && !profile) router.replace("/onboarding");
  }, [hydrated, profile, router]);
  return hydrated ? profile : null;
}

/** Same profile resolution as useRequiredProfile, without redirecting. */
export function useRequiredProfileOptional(): FounderProfile | null {
  const session = useSession();
  const hydrated = useHydrated();
  const accountId = useLeadline((s) => s.accountId);
  const local = useLeadline((s) => s.profile);
  if (session.role !== "founder") return null;
  return hydrated && accountId === session.id ? (local ?? session.profile) : session.profile;
}

export type CalaMode = "live" | "simulated";

export function useCalaMode(): CalaMode | null {
  const [mode, setMode] = useState<CalaMode | null>(null);
  useEffect(() => {
    fetch("/api/status")
      .then((r) => r.json())
      .then((d) => setMode(d.mode))
      .catch(() => setMode(null));
  }, []);
  return mode;
}

export function PoweredByCala({ mode, className }: { mode?: CalaMode | null; className?: string }) {
  if (mode !== "simulated") return null;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-600 dark:text-amber-400",
        className,
      )}
    >
      simulated data
    </span>
  );
}

export function SourceLinks({ sources, className }: { sources: Source[]; className?: string }) {
  if (!sources.length) {
    return <span className={cn("text-[11px] text-muted-foreground", className)}>no source link</span>;
  }
  return (
    <span className={cn("inline-flex flex-wrap gap-1 align-middle", className)}>
      {sources.slice(0, 3).map((s) => (
        <a
          key={s.url}
          href={s.url}
          target="_blank"
          rel="noreferrer"
          title={`${s.publisher}: ${s.title}`}
          className="relative z-10 inline-flex items-center gap-0.5 rounded border border-primary/20 bg-primary/5 px-1.5 text-[11px] font-medium text-primary hover:bg-primary/10"
        >
          {s.publisher}
          <ExternalLink className="h-2.5 w-2.5" />
        </a>
      ))}
    </span>
  );
}

/** "Led Heliora's €1.8M seed, Nov 2026 [source]" */
export function DealClaim({ deal, verb = "Led" }: { deal: Deal; verb?: string }) {
  return (
    <span className="text-sm">
      {verb} {dealPhrase(deal)}, {fmtMonth(deal.announced)} <SourceLinks sources={deal.sources} />
    </span>
  );
}

export function ScoreBar({ score }: { score: number }) {
  const color = score >= 75 ? "bg-emerald-500" : score >= 50 ? "bg-indigo-500" : score >= 30 ? "bg-amber-500" : "bg-slate-400";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-secondary">
        <div className={cn("h-full rounded-full", color)} style={{ width: `${score}%` }} />
      </div>
      <span className="w-7 text-right text-sm font-semibold tabular-nums">{score}</span>
    </div>
  );
}

export function ConflictBadge({ conflict }: { conflict: Conflict }) {
  if (conflict.level === "direct") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-rose-500/25 bg-rose-500/10 px-2 py-0.5 text-xs font-medium text-rose-600 dark:text-rose-400">
        <ShieldAlert className="h-3 w-3" /> Backs {conflict.company}
      </span>
    );
  }
  if (conflict.level === "possible") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-amber-500/25 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400">
        <AlertTriangle className="h-3 w-3" /> Check {conflict.company}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
      <CheckCircle2 className="h-3 w-3" /> No competitor found
    </span>
  );
}

/** A failure, in plain words. A trailing "Details: ..." part (raw error codes) is shown smaller below it. */
export function ErrorBox({ message }: { message: string }) {
  const at = message.indexOf(" Details: ");
  const text = at < 0 ? message : message.slice(0, at);
  const details = at < 0 ? null : message.slice(at + " Details: ".length);
  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
      <p>{text}</p>
      {details && <p className="mt-1 break-words font-mono text-xs opacity-70">Details: {details}</p>}
    </div>
  );
}


export async function postJson<T>(url: string, body: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new Error("Couldn't reach Leadline. Check your connection and try again.");
  }
  // A non-JSON answer (an error page, a proxy limit) gets a plain sentence instead of a parser error.
  const unreadable = `Leadline sent an answer we couldn't read. Try again in a minute. Details: HTTP ${res.status}`;
  const data = await res.json().catch(() => null);
  if (data === null) throw Object.assign(new Error(unreadable), { status: res.status });
  if (!res.ok) throw Object.assign(new Error(data.error ?? `Request failed (${res.status})`), { status: res.status });
  return data as T;
}

export type ShortlistState =
  | { kind: "loading" }
  | { kind: "pending"; pending: ShortlistPending; gaveUp: boolean }
  | { kind: "ready"; data: ShortlistResponse }
  | { kind: "error"; message: string };

// Wait times between checks while the agent works (the last one repeats), and when to stop checking on our own.
const POLL_DELAYS_MS = [3_000, 5_000, 8_000, 13_000, 20_000, 30_000];
const POLL_LIMIT_MS = 6 * 60_000;

const isPending = (d: unknown): d is ShortlistPending =>
  typeof d === "object" && d !== null && (d as { status?: unknown }).status === "building";

/**
 * The founder's shortlist. While the profile or ranking is still being built (HTTP 202) it checks again with
 * growing waits, and after `POLL_LIMIT_MS` stops with `gaveUp` so the page can offer a manual check (`retry`).
 */
export function useShortlist(profile: FounderProfile | null): { state: ShortlistState; retry: () => void } {
  const [state, setState] = useState<ShortlistState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!profile) return;
    const ctrl = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();
    let building = false; // a build was reported: a failed check is then retried, not shown at once
    let misses = 0;
    const later = (n: number) => {
      const gaveUp = Date.now() - started >= POLL_LIMIT_MS;
      if (!gaveUp) timer = setTimeout(() => check(n + 1), POLL_DELAYS_MS[Math.min(n, POLL_DELAYS_MS.length - 1)]);
      return gaveUp;
    };
    const check = (n: number) => {
      postJson<ShortlistResponse | ShortlistPending>("/api/shortlist", profile, ctrl.signal)
        .then((d) => {
          misses = 0;
          if (!isPending(d)) return setState({ kind: "ready", data: d });
          building = true;
          const gaveUp = later(n);
          setState({ kind: "pending", pending: d, gaveUp });
        })
        .catch((e) => {
          if (e.name === "AbortError") return;
          // A brief outage mid-build (503, or no answer at all) gets two more tries; a job failure (502) or any
          // other answer is shown at once, since asking again gives the same reply.
          const outage = e.status === undefined || e.status === 503;
          if (building && outage && ++misses < 3 && !later(n)) return;
          setState({ kind: "error", message: e.message });
        });
    };
    setState((s) => (s.kind === "pending" ? { ...s, gaveUp: false } : { kind: "loading" }));
    check(0);
    return () => {
      ctrl.abort();
      clearTimeout(timer);
    };
  }, [profile, attempt]);
  return { state, retry: () => setAttempt((a) => a + 1) };
}

/** Background work in progress: which step runs now and what comes next. Not an error. */
export function PendingBox({ pending, gaveUp, onRetry }: { pending: ShortlistPending; gaveUp: boolean; onRetry: () => void }) {
  const step = pending.step === "profile" ? 1 : 2;
  return (
    <div className="rounded-lg border border-primary/25 bg-primary/5 p-4 text-sm">
      <div className="flex items-center gap-2 font-medium">
        {gaveUp ? <Clock className="h-4 w-4 text-primary" /> : <Loader2 className="h-4 w-4 animate-spin text-primary" />}
        Step {step} of 2: {pending.message}
      </div>
      <p className="mt-1 text-muted-foreground">
        {pending.next ? `${pending.next} ` : ""}
        {gaveUp ? "This is taking longer than usual." : "This page updates on its own; it usually takes a few minutes."}
      </p>
      {gaveUp && (
        <button type="button" onClick={onRetry} className="mt-2 text-sm font-medium text-primary hover:underline">
          Check again
        </button>
      )}
    </div>
  );
}

const pill = "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium";

export function TimingBadge({ status, title }: { status?: TimingStatus; title?: string }) {
  if (!status) return null;
  const styles: Record<TimingStatus, string> = {
    deploying: "border-sky-500/25 bg-sky-500/10 text-sky-700 dark:text-sky-400",
    steady: "border-border bg-secondary text-muted-foreground",
    slowing: "border-slate-400/30 bg-slate-400/10 text-slate-600 dark:text-slate-400",
    unknown: "border-border bg-secondary text-muted-foreground",
  };
  const label: Record<TimingStatus, string> = {
    deploying: "Deploying now",
    steady: "Steady pace",
    slowing: "Slowing down",
    unknown: "Pace unknown",
  };
  return (
    <span className={cn(pill, styles[status])} title={title}>
      <Gauge className="h-3 w-3" /> {label[status]}
    </span>
  );
}

export function TwinBadge({ count }: { count?: number }) {
  if (!count) return null;
  return (
    <span className={cn(pill, "border-violet-500/25 bg-violet-500/10 text-violet-700 dark:text-violet-400")}>
      <GitBranch className="h-3 w-3" /> Backed {count} of your twins
    </span>
  );
}

export function SynergyBadge({ count }: { count?: number }) {
  if (!count) return null;
  return (
    <span className={cn(pill, "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400")}>
      <Handshake className="h-3 w-3" /> {count} portfolio co{count === 1 ? "" : "s"} could buy from you
    </span>
  );
}

/** Saves the logged-in founder's profile on the server (visible to investors only if discoverable). */
export async function syncFounder(): Promise<string | null> {
  const s = useLeadline.getState();
  if (!s.profile) return null;
  const { id } = await postJson<{ id: string }>("/api/founders", { profile: s.profile, discoverable: s.discoverable });
  return id;
}
