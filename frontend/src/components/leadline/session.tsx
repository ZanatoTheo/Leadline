"use client";

import { createContext, useContext, useEffect } from "react";
import type { SessionUser } from "@/lib/server/auth";
import { useLeadline } from "@/lib/leadline/store";

const SessionContext = createContext<SessionUser | null>(null);

/** The logged-in user, provided by the role's server layout. */
export function useSession(): SessionUser {
  const s = useContext(SessionContext);
  if (!s) throw new Error("useSession must be used inside a role layout");
  return s;
}

export function SessionProvider({ user, children }: { user: SessionUser; children: React.ReactNode }) {
  const loadAccount = useLeadline((s) => s.loadAccount);
  // The server is the source of truth; the local store is a cache of it.
  useEffect(() => {
    loadAccount(user);
  }, [user, loadAccount]);
  return <SessionContext.Provider value={user}>{children}</SessionContext.Provider>;
}
