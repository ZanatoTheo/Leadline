"use client";

import { useState } from "react";
import {
  Search,
  TrendingUp,
  Users,
  Zap,
  ChevronRight,
  Activity,
  Target,
} from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

// Demo startups that investors might discover
const DEAL_SIGNALS = [
  {
    id: "meridian-ai",
    name: "Meridian AI",
    sector: "AI / ML",
    stage: "Series A",
    raising: "$12M",
    score: 91,
    signals: ["Strong NRR (142%)", "AI-native product", "Existing tier-1 backer"],
    lastSignal: "Active fundraise",
    tags: ["AI", "Customer Success", "B2B SaaS"],
  },
  {
    id: "forge-data",
    name: "ForgeData",
    sector: "Data Infrastructure",
    stage: "Seed",
    raising: "$4M",
    score: 74,
    signals: ["Technical founders", "Strong product market fit", "Growing pipeline"],
    lastSignal: "Hiring VP Sales",
    tags: ["Data", "Infrastructure", "API"],
  },
  {
    id: "atlas-health",
    name: "AtlasHealth",
    sector: "Healthtech",
    stage: "Series A",
    raising: "$8M",
    score: 68,
    signals: ["FDA clearance", "Hospital network signed", "Repeat founders"],
    lastSignal: "Clinical results published",
    tags: ["Healthcare", "AI", "Diagnostics"],
  },
  {
    id: "current-iq",
    name: "CurrentIQ",
    sector: "Fintech",
    stage: "Seed",
    raising: "$5M",
    score: 62,
    signals: ["First-mover in category", "Strong founder network", "Early revenue"],
    lastSignal: "New regulation tailwind",
    tags: ["Fintech", "Compliance", "B2B"],
  },
];

const THESIS = [
  "AI-native B2B SaaS applications with defensible data moats",
  "Enterprise software replacing manual workflows with AI",
  "Vertical SaaS for underserved industries",
];

export default function InvestorWorkspacePage() {
  const [search, setSearch] = useState("");

  const filtered = DEAL_SIGNALS.filter(
    (d) =>
      !search ||
      d.name.toLowerCase().includes(search.toLowerCase()) ||
      d.sector.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <AppLayout>
      <div className="mb-5">
        <h1 className="text-2xl font-bold mb-1">Deal Discovery</h1>
        <p className="text-muted-foreground text-sm">
          Discover startups that match your investment thesis and show strong fundraising signals.
          <Badge variant="secondary" className="ml-2 text-[10px]">Synthetic demo data</Badge>
        </p>
      </div>

      <div className="grid lg:grid-cols-3 gap-5">
        {/* Thesis & Filters */}
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Target className="h-4 w-4 text-indigo-400" />
                Investment thesis
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {THESIS.map((t) => (
                <div key={t} className="flex items-start gap-2 text-xs text-muted-foreground">
                  <div className="h-1.5 w-1.5 rounded-full bg-indigo-400 mt-1 shrink-0" />
                  {t}
                </div>
              ))}
              <Button variant="outline" size="sm" className="w-full mt-3 text-xs gap-1.5">
                <Zap className="h-3 w-3" />
                Generate AI thesis update
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Matching signals</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {[
                { label: "Startups in thesis", value: 4 },
                { label: "Raising now", value: 4 },
                { label: "High signal score", value: 2 },
                { label: "Warm intro possible", value: 3 },
              ].map((s) => (
                <div key={s.label} className="flex justify-between text-xs">
                  <span className="text-muted-foreground">{s.label}</span>
                  <span className="font-semibold">{s.value}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        {/* Deal flow */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                className="pl-9 h-8"
                placeholder="Search startups..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <Badge variant="secondary">{filtered.length} startups</Badge>
          </div>

          {filtered.map((deal) => (
            <Card
              key={deal.id}
              className="p-4 hover:border-primary/30 hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 cursor-pointer"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-xl bg-secondary border border-border flex items-center justify-center text-sm font-bold">
                    {deal.name[0]}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{deal.name}</span>
                      <Badge variant="secondary" className="text-[9px] h-4">
                        {deal.stage}
                      </Badge>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {deal.sector} · Raising {deal.raising}
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <div
                    className={`text-lg font-bold ${
                      deal.score >= 80
                        ? "text-emerald-400"
                        : deal.score >= 65
                        ? "text-indigo-400"
                        : "text-amber-400"
                    }`}
                  >
                    {deal.score}
                  </div>
                  <div className="text-[10px] text-muted-foreground">signal score</div>
                </div>
              </div>

              <div className="space-y-1 mb-3">
                {deal.signals.map((s) => (
                  <div key={s} className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Activity className="h-3 w-3 text-emerald-400 shrink-0" />
                    {s}
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between">
                <div className="flex flex-wrap gap-1">
                  {deal.tags.map((tag) => (
                    <Badge key={tag} variant="secondary" className="text-[9px] h-4">
                      {tag}
                    </Badge>
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-indigo-400">{deal.lastSignal}</span>
                  <Button variant="outline" size="sm" className="h-7 text-xs gap-1">
                    View <ChevronRight className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </AppLayout>
  );
}
