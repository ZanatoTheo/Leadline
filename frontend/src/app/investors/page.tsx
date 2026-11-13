"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import {
  Search,
  SlidersHorizontal,
  ChevronRight,
  CheckCircle,
  AlertTriangle,
  X,
  ArrowUpDown,
  Users,
  Info,
  Filter,
} from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { INVESTORS, DEMO_COMPANY, getIntroPathForInvestor } from "@/lib/data/seed";
import { scoreAllInvestors } from "@/lib/scoring/leadScore";
import {
  formatStage,
  formatCheckSize,
  scoreColor,
  conflictColor,
  formatCurrency,
  timeAgo,
} from "@/lib/utils";
import type { FundingStage, Sector } from "@/types";

const ALL_STAGES: { value: FundingStage; label: string }[] = [
  { value: "pre-seed", label: "Pre-Seed" },
  { value: "seed", label: "Seed" },
  { value: "series-a", label: "Series A" },
  { value: "series-b", label: "Series B" },
  { value: "series-c", label: "Series C" },
];

const scoredInvestors = scoreAllInvestors(DEMO_COMPANY);

function ScoreBar({ score, size = "md" }: { score: number; size?: "sm" | "md" }) {
  const color =
    score >= 80 ? "bg-emerald-400" : score >= 60 ? "bg-indigo-400" : score >= 40 ? "bg-amber-400" : "bg-rose-400";
  const textColor = score >= 80 ? "text-emerald-400" : score >= 60 ? "text-indigo-400" : score >= 40 ? "text-amber-400" : "text-rose-400";
  const h = size === "sm" ? "h-1" : "h-1.5";

  return (
    <div className="flex items-center gap-2 w-full">
      <div className={`flex-1 ${h} bg-secondary rounded-full overflow-hidden`}>
        <div
          className={`${h} rounded-full ${color} transition-all duration-700`}
          style={{ width: `${score}%` }}
        />
      </div>
      <span className={`text-sm font-bold tabular-nums w-6 text-right ${textColor}`}>
        {score}
      </span>
    </div>
  );
}

export default function InvestorsPage() {
  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState<FundingStage[]>([]);
  const [hideConflicts, setHideConflicts] = useState(false);
  const [onlyLeads, setOnlyLeads] = useState(false);
  const [sortBy, setSortBy] = useState<"score" | "leadRate" | "activity">("score");

  const filtered = useMemo(() => {
    let results = scoredInvestors;

    if (search) {
      const q = search.toLowerCase();
      results = results.filter(
        (r) =>
          r.investor.name.toLowerCase().includes(q) ||
          r.investor.firm.toLowerCase().includes(q) ||
          r.investor.tags.some((t) => t.toLowerCase().includes(q))
      );
    }

    if (stageFilter.length > 0) {
      results = results.filter((r) =>
        r.investor.stages.some((s) => stageFilter.includes(s))
      );
    }

    if (hideConflicts) {
      results = results.filter((r) => r.score.conflictStatus === "none");
    }

    if (onlyLeads) {
      results = results.filter((r) => r.investor.dna.leadRate >= 0.6);
    }

    if (sortBy === "leadRate") {
      results = [...results].sort((a, b) => b.investor.dna.leadRate - a.investor.dna.leadRate);
    } else if (sortBy === "activity") {
      results = [...results].sort(
        (a, b) =>
          new Date(b.investor.dna.lastActiveDate).getTime() -
          new Date(a.investor.dna.lastActiveDate).getTime()
      );
    }

    return results;
  }, [search, stageFilter, hideConflicts, onlyLeads, sortBy]);

  const toggleStage = (stage: FundingStage) => {
    setStageFilter((prev) =>
      prev.includes(stage) ? prev.filter((s) => s !== stage) : [...prev, stage]
    );
  };

  return (
    <AppLayout>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-1">Investor Discovery</h1>
        <p className="text-muted-foreground text-sm">
          {scoredInvestors.length} investors scored for Meridian AI · Series A · $12M
        </p>
      </div>

      {/* Filters */}
      <Card className="p-4 mb-5">
        <div className="flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 min-w-48">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              className="pl-9 h-8"
              placeholder="Search investors or firms..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {/* Stage filter */}
          <div className="flex items-center gap-1.5">
            {ALL_STAGES.map((s) => (
              <button
                key={s.value}
                onClick={() => toggleStage(s.value)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium border transition-all ${
                  stageFilter.includes(s.value)
                    ? "bg-primary/15 border-primary/40 text-primary"
                    : "border-border text-muted-foreground hover:text-foreground"
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>

          {/* Toggles */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setHideConflicts((v) => !v)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition-all ${
                hideConflicts
                  ? "bg-rose-500/15 border-rose-500/40 text-rose-400"
                  : "border-border text-muted-foreground hover:text-foreground"
              }`}
            >
              <AlertTriangle className="h-3 w-3" />
              Hide conflicts
            </button>
            <button
              onClick={() => setOnlyLeads((v) => !v)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition-all ${
                onlyLeads
                  ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-400"
                  : "border-border text-muted-foreground hover:text-foreground"
              }`}
            >
              <CheckCircle className="h-3 w-3" />
              Lead investors only
            </button>
          </div>

          {/* Sort */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as "score" | "leadRate" | "activity")}
            className="h-8 px-2.5 rounded-lg border border-border bg-secondary/50 text-xs text-foreground"
          >
            <option value="score">Sort: Lead Score</option>
            <option value="leadRate">Sort: Lead Rate</option>
            <option value="activity">Sort: Recent Activity</option>
          </select>

          <div className="text-xs text-muted-foreground ml-auto">
            {filtered.length} investors
          </div>
        </div>
      </Card>

      {/* Evidence disclaimer */}
      <div className="mb-4 flex items-center gap-2 text-xs text-muted-foreground">
        <Info className="h-3.5 w-3.5" />
        All data is synthetic demonstration data. Lead scores are illustrative.
      </div>

      {/* Column headers */}
      <div className="px-5 py-2 grid grid-cols-12 gap-4 text-xs font-medium text-muted-foreground uppercase tracking-wide">
        <div className="col-span-3">Investor</div>
        <div className="col-span-2">Lead Score</div>
        <div className="col-span-2">Check Size</div>
        <div className="col-span-1">Lead Rate</div>
        <div className="col-span-1">Conflict</div>
        <div className="col-span-1">Intro</div>
        <div className="col-span-2">Status</div>
      </div>

      {/* Investor rows */}
      <div className="space-y-1.5">
        {filtered.map(({ investor, score }, i) => {
          const introPath = getIntroPathForInvestor(investor.id);
          const hasIntro = !!introPath?.bestPath;
          const isConflict = score.conflictStatus === "blocking" || score.conflictStatus === "high";

          return (
            <Link href={`/investors/${investor.id}`} key={investor.id}>
              <div
                className={`px-5 py-4 rounded-xl border transition-all hover:shadow-md hover:-translate-y-0.5 hover:border-primary/30 cursor-pointer grid grid-cols-12 gap-4 items-center ${
                  isConflict
                    ? "border-rose-500/25 bg-rose-500/5"
                    : score.totalScore >= 75
                    ? "border-emerald-500/20 bg-emerald-500/5"
                    : "border-border bg-card"
                }`}
              >
                {/* Investor */}
                <div className="col-span-3 flex items-center gap-3">
                  <div className="h-9 w-9 rounded-lg bg-secondary border border-border flex items-center justify-center text-xs font-bold shrink-0">
                    {investor.name[0]}
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">{investor.name}</div>
                    <div className="text-xs text-muted-foreground truncate">{investor.firm}</div>
                  </div>
                </div>

                {/* Score */}
                <div className="col-span-2">
                  <ScoreBar score={score.totalScore} />
                </div>

                {/* Check size */}
                <div className="col-span-2">
                  <span className="text-sm text-muted-foreground">
                    {formatCheckSize(
                      investor.dna.avgCheckSize.min,
                      investor.dna.avgCheckSize.max
                    )}
                  </span>
                </div>

                {/* Lead rate */}
                <div className="col-span-1">
                  <span
                    className={`text-sm font-medium ${
                      investor.dna.leadRate >= 0.65 ? "text-emerald-400" : "text-muted-foreground"
                    }`}
                  >
                    {Math.round(investor.dna.leadRate * 100)}%
                  </span>
                </div>

                {/* Conflict */}
                <div className="col-span-1">
                  <span
                    className={`text-xs font-medium capitalize ${conflictColor(score.conflictStatus)}`}
                  >
                    {score.conflictStatus === "none" ? "None" : score.conflictStatus}
                  </span>
                </div>

                {/* Intro */}
                <div className="col-span-1">
                  {hasIntro ? (
                    <span className="text-xs text-emerald-400 font-medium flex items-center gap-1">
                      <CheckCircle className="h-3 w-3" /> Warm
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </div>

                {/* Status */}
                <div className="col-span-2 flex items-center gap-2 justify-between">
                  <div className="flex flex-wrap gap-1">
                    {score.totalScore >= 80 && score.conflictStatus === "none" && (
                      <Badge variant="success" className="text-[9px] h-4 px-1.5">
                        High match
                      </Badge>
                    )}
                    {isConflict && (
                      <Badge variant="destructive" className="text-[9px] h-4 px-1.5">
                        Conflict
                      </Badge>
                    )}
                    {investor.isActivelyInvesting && (
                      <Badge variant="secondary" className="text-[9px] h-4 px-1.5">
                        Active
                      </Badge>
                    )}
                  </div>
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                </div>
              </div>
            </Link>
          );
        })}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <Users className="h-10 w-10 mx-auto mb-3 opacity-30" />
          <div className="text-sm">No investors match your current filters.</div>
        </div>
      )}
    </AppLayout>
  );
}
