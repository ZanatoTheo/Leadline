"use client";

import { CheckCircle2, CircleSlash, GitBranch } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FitReport } from "@/lib/leadline/match-types";
import { fmtEur, fmtMonth } from "@/lib/leadline/format";
import { SourceLinks } from "./shared";

export function FitScore({ score }: { score: number }) {
  const tone =
    score >= 75 ? "text-emerald-600 dark:text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
    : score >= 50 ? "text-indigo-600 dark:text-indigo-400 border-indigo-500/30 bg-indigo-500/10"
    : score >= 30 ? "text-amber-600 dark:text-amber-400 border-amber-500/30 bg-amber-500/10"
    : "text-rose-600 dark:text-rose-400 border-rose-500/30 bg-rose-500/10";
  return (
    <div className={cn("flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-xl border", tone)}>
      <span className="text-lg font-bold leading-none tabular-nums">{score}</span>
      <span className="text-[9px] font-semibold uppercase tracking-wide">fit</span>
    </div>
  );
}

/** The evidence behind a fit score, one line per point, each with sources. */
export function FitPoints({ fit }: { fit: FitReport }) {
  return (
    <ul className="space-y-1.5">
      {fit.points.map((p) => (
        <li key={p.label} className="flex items-start gap-2 text-sm">
          {p.good ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
          ) : (
            <CircleSlash className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          <span>
            <span className="font-medium">{p.label}</span>
            <span className="text-muted-foreground"> · {p.detail}</span>{" "}
            {p.sources.length > 0 && <SourceLinks sources={p.sources} />}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** "Looks like your Factorly: Seed → Series A" path strip. */
export function PortfolioTwinPaths({ fit }: { fit: FitReport }) {
  if (!fit.portfolioTwins.length) return null;
  return (
    <div className="space-y-1.5">
      {fit.portfolioTwins.map((t) => (
        <div key={t.company} className="flex flex-wrap items-center gap-1.5 text-xs">
          <GitBranch className="h-3 w-3 text-violet-500" />
          <span className="font-medium">{t.company}</span>
          <span className="text-muted-foreground">
            {t.rounds.map((r) => `${r.round} ${fmtEur(r.amountEurM)} (${fmtMonth(r.announced)})`).join(" → ")}
          </span>
        </div>
      ))}
    </div>
  );
}
