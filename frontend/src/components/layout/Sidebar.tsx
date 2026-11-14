"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { Bell, BookOpen, CalendarCheck, GitBranch, Handshake, Inbox, ListOrdered, LogOut, Moon, Sun, UserRound, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLeadline, useUnreadSignals } from "@/lib/leadline/store";
import { stageLabel } from "@/lib/leadline/types";
import { fmtEur } from "@/lib/leadline/format";
import { PoweredByCala, useCalaMode, useHydrated } from "@/components/leadline/shared";
import { useSession } from "@/components/leadline/session";

type NavItem = { label: string; href: string; icon: React.ComponentType<{ className?: string }>; badge: number };

export function Sidebar({ incomingIntros = 0 }: { incomingIntros?: number }) {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const hydrated = useHydrated();
  const session = useSession();
  const localProfile = useLeadline((s) => s.profile);
  const accountId = useLeadline((s) => s.accountId);
  const clear = useLeadline((s) => s.clear);
  const unread = useUnreadSignals().length;
  const calaMode = useCalaMode();
  const profile = hydrated && accountId === session.id ? (localProfile ?? session.profile) : session.profile;

  const nav: NavItem[] =
    session.role === "founder"
      ? [
          { label: "Today", href: "/today", icon: CalendarCheck, badge: 0 },
          { label: "Funding twins", href: "/twins", icon: GitBranch, badge: 0 },
          { label: "Who to pitch", href: "/investors", icon: ListOrdered, badge: 0 },
          { label: "Intros", href: "/intros", icon: Handshake, badge: incomingIntros },
          { label: "Signals", href: "/alerts", icon: Bell, badge: hydrated ? unread : 0 },
          { label: "My startup", href: "/onboarding", icon: UserRound, badge: 0 },
        ]
      : [
          { label: "Today", href: "/investor/today", icon: CalendarCheck, badge: 0 },
          { label: "Deal flow", href: "/investor", icon: Inbox, badge: incomingIntros },
          { label: "Your thesis", href: "/investor/thesis", icon: BookOpen, badge: 0 },
        ];

  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    clear();
    window.location.assign("/");
  };

  return (
    <aside className="fixed left-0 top-0 z-30 flex h-screen w-56 flex-col border-r border-border bg-card">
      <Link href="/" className="flex h-14 items-center gap-2.5 border-b border-border px-4 hover:bg-secondary/40">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary">
          <Zap className="h-3.5 w-3.5 text-primary-foreground" />
        </div>
        <span className="text-sm font-bold tracking-tight">Leadline</span>
        <span className="ml-auto rounded border border-border px-1.5 py-0.5 text-[10px] capitalize text-muted-foreground">
          {session.role}
        </span>
      </Link>

      <div className="border-b border-border px-3 py-2.5">
        <div className="flex items-center gap-2 rounded-lg border border-primary/15 bg-primary/5 px-2.5 py-2">
          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-primary/20 bg-primary/15 text-[11px] font-bold text-primary">
            {(session.role === "founder" ? profile?.startupName || session.name : session.investorName || session.name)
              .charAt(0)
              .toUpperCase()}
          </div>
          <div className="min-w-0">
            {session.role === "founder" ? (
              <>
                <div className="truncate text-xs font-semibold">{profile?.startupName || "Your startup"}</div>
                <div className="truncate text-[10px] text-muted-foreground">
                  {profile ? `${stageLabel(profile.stage)} · ${fmtEur(profile.raiseEurM || null)}` : session.name}
                </div>
              </>
            ) : (
              <>
                <div className="truncate text-xs font-semibold">{session.investorName || "Pick your fund"}</div>
                <div className="truncate text-[10px] text-muted-foreground">{session.name} · Leadline Pro trial</div>
              </>
            )}
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-3">
        {nav.map((item) => {
          const active =
            pathname === item.href ||
            (item.href === "/investor"
              ? /^\/investor\/(startup|company)\//.test(pathname)
              : pathname.startsWith(item.href + "/"));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-all",
                active
                  ? "border border-primary/20 bg-primary/10 font-semibold text-primary"
                  : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
              )}
            >
              <item.icon className={cn("h-4 w-4 shrink-0", active && "text-primary")} />
              <span className="flex-1">{item.label}</span>
              {item.badge > 0 && (
                <span className="rounded-md bg-destructive/10 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-destructive">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="space-y-1 border-t border-border px-3 py-3">
        <PoweredByCala mode={calaMode} className="mb-1 w-full justify-center" />
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
        >
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
        </button>
        <button
          onClick={logout}
          className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
        >
          <LogOut className="h-4 w-4" />
          <span className="truncate">Log out {session.email}</span>
        </button>
      </div>
    </aside>
  );
}
