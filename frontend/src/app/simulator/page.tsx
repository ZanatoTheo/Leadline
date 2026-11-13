"use client";

import React, { useState, useMemo } from "react";
import {
  Sliders,
  RefreshCw,
  TrendingUp,
  Users,
  AlertTriangle,
  Network,
  CheckCircle,
  Info,
  ArrowRight,
  DollarSign,
  Clock,
  Target,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  RadialBarChart,
  RadialBar,
  Cell,
  Legend,
} from "recharts";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { INVESTORS, DEMO_COMPANY } from "@/lib/data/seed";
import { calculateLeadScore, scoreAllInvestors } from "@/lib/scoring/leadScore";
import { formatCurrency, formatStage } from "@/lib/utils";
import type { FundingStage, Sector, Geography } from "@/types";

const STAGES: FundingStage[] = ["pre-seed", "seed", "series-a", "series-b", "series-c"];
const SECTORS: Sector[] = ["ai-ml", "saas", "enterprise", "fintech", "healthtech", "climate"];
const GEOS: Geography[] = ["north-america", "europe", "asia", "global"];

function computeSimulation(config: {
  targetRaise: number;
  stage: FundingStage;
  sectors: Sector[];
  geographies: Geography[];
  timelineMonths: number;
  hideConflicts: boolean;
  minLeadRate: number;
}) {
  const company = {
    ...DEMO_COMPANY,
    targetRaise: config.targetRaise,
    stage: config.stage,
  };

  const scored = scoreAllInvestors(company);

  const matching = scored.filter((s) => {
    // Stage filter
    if (!s.investor.stages.includes(config.stage)) return false;
    // Sector filter
    if (config.sectors.length > 0) {
      const overlap = s.investor.sectors.some((sector) => config.sectors.includes(sector));
      if (!overlap) return false;
    }
    // Geography filter
    if (config.geographies.length > 0) {
      const overlap = s.investor.geography.some(
        (geo) => config.geographies.includes(geo) || geo === "global"
      );
      if (!overlap) return false;
    }
    // Lead rate filter
    if (s.investor.dna.leadRate < config.minLeadRate) return false;
    return true;
  });

  const conflicts = matching.filter(
    (s) => s.score.conflictStatus !== "none"
  );

  const noConflict = config.hideConflicts
    ? matching.filter((s) => s.score.conflictStatus === "none")
    : matching;

  const warmIntros = noConflict.filter((s) => {
    const { getIntroPathForInvestor } = require("@/lib/data/seed");
    return !!getIntroPathForInvestor(s.investor.id)?.bestPath;
  }).length;

  const checkSizeMatch = matching.filter((s) => {
    const { min, max } = s.investor.dna.avgCheckSize;
    const leadCheckMin = config.targetRaise * 0.15;
    const leadCheckMax = config.targetRaise * 0.5;
    return max >= leadCheckMin && min <= leadCheckMax;
  }).length;

  const highMatch = noConflict.filter((s) => s.score.totalScore >= 70).length;

  // Scenario bar chart data
  const scoreDistribution = [
    { label: "80–100", count: noConflict.filter((s) => s.score.totalScore >= 80).length, color: "#34d399" },
    { label: "60–79", count: noConflict.filter((s) => s.score.totalScore >= 60 && s.score.totalScore < 80).length, color: "#818cf8" },
    { label: "40–59", count: noConflict.filter((s) => s.score.totalScore >= 40 && s.score.totalScore < 60).length, color: "#fbbf24" },
    { label: "<40", count: noConflict.filter((s) => s.score.totalScore < 40).length, color: "#fb7185" },
  ];

  const tradeoffs: string[] = [];
  if (config.minLeadRate > 0.6) tradeoffs.push("High lead rate filter reduces pool but improves quality");
  if (config.hideConflicts) tradeoffs.push("Conflict exclusion removes overlapping investors, improving signal");
  if (config.timelineMonths < 4) tradeoffs.push("Short timeline favours investors with fast decision cycles");
  if (config.targetRaise > 15) tradeoffs.push("Larger raise requires investors with bigger check sizes, reducing pool");
  if (config.sectors.length <= 1) tradeoffs.push("Single sector focus reduces pool but improves thesis alignment");

  let recommendation = "";
  if (highMatch >= 5) {
    recommendation = `Strong investor pool with ${highMatch} high-match leads. Prioritise ${noConflict.slice(0, 2).map((s) => s.investor.firm).join(" and ")} based on current parameters.`;
  } else if (highMatch >= 2) {
    recommendation = `Moderate pool with ${highMatch} high-match leads. Consider expanding stage or sector filters to increase options.`;
  } else {
    recommendation = `Limited pool under current parameters. Recommend broadening stage range or reducing lead-rate threshold to surface more options.`;
  }

  return {
    total: noConflict.length,
    conflicts: conflicts.length,
    warmIntros,
    checkSizeMatch,
    highMatch,
    scoreDistribution,
    topInvestors: noConflict.slice(0, 5),
    tradeoffs,
    recommendation,
  };
}

export default function SimulatorPage() {
  const [targetRaise, setTargetRaise] = useState([12]);
  const [stage, setStage] = useState<FundingStage>("series-a");
  const [sectors, setSectors] = useState<Sector[]>(["ai-ml", "saas"]);
  const [geographies, setGeographies] = useState<Geography[]>(["north-america"]);
  const [timelineMonths, setTimelineMonths] = useState([6]);
  const [hideConflicts, setHideConflicts] = useState(true);
  const [minLeadRate, setMinLeadRate] = useState([0.5]);
  const [scenarioA, setScenarioA] = useState(false);

  const result = useMemo(
    () =>
      computeSimulation({
        targetRaise: targetRaise[0],
        stage,
        sectors,
        geographies,
        timelineMonths: timelineMonths[0],
        hideConflicts,
        minLeadRate: minLeadRate[0],
      }),
    [targetRaise, stage, sectors, geographies, timelineMonths, hideConflicts, minLeadRate]
  );

  // Comparison scenario — broader params
  const resultB = useMemo(
    () =>
      computeSimulation({
        targetRaise: targetRaise[0],
        stage,
        sectors: ["ai-ml", "saas", "enterprise", "fintech"],
        geographies: ["north-america", "europe"],
        timelineMonths: 9,
        hideConflicts: false,
        minLeadRate: 0.4,
      }),
    [targetRaise, stage]
  );

  const toggleSector = (s: Sector) =>
    setSectors((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));

  const toggleGeo = (g: Geography) =>
    setGeographies((prev) => (prev.includes(g) ? prev.filter((x) => x !== g) : [...prev, g]));

  return (
    <AppLayout>
      <div className="mb-5">
        <h1 className="text-2xl font-bold mb-1">Raise Simulator</h1>
        <p className="text-muted-foreground text-sm">
          Model your fundraising parameters and see how they affect your investor pool in real time.
          A high match count does not imply guaranteed fundraising success.
        </p>
      </div>

      <div className="grid lg:grid-cols-3 gap-5">
        {/* Controls */}
        <Card className="lg:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2">
              <Sliders className="h-4 w-4 text-primary" />
              Fundraising parameters
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Target raise */}
            <div>
              <div className="flex justify-between mb-2">
                <label className="text-sm font-medium">Target raise</label>
                <span className="text-sm font-bold text-primary">{formatCurrency(targetRaise[0])}</span>
              </div>
              <Slider
                min={1}
                max={50}
                step={1}
                value={targetRaise}
                onValueChange={setTargetRaise}
              />
              <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
                <span>$1M</span>
                <span>$50M</span>
              </div>
            </div>

            {/* Stage */}
            <div>
              <label className="text-sm font-medium mb-2 block">Funding stage</label>
              <div className="flex flex-wrap gap-1.5">
                {STAGES.map((s) => (
                  <button
                    key={s}
                    onClick={() => setStage(s)}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium border transition-all ${
                      stage === s
                        ? "bg-primary/15 border-primary/40 text-primary"
                        : "border-border text-muted-foreground hover:border-primary/30"
                    }`}
                  >
                    {formatStage(s)}
                  </button>
                ))}
              </div>
            </div>

            {/* Sectors */}
            <div>
              <label className="text-sm font-medium mb-2 block">Sectors</label>
              <div className="flex flex-wrap gap-1.5">
                {SECTORS.map((s) => (
                  <button
                    key={s}
                    onClick={() => toggleSector(s)}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium border transition-all ${
                      sectors.includes(s)
                        ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-400"
                        : "border-border text-muted-foreground hover:border-primary/30"
                    }`}
                  >
                    {s.replace("-", "/")}
                  </button>
                ))}
              </div>
            </div>

            {/* Geographies */}
            <div>
              <label className="text-sm font-medium mb-2 block">Geographies</label>
              <div className="flex flex-wrap gap-1.5">
                {GEOS.map((g) => (
                  <button
                    key={g}
                    onClick={() => toggleGeo(g)}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium border transition-all ${
                      geographies.includes(g)
                        ? "bg-indigo-500/15 border-indigo-500/40 text-indigo-400"
                        : "border-border text-muted-foreground hover:border-primary/30"
                    }`}
                  >
                    {g.replace("-", " ")}
                  </button>
                ))}
              </div>
            </div>

            {/* Min lead rate */}
            <div>
              <div className="flex justify-between mb-2">
                <label className="text-sm font-medium">Min lead rate</label>
                <span className="text-sm font-bold text-primary">
                  {Math.round(minLeadRate[0] * 100)}%
                </span>
              </div>
              <Slider
                min={0.1}
                max={0.9}
                step={0.05}
                value={minLeadRate}
                onValueChange={setMinLeadRate}
              />
            </div>

            {/* Timeline */}
            <div>
              <div className="flex justify-between mb-2">
                <label className="text-sm font-medium">Fundraising timeline</label>
                <span className="text-sm font-bold text-primary">{timelineMonths[0]} months</span>
              </div>
              <Slider
                min={2}
                max={18}
                step={1}
                value={timelineMonths}
                onValueChange={setTimelineMonths}
              />
            </div>

            {/* Toggles */}
            <div className="space-y-2">
              <button
                onClick={() => setHideConflicts((v) => !v)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg border text-sm transition-all ${
                  hideConflicts
                    ? "border-rose-500/30 bg-rose-500/5 text-rose-400"
                    : "border-border text-muted-foreground"
                }`}
              >
                <span>Exclude portfolio conflicts</span>
                <div
                  className={`h-4 w-7 rounded-full transition-all ${
                    hideConflicts ? "bg-rose-400" : "bg-secondary"
                  }`}
                >
                  <div
                    className={`h-3 w-3 rounded-full bg-white m-0.5 transition-transform ${
                      hideConflicts ? "translate-x-3" : "translate-x-0"
                    }`}
                  />
                </div>
              </button>
            </div>
          </CardContent>
        </Card>

        {/* Results */}
        <div className="lg:col-span-2 space-y-5">
          {/* KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              {
                label: "Matching investors",
                value: result.total,
                icon: Users,
                color: "text-indigo-400",
              },
              {
                label: "High-match leads",
                value: result.highMatch,
                icon: Target,
                color: "text-emerald-400",
              },
              {
                label: "Conflicts found",
                value: result.conflicts,
                icon: AlertTriangle,
                color: "text-rose-400",
              },
              {
                label: "Warm intros",
                value: result.warmIntros,
                icon: Network,
                color: "text-amber-400",
              },
            ].map((kpi) => (
              <Card key={kpi.label} className="p-4">
                <kpi.icon className={`h-4 w-4 ${kpi.color} mb-2`} />
                <div className="text-2xl font-bold mb-0.5">{kpi.value}</div>
                <div className="text-xs text-muted-foreground">{kpi.label}</div>
              </Card>
            ))}
          </div>

          {/* Scenario comparison */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Scenario comparison</CardTitle>
              <p className="text-xs text-muted-foreground">
                Current parameters vs. broader scenario (all sectors, Europe added, no conflict exclusion)
              </p>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-5 gap-2 text-xs">
                <div className="col-span-2 font-medium text-muted-foreground">Metric</div>
                <div className="font-medium text-indigo-400 text-center">Your scenario</div>
                <div className="font-medium text-muted-foreground text-center">Broader</div>
                <div className="font-medium text-muted-foreground text-center">Difference</div>
                {[
                  { label: "Total investors", a: result.total, b: resultB.total },
                  { label: "High-match", a: result.highMatch, b: resultB.highMatch },
                  { label: "Conflicts", a: result.conflicts, b: resultB.conflicts },
                  { label: "Warm intros", a: result.warmIntros, b: resultB.warmIntros },
                  { label: "Check-size match", a: result.checkSizeMatch, b: resultB.checkSizeMatch },
                ].map((row) => (
                  <React.Fragment key={row.label}>
                    <div className="col-span-2 py-2 border-t border-border text-muted-foreground">
                      {row.label}
                    </div>
                    <div className="py-2 border-t border-border font-bold text-indigo-400 text-center">
                      {row.a}
                    </div>
                    <div className="py-2 border-t border-border text-center">
                      {row.b}
                    </div>
                    <div
                      className={`py-2 border-t border-border text-center font-medium ${
                        row.b - row.a > 0 ? "text-emerald-400" : row.b - row.a < 0 ? "text-rose-400" : "text-muted-foreground"
                      }`}
                    >
                      {row.b - row.a > 0 ? `+${row.b - row.a}` : row.b - row.a}
                    </div>
                  </React.Fragment>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Score distribution */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Score distribution (current scenario)</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={result.scoreDistribution} barCategoryGap="30%">
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{
                      background: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                      fontSize: "12px",
                      color: "hsl(var(--popover-foreground))",
                    }}
                  />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {result.scoreDistribution.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Trade-offs and recommendation */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-indigo-400" />
                Strategy recommendation
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground leading-relaxed mb-4">
                {result.recommendation}
              </p>
              {result.tradeoffs.length > 0 && (
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                    Parameter trade-offs
                  </div>
                  <div className="space-y-1.5">
                    {result.tradeoffs.map((t) => (
                      <div key={t} className="flex items-start gap-2 text-xs text-muted-foreground">
                        <Info className="h-3.5 w-3.5 text-indigo-400 shrink-0 mt-0.5" />
                        {t}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppLayout>
  );
}
