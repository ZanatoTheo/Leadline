"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useModeStore } from "@/store/useModeStore";
import {
  LayoutDashboard,
  Users,
  Share2,
  SlidersHorizontal,
  MessageSquare,
  Bell,
  Briefcase,
  Sun,
  Moon,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";

const FOUNDER_NAV = [
  { label: "Dashboard",  href: "/dashboard",           icon: LayoutDashboard },
  { label: "Investors",  href: "/investors",            icon: Users           },
  { label: "Networks",   href: "/syndicate",            icon: Share2          },
  { label: "Simulator",  href: "/simulator",            icon: SlidersHorizontal },
  { label: "Copilot",    href: "/copilot",              icon: MessageSquare   },
  { label: "Alerts",     href: "/alerts",               icon: Bell, badge: "3" },
];

const INVESTOR_NAV = [
  { label: "Deal Discovery", href: "/investor-workspace", icon: Briefcase },
];

type NavItem = { label: string; href: string; icon: React.ComponentType<{ className?: string }>; badge?: string };

export function Sidebar() {
  const pathname  = usePathname();
  const { theme, setTheme } = useTheme();
  const { mode, setMode }   = useModeStore();

  const nav: NavItem[] = mode === "founder" ? FOUNDER_NAV : INVESTOR_NAV;

  return (
    <aside className="fixed left-0 top-0 z-30 h-screen w-56 border-r border-border bg-card flex flex-col">

      {/* Logo → home */}
      <Link
        href="/"
        className="flex h-14 items-center gap-2.5 px-4 border-b border-border hover:bg-secondary/40 transition-colors"
      >
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary shrink-0">
          <Zap className="h-3.5 w-3.5 text-primary-foreground" />
        </div>
        <span className="font-bold text-sm tracking-tight">Leadline</span>
      </Link>

      {/* Mode toggle */}
      <div className="px-3 py-3 border-b border-border">
        <div className="flex rounded-lg border border-border bg-secondary p-0.5 text-xs font-medium">
          <button
            onClick={() => setMode("founder")}
            className={cn(
              "flex-1 rounded-md py-1.5 transition-all duration-150",
              mode === "founder"
                ? "bg-card text-foreground shadow-sm font-semibold"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            Founder
          </button>
          <button
            onClick={() => setMode("investor")}
            className={cn(
              "flex-1 rounded-md py-1.5 transition-all duration-150",
              mode === "investor"
                ? "bg-card text-foreground shadow-sm font-semibold"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            Investor
          </button>
        </div>
      </div>

      {/* Company context (founder only) */}
      {mode === "founder" && (
        <div className="px-3 py-2.5 border-b border-border">
          <div className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-primary/8 border border-primary/15">
            <div className="h-5 w-5 rounded-md bg-primary/15 border border-primary/20 flex items-center justify-center text-[10px] font-bold text-primary shrink-0">
              M
            </div>
            <div className="min-w-0">
              <div className="text-xs font-semibold truncate">Meridian AI</div>
              <div className="text-[10px] text-muted-foreground">Series A · $12M</div>
            </div>
          </div>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-0.5">
        {nav.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-all duration-150",
                isActive
                  ? "bg-primary/10 text-primary font-semibold border border-primary/20"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary/60"
              )}
            >
              <item.icon className={cn("h-4 w-4 shrink-0", isActive ? "text-primary" : "")} />
              <span className="flex-1">{item.label}</span>
              {item.badge && (
                <span className="text-[10px] font-semibold tabular-nums bg-destructive/10 text-destructive rounded-md px-1.5 py-0.5">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-3 py-3 border-t border-border space-y-1">
        {/* Theme toggle */}
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="flex w-full items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-colors"
        >
          {theme === "dark" ? (
            <Sun className="h-4 w-4 shrink-0" />
          ) : (
            <Moon className="h-4 w-4 shrink-0" />
          )}
          <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
        </button>

        {/* User */}
        <div className="flex items-center gap-2 px-2.5 py-2">
          <div className="h-6 w-6 rounded-full bg-primary/15 border border-primary/20 flex items-center justify-center text-[10px] font-semibold text-primary shrink-0">
            {mode === "founder" ? "F" : "I"}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium truncate">
              {mode === "founder" ? "Demo Founder" : "Demo Investor"}
            </div>
            <div className="text-[10px] text-muted-foreground">Demo account</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
