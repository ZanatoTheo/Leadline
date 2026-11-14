"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "./Sidebar";
import { useLeadline } from "@/lib/leadline/store";
import type { SignalsResponse } from "@/lib/leadline/types";
import type { Intro } from "@/lib/leadline/match-types";
import { postJson, useRequiredProfileOptional } from "@/components/leadline/shared";
import { useSession } from "@/components/leadline/session";

const WATCH_INTERVAL_MS = 5 * 60 * 1000;
const INTRO_POLL_MS = 15 * 1000;

/** Founders: watch Cala for new rounds and funds while the app is open. */
function useSignalWatcher() {
  const session = useSession();
  const profile = useRequiredProfileOptional();
  const setSignals = useLeadline((s) => s.setSignals);

  useEffect(() => {
    if (session.role !== "founder" || !profile) return;
    let cancelled = false;
    const check = () =>
      postJson<SignalsResponse>("/api/signals", profile)
        .then((r) => !cancelled && setSignals(r.signals, r.checkedAt))
        .catch(() => {});
    check();
    const id = setInterval(check, WATCH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [session.role, profile, setSignals]);
}

/** Intros waiting for the logged-in user's answer. */
function useIncomingIntros(): number {
  const session = useSession();
  const [count, setCount] = useState(0);
  useEffect(() => {
    const waitingFor = session.role === "founder" ? "investor-to-founder" : "founder-to-investor";
    const poll = () =>
      fetch("/api/intros")
        .then((r) => r.json())
        .then((d: { intros?: Intro[] }) =>
          setCount((d.intros ?? []).filter((i) => i.direction === waitingFor && i.status === "pending").length),
        )
        .catch(() => {});
    poll();
    const id = setInterval(poll, INTRO_POLL_MS);
    return () => clearInterval(id);
  }, [session.role]);
  return count;
}

export function AppLayout({ children }: { children: React.ReactNode }) {
  useSignalWatcher();
  const incoming = useIncomingIntros();
  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar incomingIntros={incoming} />
      <main className="min-h-screen flex-1 pl-56">
        <div className="mx-auto max-w-[1100px] p-6">{children}</div>
      </main>
    </div>
  );
}
