"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { FounderProfile, Signal } from "./types";
import type { SessionUser } from "@/lib/server/auth";

/**
 * Client cache of the logged-in account. The server (session + database) is
 * the source of truth; `loadAccount` refreshes this from it on every page.
 */
interface LeadlineStore {
  accountId: string | null;
  loadAccount: (u: SessionUser) => void;
  clear: () => void;

  // Founder
  profile: FounderProfile | null;
  setProfile: (p: FounderProfile) => void;
  founderName: string;
  email: string;
  discoverable: boolean;
  setDiscoverable: (d: boolean) => void;

  signals: Signal[];
  signalsCheckedAt: string | null;
  setSignals: (s: Signal[], checkedAt: string) => void;
  seenSignalIds: string[];
  markSignalsSeen: () => void;
}

const EMPTY = {
  accountId: null,
  profile: null,
  founderName: "",
  email: "",
  discoverable: true,
  signals: [],
  signalsCheckedAt: null,
  seenSignalIds: [],
};

export const useLeadline = create<LeadlineStore>()(
  persist(
    (set, get) => ({
      ...EMPTY,
      loadAccount: (u) => {
        // Different account on this browser: drop everything cached for the previous one.
        const base = get().accountId === u.id ? {} : EMPTY;
        set({
          ...base,
          accountId: u.id,
          profile: u.profile,
          founderName: u.name,
          email: u.email,
          discoverable: u.discoverable,
        });
      },
      clear: () => set(EMPTY),

      setDiscoverable: (discoverable) => set({ discoverable }),
      setProfile: (profile) => set({ profile, signals: [], signalsCheckedAt: null, seenSignalIds: [] }),

      setSignals: (signals, signalsCheckedAt) => set({ signals, signalsCheckedAt }),
      markSignalsSeen: () => set({ seenSignalIds: get().signals.map((s) => s.id) }),
    }),
    { name: "leadline" },
  ),
);

export function useUnreadSignals(): Signal[] {
  const signals = useLeadline((s) => s.signals);
  const seen = useLeadline((s) => s.seenSignalIds);
  return signals.filter((s) => !seen.includes(s.id));
}

export { DEMO_PERSONA } from "./demo";
