"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Bell,
  TrendingUp,
  AlertTriangle,
  Users,
  Network,
  Sparkles,
  CheckCircle,
  Filter,
  ChevronRight,
} from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DEMO_ALERTS } from "@/lib/data/seed";
import { timeAgo } from "@/lib/utils";
import type { AlertType } from "@/types";

const TYPE_ICONS: Record<AlertType, React.ComponentType<{ className?: string }>> = {
  "new-investor": Sparkles,
  "investor-active": TrendingUp,
  "conflict-change": AlertTriangle,
  "intro-opportunity": Network,
  "momentum-shift": TrendingUp,
};

const TYPE_LABELS: Record<AlertType, string> = {
  "new-investor": "New investor",
  "investor-active": "Investor active",
  "conflict-change": "Conflict change",
  "intro-opportunity": "Intro opportunity",
  "momentum-shift": "Momentum shift",
};

const SEVERITY_COLORS = {
  opportunity: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  warning: "text-rose-400 bg-rose-500/10 border-rose-500/20",
  info: "text-indigo-400 bg-indigo-500/10 border-indigo-500/20",
};

const SEVERITY_DOT = {
  opportunity: "bg-emerald-400",
  warning: "bg-rose-400",
  info: "bg-indigo-400",
};

export default function AlertsPage() {
  const [filter, setFilter] = useState<"all" | "unread" | "opportunity" | "warning">("all");
  const [alerts, setAlerts] = useState(DEMO_ALERTS);

  const filtered = alerts.filter((a) => {
    if (filter === "unread") return !a.read;
    if (filter === "opportunity") return a.severity === "opportunity";
    if (filter === "warning") return a.severity === "warning";
    return true;
  });

  const unreadCount = alerts.filter((a) => !a.read).length;

  const markAllRead = () =>
    setAlerts((prev) => prev.map((a) => ({ ...a, read: true })));

  const markRead = (id: string) =>
    setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, read: true } : a)));

  return (
    <AppLayout>
      <div className="mb-5 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            Alerts & Activity
            {unreadCount > 0 && (
              <Badge variant="destructive" className="text-xs">
                {unreadCount} new
              </Badge>
            )}
          </h1>
          <p className="text-muted-foreground text-sm">
            Real-time changes in investor activity, portfolio status, and introduction opportunities.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={markAllRead} className="text-xs">
          <CheckCircle className="h-3.5 w-3.5 mr-1.5" />
          Mark all read
        </Button>
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-2 mb-5">
        {[
          { value: "all", label: "All alerts", count: alerts.length },
          { value: "unread", label: "Unread", count: unreadCount },
          { value: "opportunity", label: "Opportunities", count: alerts.filter((a) => a.severity === "opportunity").length },
          { value: "warning", label: "Warnings", count: alerts.filter((a) => a.severity === "warning").length },
        ].map((tab) => (
          <button
            key={tab.value}
            onClick={() => setFilter(tab.value as typeof filter)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-all ${
              filter === tab.value
                ? "bg-primary/15 border-primary/40 text-primary"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab.label}
            <span
              className={`text-[10px] px-1.5 rounded-md ${
                filter === tab.value ? "bg-primary/20" : "bg-secondary"
              }`}
            >
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* Alert list */}
      <div className="space-y-3">
        {filtered.map((alert) => {
          const Icon = TYPE_ICONS[alert.type];
          return (
            <div
              key={alert.id}
              className={`rounded-xl border p-4 transition-all ${
                !alert.read
                  ? SEVERITY_COLORS[alert.severity]
                  : "border-border bg-card opacity-70"
              }`}
              onClick={() => markRead(alert.id)}
            >
              <div className="flex items-start gap-3">
                <div
                  className={`h-9 w-9 rounded-lg flex items-center justify-center shrink-0 ${
                    !alert.read
                      ? alert.severity === "opportunity"
                        ? "bg-emerald-500/20"
                        : alert.severity === "warning"
                        ? "bg-rose-500/20"
                        : "bg-indigo-500/20"
                      : "bg-secondary"
                  }`}
                >
                  <Icon
                    className={`h-4 w-4 ${
                      !alert.read
                        ? alert.severity === "opportunity"
                          ? "text-emerald-400"
                          : alert.severity === "warning"
                          ? "text-rose-400"
                          : "text-indigo-400"
                        : "text-muted-foreground"
                    }`}
                  />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-3 mb-1">
                    <div className="flex items-center gap-2">
                      {!alert.read && (
                        <div className={`h-1.5 w-1.5 rounded-full shrink-0 ${SEVERITY_DOT[alert.severity]}`} />
                      )}
                      <span className="text-sm font-semibold leading-tight">
                        {alert.title}
                      </span>
                    </div>
                    <span className="text-[10px] text-muted-foreground shrink-0">
                      {timeAgo(alert.createdAt)}
                    </span>
                  </div>

                  <p className="text-sm text-muted-foreground leading-relaxed mb-3">
                    {alert.description}
                  </p>

                  <div className="flex items-center gap-3">
                    <Badge variant="secondary" className="text-[9px] h-4">
                      {TYPE_LABELS[alert.type]}
                    </Badge>
                    {alert.investorId && (
                      <Link href={`/investors/${alert.investorId}`}>
                        <Button variant="ghost" size="sm" className="h-6 text-xs gap-1 px-2">
                          {alert.action ?? "View investor"}
                          <ChevronRight className="h-3 w-3" />
                        </Button>
                      </Link>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}

        {filtered.length === 0 && (
          <div className="text-center py-16 text-muted-foreground">
            <Bell className="h-10 w-10 mx-auto mb-3 opacity-30" />
            <div className="text-sm">No alerts matching your filter.</div>
          </div>
        )}
      </div>

      {/* Momentum engine status */}
      <Card className="mt-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-primary" />
            Activity monitor
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground leading-relaxed mb-3">
            Monitors changes in investor activity, portfolio conflicts, and co-investment relationships.
            Lead scores update automatically when significant changes are detected.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Investors monitored", value: "10" },
              { label: "Signal sources", value: "4" },
              { label: "Score updates (30d)", value: "7" },
              { label: "New opportunities", value: "2" },
            ].map((stat) => (
              <div key={stat.label} className="text-center p-3 rounded-lg bg-secondary/40 border border-border">
                <div className="text-lg font-bold">{stat.value}</div>
                <div className="text-[10px] text-muted-foreground">{stat.label}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </AppLayout>
  );
}
