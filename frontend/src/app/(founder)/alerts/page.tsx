"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Bell, Landmark, Loader2, Mail, RefreshCw } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/button";
import {
  ConflictBadge,
  ErrorBox,
  PoweredByCala,
  SourceLinks,
  SynergyBadge,
  postJson,
  useCalaMode,
  useRequiredProfile,
} from "@/components/leadline/shared";
import { cn } from "@/lib/utils";
import { useLeadline } from "@/lib/leadline/store";
import { daysAgoText, dealPhrase, fmtDate, fmtEur } from "@/lib/leadline/format";
import { sectorLabel, stageLabel, type Signal, type SignalsResponse } from "@/lib/leadline/types";

function SignalBody({ s }: { s: Signal }) {
  const name = (
    <Link href={`/investors/${s.investorSlug}`} className="font-semibold hover:underline">
      {s.investor}
    </Link>
  );
  if (s.kind === "fund" && s.fund) {
    return (
      <>
        <div className="text-sm">
          {name} just closed a new fund: {s.fund.fundName}
          {s.fund.sizeEurM ? ` (${fmtEur(s.fund.sizeEurM)})` : ""}, {daysAgoText(s.daysAgo)}.
        </div>
        <div className="text-xs text-muted-foreground">
          A fresh fund means they need to deploy capital. Best time to get on their radar.
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <ConflictBadge conflict={s.conflict} />
          <SynergyBadge count={s.synergyCount} />
          <span>Closed {fmtDate(s.fund.closed)}</span>
          <SourceLinks sources={s.fund.sources} />
        </div>
      </>
    );
  }
  if (!s.deal) return null;
  return (
    <>
      <div className="text-sm">
        {name} just led {dealPhrase(s.deal)}, {daysAgoText(s.daysAgo)}.
      </div>
      {s.deal.companyDescription && (
        <div className="text-xs text-muted-foreground">
          {s.deal.company}: {s.deal.companyDescription}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <ConflictBadge conflict={s.conflict} />
        <SynergyBadge count={s.synergyCount} />
        <span>Announced {fmtDate(s.deal.announced)}</span>
        <SourceLinks sources={s.deal.sources} />
      </div>
    </>
  );
}

export default function SignalsPage() {
  const profile = useRequiredProfile();
  const mode = useCalaMode();
  const signals = useLeadline((s) => s.signals);
  const checkedAt = useLeadline((s) => s.signalsCheckedAt);
  const seen = useLeadline((s) => s.seenSignalIds);
  const setSignals = useLeadline((s) => s.setSignals);
  const markSeen = useLeadline((s) => s.markSignalsSeen);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Highlight what was new when the page opened, then mark it as seen.
  const newOnOpen = useRef<Set<string> | null>(null);
  if (newOnOpen.current === null && signals.length) {
    newOnOpen.current = new Set(signals.filter((s) => !seen.includes(s.id)).map((s) => s.id));
  }
  useEffect(() => {
    if (signals.length) markSeen();
  }, [signals, markSeen]);

  const checkNow = async () => {
    if (!profile) return;
    setChecking(true);
    setError(null);
    try {
      const r = await postJson<SignalsResponse>("/api/signals", profile);
      setSignals(r.signals, r.checkedAt);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setChecking(false);
    }
  };

  return (
    <AppLayout>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-2xl font-bold tracking-tight">Signals</h1>
          {profile && (
            <p className="mt-1 text-sm text-muted-foreground">
              Leadline watches Cala for new {stageLabel(profile.stage)} rounds in {sectorLabel(profile.sector)} and for
              funds that just closed, so you reach investors while they&apos;re actively deploying. You don&apos;t
              have to keep checking.
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <PoweredByCala mode={mode} />
          <Button variant="outline" size="sm" onClick={checkNow} disabled={checking}>
            {checking ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Check now
          </Button>
        </div>
      </div>

      {checkedAt && (
        <p className="mb-3 text-xs text-muted-foreground">
          Last checked {new Date(checkedAt).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}.
          Checks again every 5 minutes while Leadline is open.
        </p>
      )}
      {error && <ErrorBox message={error} />}

      {!checkedAt && !error && (
        <div className="flex items-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Checking Cala for new rounds and funds…
        </div>
      )}

      {checkedAt && signals.length === 0 && (
        <div className="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">
          Nothing new in your space in the last 30 days. We&apos;ll tell you when something appears.
        </div>
      )}

      <div className="space-y-3">
        {signals.map((s) => {
          const isNew = newOnOpen.current?.has(s.id);
          const Icon = s.kind === "fund" ? Landmark : Bell;
          const draftHref =
            s.kind === "lead" && s.deal
              ? `/outreach/${s.investorSlug}?deal=${encodeURIComponent(s.deal.id)}`
              : `/outreach/${s.investorSlug}`;
          return (
            <div
              key={s.id}
              className={cn("rounded-xl border bg-card p-5", isNew ? "border-primary/40 ring-1 ring-primary/20" : "border-border")}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 flex-1 items-start gap-3">
                  <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", isNew ? "text-primary" : "text-muted-foreground")} />
                  <div className="space-y-1.5">
                    {isNew && (
                      <span className="rounded bg-primary px-1.5 py-0.5 text-[10px] font-semibold uppercase text-primary-foreground">
                        new
                      </span>
                    )}
                    <SignalBody s={s} />
                  </div>
                </div>
                <Link href={draftHref} className="shrink-0">
                  <Button size="sm">
                    <Mail className="h-3.5 w-3.5" /> Draft intro
                  </Button>
                </Link>
              </div>
            </div>
          );
        })}
      </div>
    </AppLayout>
  );
}
