"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Bell, ChevronRight, Loader2 } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import {
  ConflictBadge,
  DealClaim,
  ErrorBox,
  PendingBox,
  PoweredByCala,
  ScoreBar,
  SynergyBadge,
  TimingBadge,
  TwinBadge,
  useRequiredProfile,
  useShortlist,
} from "@/components/leadline/shared";
import { cn } from "@/lib/utils";
import { isActive } from "@/lib/leadline/rank";
import { useUnreadSignals } from "@/lib/leadline/store";
import { daysAgoText, dealPhrase, fmtEur } from "@/lib/leadline/format";
import type { RankedInvestor, Signal } from "@/lib/leadline/types";
import { regionLabel, sectorLabel, stageLabel } from "@/lib/leadline/types";

const SORTS: { key: string; label: string; value: (i: RankedInvestor) => number }[] = [
  { key: "lead", label: "Lead index", value: (i) => i.score },
  { key: "now", label: "Deploying now", value: (i) => (i.timingStatus === "deploying" ? 1000 : i.timingStatus === "slowing" ? -1000 : 0) + i.score },
  { key: "you", label: "Portfolio fit", value: (i) => (i.synergyCount ?? 0) * 1000 + i.score },
  { key: "twins", label: "Backed your twins", value: (i) => (i.twinsLedCount ?? 0) * 1000 + i.score },
];

function signalText(s: Signal): string {
  if (s.kind === "fund" && s.fund) return `${s.investor} just closed ${s.fund.fundName}, ${daysAgoText(s.daysAgo)}.`;
  if (s.deal) return `${s.investor} just led ${dealPhrase(s.deal)}, ${daysAgoText(s.daysAgo)}.`;
  return `${s.investor}: new activity.`;
}

const ACTIVE_OPTIONS = [
  { label: "Any time", months: 0 },
  { label: "Led in last 12 months", months: 12 },
  { label: "Led in last 6 months", months: 6 },
];

function Stat({ value, label }: { value: React.ReactNode; label: string }) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <div className="text-xl font-bold tabular-nums">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function Toggle({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
        active ? "border-primary/30 bg-primary/10 text-primary" : "border-border text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

export default function ShortlistPage() {
  const profile = useRequiredProfile();
  const unread = useUnreadSignals();
  const { state: list, retry } = useShortlist(profile);
  const data = list.kind === "ready" ? list.data : null;
  const error = list.kind === "error" ? list.message : null;
  // Every investor the agent ranked is shown at first; the filters only narrow the list.
  const [activeMonths, setActiveMonths] = useState(0);
  const [hideConflicts, setHideConflicts] = useState(false);
  const [showFollowers, setShowFollowers] = useState(true);
  const clearFilters = () => {
    setActiveMonths(0);
    setHideConflicts(false);
    setShowFollowers(true);
  };
  const [sort, setSort] = useState("lead");

  const visible = useMemo(() => {
    if (!data) return [];
    return data.investors
      .filter((i) => showFollowers || i.ledCount > 0)
      .filter((i) => !activeMonths || isActive(i, activeMonths))
      .filter((i) => !hideConflicts || i.conflict.level !== "direct")
      .sort((a, b) => {
        const by = SORTS.find((x) => x.key === sort)!.value;
        return by(b) - by(a);
      });
  }, [data, activeMonths, hideConflicts, showFollowers, sort]);

  const latest = unread[0];

  return (
    <AppLayout>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Who is likely to lead your round</h1>
          {profile && (
            <p className="mt-1 text-sm text-muted-foreground">
              Ranked by how often and how recently they led {stageLabel(profile.stage)} rounds in{" "}
              {sectorLabel(profile.sector)} across {regionLabel(profile.region)}. You&apos;re raising{" "}
              {fmtEur(profile.raiseEurM)}.
            </p>
          )}
        </div>
        <PoweredByCala mode={data?.mode} />
      </div>

      {latest && (
        <Link
          href="/alerts"
          className="mb-5 flex items-center gap-3 rounded-lg border border-primary/25 bg-primary/5 px-4 py-3 text-sm hover:bg-primary/10"
        >
          <Bell className="h-4 w-4 shrink-0 text-primary" />
          <span className="flex-1">
            <span className="font-semibold">New signal:</span> {signalText(latest)}
            {unread.length > 1 && ` +${unread.length - 1} more.`}
          </span>
          <ChevronRight className="h-4 w-4 text-primary" />
        </Link>
      )}

      {error && <ErrorBox message={error} />}

      {list.kind === "pending" && <PendingBox pending={list.pending} gaveUp={list.gaveUp} onRetry={retry} />}

      {list.kind === "loading" && (
        <div className="flex items-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading your shortlist…
        </div>
      )}

      {data && (
        <>
          <div className="mb-5 grid grid-cols-3 gap-3">
            <Stat value={data.roundsAnalysed} label="comparable rounds from Cala (18 months)" />
            <Stat value={data.investors.filter((i) => i.ledCount > 0).length} label="investors who led at least one" />
            <Stat value={data.sourcesCited} label="source documents cited" />
          </div>

          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="mr-1 text-xs font-medium text-muted-foreground">Still active:</span>
            {ACTIVE_OPTIONS.map((o) => (
              <Toggle key={o.months} active={activeMonths === o.months} onClick={() => setActiveMonths(o.months)}>
                {o.label}
              </Toggle>
            ))}
            <span className="mx-2 h-4 w-px bg-border" />
            <Toggle active={hideConflicts} onClick={() => setHideConflicts((v) => !v)}>
              Hide investors backing a competitor
            </Toggle>
            <Toggle active={showFollowers} onClick={() => setShowFollowers((v) => !v)}>
              Include follow-only investors
            </Toggle>
          </div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="mr-1 text-xs font-medium text-muted-foreground">Sort by:</span>
            {SORTS.map((o) => (
              <Toggle key={o.key} active={sort === o.key} onClick={() => setSort(o.key)}>
                {o.label}
              </Toggle>
            ))}
          </div>

          <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
            {visible.length === 0 && (
              <div className="p-8 text-center text-sm text-muted-foreground">
                {data.investors.length === 0 ? (
                  "No investors ranked for your round yet. Save your profile again on My startup to re-rank."
                ) : (
                  <>
                    Your filters hide all {data.investors.length} ranked investor{data.investors.length === 1 ? "" : "s"}.{" "}
                    <button type="button" onClick={clearFilters} className="font-medium text-primary hover:underline">
                      Clear filters
                    </button>
                  </>
                )}
              </div>
            )}
            {visible.map((inv, idx) => (
              <div key={inv.slug} className="relative flex items-start gap-4 px-5 py-4 transition-colors hover:bg-secondary/40">
                <Link href={`/investors/${inv.slug}`} className="absolute inset-0" aria-label={`Open ${inv.name}`} />
                <span className="w-5 pt-0.5 text-sm font-semibold tabular-nums text-muted-foreground">{idx + 1}</span>
                <div className="min-w-0 flex-1 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{inv.name}</span>
                    <ConflictBadge conflict={inv.conflict} />
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <TwinBadge count={inv.twinsLedCount} />
                    <TimingBadge status={inv.timingStatus} title={inv.timingHeadline} />
                    <SynergyBadge count={inv.synergyCount} />
                  </div>
                  <div className="text-xs text-muted-foreground">{inv.explanation}</div>
                  {inv.ledDeals[0] ? (
                    <DealClaim deal={inv.ledDeals[0]} />
                  ) : (
                    inv.joinedDeals[0] && <DealClaim deal={inv.joinedDeals[0]} verb="Joined" />
                  )}
                </div>
                <div className="flex flex-col items-end gap-1 pt-0.5">
                  <ScoreBar score={inv.score} />
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground">lead index</span>
                </div>
                <ChevronRight className="mt-1 h-4 w-4 text-muted-foreground" />
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Lead index: each round an investor led counts fully and each round they only joined counts a quarter,
            both fading with age (about a 6-month half-life). Badges come from each investor&apos;s own rounds and
            funds in Cala. Open an investor for the full brief behind every badge.
          </p>
        </>
      )}
    </AppLayout>
  );
}
