"use client";

import { ArrowRight, CheckCircle2, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DiligencePoint } from "@/lib/leadline/match-types";
import type { Deal } from "@/lib/leadline/types";
import { fmtEur, fmtMonth } from "@/lib/leadline/format";
import { SourceLinks } from "./shared";

export function Section({
  title,
  icon: Icon,
  children,
  className,
}: {
  title: string;
  icon?: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-xl border border-border bg-card p-5", className)}>
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
        {Icon && <Icon className="h-4 w-4 text-primary" />} {title}
      </h2>
      {children}
    </section>
  );
}

/** Two columns: reasons to invest, and risks to check. */
export function ProsCons({ strengths, risks }: { strengths: DiligencePoint[]; risks: DiligencePoint[] }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <section className="rounded-xl border border-emerald-500/25 bg-card p-5">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-emerald-700 dark:text-emerald-400">
          <CheckCircle2 className="h-4 w-4" /> Reasons to invest
        </h2>
        {strengths.length === 0 && <p className="text-sm text-muted-foreground">Nothing stands out in Cala yet.</p>}
        <ul className="space-y-2.5">
          {strengths.map((s) => (
            <li key={s.text} className="text-sm">
              {s.text} {s.sources.length > 0 && <SourceLinks sources={s.sources} />}
            </li>
          ))}
        </ul>
      </section>
      <section className="rounded-xl border border-amber-500/25 bg-card p-5">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-amber-700 dark:text-amber-400">
          <AlertTriangle className="h-4 w-4" /> Risks to check
        </h2>
        {risks.length === 0 && <p className="text-sm text-muted-foreground">No red flags in Cala.</p>}
        <ul className="space-y-2.5">
          {risks.map((r) => (
            <li key={r.text} className="text-sm">
              {r.text} {r.sources.length > 0 && <SourceLinks sources={r.sources} />}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

/** A company's funding path: one step per round, with lead and source. */
export function RoundPath({ rounds, highlight }: { rounds: Deal[]; highlight?: (d: Deal) => boolean }) {
  return (
    <div className="flex flex-wrap items-stretch gap-2">
      {rounds.map((r, i) => (
        <div key={r.id} className="flex items-center gap-2">
          {i > 0 && <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
          <div
            className={cn(
              "min-w-[160px] rounded-lg border px-3 py-2 text-xs",
              highlight?.(r) ? "border-primary/40 bg-primary/5" : "border-border bg-background",
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold">{r.round}</span>
              <span className="text-muted-foreground">
                {fmtEur(r.amountEurM)} · {fmtMonth(r.announced)}
              </span>
            </div>
            <div className="mt-1">{r.leadInvestors.length ? `Led by ${r.leadInvestors.join(", ")}` : "Lead not disclosed"}</div>
            {r.otherInvestors.length > 0 && (
              <div className="text-muted-foreground">With {r.otherInvestors.join(", ")}</div>
            )}
            <div className="mt-1">
              <SourceLinks sources={r.sources} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function Stat({ value, label }: { value: React.ReactNode; label: string }) {
  return (
    <div className="rounded-lg border border-border bg-background px-4 py-3">
      <div className="text-xl font-bold tabular-nums">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}
