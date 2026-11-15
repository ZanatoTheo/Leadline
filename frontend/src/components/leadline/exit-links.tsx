"use client";

import Link from "next/link";
import { LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLeadline } from "@/lib/leadline/store";

/** Way out of the full-page setup screens (no sidebar there): Cancel back into the app, and Log out.
 *  `cancelHref` is shown only when there is somewhere to go back to (a profile or fund already saved). */
export function ExitLinks({ cancelHref }: { cancelHref?: string }) {
  const clear = useLeadline((s) => s.clear);
  // Same steps as the sidebar's log out.
  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    clear();
    window.location.assign("/");
  };
  return (
    <>
      {cancelHref && (
        <Link href={cancelHref} className="text-sm text-muted-foreground hover:text-foreground">
          Cancel
        </Link>
      )}
      <Button variant="ghost" size="sm" onClick={logout}>
        <LogOut className="h-4 w-4" /> Log out
      </Button>
    </>
  );
}
