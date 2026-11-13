"use client";

import Link from "next/link";
import {
  TrendingUp,
  Users,
  AlertCircle,
  ArrowRight,
  CheckCircle,
  Clock,
  Zap,
  Bell,
  Target,
  Network,
  ArrowUpRight,
  ChevronRight,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
} from "recharts";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { INVESTORS, DEMO_ALERTS, DEMO_COMPANY } from "@/lib/data/seed";
import { scoreAllInvestors } from "@/lib/scoring/leadScore";
import { formatCurrency, timeAgo, formatStage, scoreColor } from "@/lib/utils";

// Pre-compute scores
const scoredInvestors = scoreAllInvestors(DEMO_COMPANY).slice(0, 5);

const MOMENTUM_DATA = [
  { month: "May", investors: 3 },
  { month: "Jun", investors: 4 },
  { month: "Jul", investors: 5 },
  { month: "Aug", investors: 4 },
  { month: "Sep", investors: 7 },
  { month: "Oct", investors: 8 },
  { month: "Nov", investors: 10 },
];

const RADAR_DATA = [
  { dimension: "Lead Rate", value: 78 },
  { dimension: "Stage Fit", value: 85 },
  { dimension: "Sector Fit", value: 90 },
  { dimension: "Check Size", value: 72 },
  { dimension: "Warm Intros", value: 65 },
  { dimension: "Activity", value: 80 },
];

const NEXT_ACTIONS = [
  {
    priority: "high",
    action: "Request warm introduction to Lucinda Marsh (Accel) via Sarah Kim at First Round",
    investorId: "accel-partners",
    due: "This week",
  },
  {
    priority: "high",
    action: "Prepare AI-generated investor brief for Priya Nair (General Catalyst)",
    investorId: "general-catalyst",
    due: "This week",
  },
  {
    priority: "medium",
    action: "Research Yemi Okonkwo's (Bessemer) recent investments in AI-SaaS",
    investorId: "bessemer",
    due: "Next week",
  },
  {
    priority: "low",
    action: "Confirm portfolio conflict with Index Ventures before approaching",
    investorId: "index-ventures",
    due: "Before outreach",
  },
];

function ScoreRing({ score }: { score: number }) {
  const color =
    score >= 80 ? "#34d399" : score >= 60 ? "#818cf8" : score >= 40 ? "#fbbf24" : "#fb7185";
  const circumference = 2 * Math.PI * 20;
  const offset = circumference - (score / 100) * circumference;

  return (
    <svg width="52" height="52" className="-rotate-90">
      <circle cx="26" cy="26" r="20" fill="none" stroke="hsl(var(--border))" strokeWidth="3" />
      <circle
        cx="26"
        cy="26"
        r="20"
        fill="none"
        stroke={color}
        strokeWidth="3"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        style={{ transition: "stroke-dashoffset 1s ease" }}
      />
      <text
        x="26"
        y="26"
        textAnchor="middle"
        dominantBaseline="middle"
        className="rotate-90"
        style={{
          transform: "rotate(90deg) translate(0, 0)",
          transformOrigin: "26px 26px",
          fill: color,
          fontSize: "11px",
          fontWeight: "700",
        }}
      >
        {score}
      </text>
    </svg>
  );
}

export default function DashboardPage() {
  const unreadAlerts = DEMO_ALERTS.filter((a) => !a.read);
  const highMatch = scoredInvestors.filter((s) => s.score.totalScore >= 70).length;
  const conflicts = scoredInvestors.filter((s) => s.score.conflictStatus !== "none").length;
  const warmIntros = 3;

  return (
    <AppLayout>
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <h1 className="text-2xl font-bold">Fundraising Intelligence</h1>
            <Badge variant="secondary" className="text-xs font-medium">
              Series A · $12M
            </Badge>
          </div>
          <p className="text-muted-foreground text-sm">
            Meridian AI · 10 investors scored · <span className="text-emerald-600 dark:text-emerald-400 font-medium">{highMatch} high-match leads identified</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/alerts">
            <Button variant="outline" size="sm" className="gap-2">
              <Bell className="h-3.5 w-3.5" />
              {unreadAlerts.length} new
            </Button>
          </Link>
          <Link href="/copilot">
            <Button size="sm" className="gap-2 shadow-sm">
              <Zap className="h-3.5 w-3.5" />
              Open Copilot
            </Button>
          </Link>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {[
          {
            label: "High-match investors",
            value: highMatch,
            change: "+2 this week",
            positive: true,
            icon: Target,
            bg: "bg-emerald-500/10 border-emerald-500/20",
            color: "text-emerald-500",
          },
          {
            label: "Portfolio conflicts",
            value: conflicts,
            change: "1 blocking",
            positive: false,
            icon: AlertCircle,
            bg: "bg-rose-500/10 border-rose-500/20",
            color: "text-rose-500",
          },
          {
            label: "Warm intro paths",
            value: warmIntros,
            change: "2 strong",
            positive: true,
            icon: Network,
            bg: "bg-indigo-500/10 border-indigo-500/20",
            color: "text-indigo-500",
          },
          {
            label: "Active investors",
            value: 8,
            change: "Deploying now",
            positive: true,
            icon: TrendingUp,
            bg: "bg-amber-500/10 border-amber-500/20",
            color: "text-amber-500",
          },
        ].map((kpi) => (
          <Card key={kpi.label} className="p-4 hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between mb-3">
              <div className={`h-9 w-9 rounded-lg border flex items-center justify-center ${kpi.bg}`}>
                <kpi.icon className={`h-4.5 w-4.5 ${kpi.color}`} />
              </div>
              <ArrowUpRight className={`h-3.5 w-3.5 mt-0.5 ${kpi.positive ? "text-emerald-500" : "text-rose-500"}`} />
            </div>
            <div className="text-2xl font-bold mb-0.5">{kpi.value}</div>
            <div className="text-xs text-muted-foreground">{kpi.label}</div>
            <div className={`text-xs mt-1 font-medium ${kpi.positive ? "text-emerald-500 dark:text-emerald-400" : "text-rose-500 dark:text-rose-400"}`}>
              {kpi.change}
            </div>
          </Card>
        ))}
      </div>

      {/* Main grid */}
      <div className="grid lg:grid-cols-3 gap-5">
        {/* Top investors */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader className="pb-3 flex flex-row items-center justify-between">
              <CardTitle>Lead investor recommendations</CardTitle>
              <Link href="/investors">
                <Button variant="ghost" size="sm" className="gap-1 text-xs">
                  View all <ArrowRight className="h-3 w-3" />
                </Button>
              </Link>
            </CardHeader>
            <CardContent className="p-0">
              {scoredInvestors.map((item, i) => (
                <Link href={`/investors/${item.investor.id}`} key={item.investor.id}>
                  <div className="px-5 py-4 border-t border-border first:border-0 hover:bg-secondary/20 transition-colors flex items-center gap-4">
                    <div className="shrink-0">
                      <ScoreRing score={item.score.totalScore} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5 leading-none">
                        <span className="text-sm font-semibold truncate">{item.investor.name}</span>
                        <span className="text-xs text-muted-foreground">· {item.investor.firm}</span>
                        {item.score.conflictStatus === "blocking" && (
                          <Badge variant="destructive" className="text-[10px] h-4 px-1.5">
                            Conflict
                          </Badge>
                        )}
                        {item.score.conflictStatus === "none" &&
                          item.score.totalScore >= 70 && (
                            <Badge variant="success" className="text-[10px] h-4 px-1.5">
                              High match
                            </Badge>
                          )}
                      </div>
                      <div className="text-xs text-muted-foreground truncate">
                        {item.score.recommendedAction}
                      </div>
                      <div className="flex items-center gap-3 mt-1.5">
                        {item.score.keyStrengths.slice(0, 2).map((s) => (
                          <span key={s} className="text-[10px] text-emerald-400 flex items-center gap-1">
                            <CheckCircle className="h-2.5 w-2.5" /> {s}
                          </span>
                        ))}
                      </div>
                    </div>
                    <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
                  </div>
                </Link>
              ))}
            </CardContent>
          </Card>
        </div>

        {/* Right column */}
        <div className="space-y-5">
          {/* Investor activity chart */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Investor pipeline momentum</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={120}>
                <AreaChart data={MOMENTUM_DATA} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="investorGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="month"
                    tick={{ fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{
                      background: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                      fontSize: "12px",
                      color: "hsl(var(--popover-foreground))",
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="investors"
                    stroke="hsl(var(--primary))"
                    strokeWidth={2}
                    fill="url(#investorGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Company metrics */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Meridian AI — Key metrics</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {DEMO_COMPANY.keyMetrics.map((m) => (
                <div key={m.label} className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">{m.label}</span>
                  <span className="text-sm font-semibold text-foreground">{m.value}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Next actions */}
      <Card className="mt-5">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle>Recommended next actions</CardTitle>
            <Link href="/copilot">
              <Button size="sm" variant="outline" className="gap-1.5 text-xs">
                <Zap className="h-3 w-3 text-primary" />
                Execute with Copilot
              </Button>
            </Link>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {NEXT_ACTIONS.map((action, i) => (
            <div
              key={i}
              className="px-5 py-3.5 border-t border-border first:border-0 flex items-center gap-4"
            >
              <div
                className={`h-2 w-2 rounded-full shrink-0 ${
                  action.priority === "high"
                    ? "bg-rose-400"
                    : action.priority === "medium"
                    ? "bg-amber-400"
                    : "bg-muted-foreground"
                }`}
              />
              <div className="flex-1 text-sm">{action.action}</div>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground shrink-0">
                <Clock className="h-3 w-3" />
                {action.due}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Alerts */}
      {unreadAlerts.length > 0 && (
        <Card className="mt-5 border-border">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-4 w-4 text-primary" />
                {unreadAlerts.length} new alerts
              </CardTitle>
              <Link href="/alerts">
                <Button variant="ghost" size="sm" className="text-xs gap-1">
                  View all <ArrowRight className="h-3 w-3" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {unreadAlerts.slice(0, 2).map((alert) => (
              <div
                key={alert.id}
                className="px-5 py-3 border-t border-border first:border-0"
              >
                <div className="flex items-start gap-3">
                  <div
                    className={`h-2 w-2 rounded-full mt-1.5 shrink-0 ${
                      alert.severity === "opportunity"
                        ? "bg-emerald-400"
                        : alert.severity === "warning"
                        ? "bg-rose-400"
                        : "bg-indigo-400"
                    }`}
                  />
                  <div>
                    <div className="text-sm font-medium mb-0.5">{alert.title}</div>
                    <div className="text-xs text-muted-foreground">{alert.description}</div>
                  </div>
                  <div className="text-[10px] text-muted-foreground shrink-0 mt-0.5">
                    {timeAgo(alert.createdAt)}
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </AppLayout>
  );
}
