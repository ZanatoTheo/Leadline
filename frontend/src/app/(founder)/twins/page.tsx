"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, GitBranch, Loader2 } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/button";
import { ErrorBox, PoweredByCala, SourceLinks, postJson, useRequiredProfile } from "@/components/leadline/shared";
import { cn } from "@/lib/utils";
import { fmtEur, fmtMonth } from "@/lib/leadline/format";
import { stageLabel, slugify, type FounderProfile, type TwinsResponse } from "@/lib/leadline/types";
import { stageKey } from "@/lib/leadline/twins";

function Benchmark({ data, profile }: { data: TwinsResponse; profile: FounderProfile }) {
  const { sameStage, monthsToNext, reachedNext } = data;
  const stage = stageLabel(profile.stage);
  let verdict: React.ReactNode = null;
  if (sameStage.minEurM != null && sameStage.maxEurM != null) {
    const r = profile.raiseEurM;
    verdict =
      r < sameStage.minEurM ? (
        <>Your {fmtEur(r)} is <b>below</b> what your twins raised. You may be able to ask for more.</>
      ) : r > sameStage.maxEurM ? (
        <>Your {fmtEur(r)} is <b>above</b> every twin. Expect investors to push back on size.</>
      ) : (
        <>Your {fmtEur(r)} is <b>in line</b> with your twins.</>
      );
  }
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <div className="rounded-lg border border-border bg-card px-4 py-3">
        <div className="text-xl font-bold tabular-nums">
          {sameStage.minEurM != null ? `${fmtEur(sameStage.minEurM)}–${fmtEur(sameStage.maxEurM)}` : "–"}
        </div>
        <div className="text-xs text-muted-foreground">
          twins&apos; {stage.toLowerCase()} rounds ({sameStage.count}), median {fmtEur(sameStage.medianEurM)}
        </div>
      </div>
      <div className="rounded-lg border border-border bg-card px-4 py-3">
        <div className="text-xl font-bold tabular-nums">{monthsToNext != null ? `${monthsToNext} months` : "–"}</div>
        <div className="text-xs text-muted-foreground">
          from {stage.toLowerCase()} to next round ({reachedNext} twin{reachedNext === 1 ? "" : "s"} got there)
        </div>
      </div>
      <div className="flex items-center rounded-lg border border-primary/20 bg-primary/5 px-4 py-3 text-sm">
        <p>{verdict}</p>
      </div>
    </div>
  );
}

export default function TwinsPage() {
  const profile = useRequiredProfile();
  const [data, setData] = useState<TwinsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!profile) return;
    const ctrl = new AbortController();
    postJson<TwinsResponse>("/api/twins", profile, ctrl.signal)
      .then(setData)
      .catch((e) => e.name !== "AbortError" && setError(e.message));
    return () => ctrl.abort();
  }, [profile]);

  return (
    <AppLayout>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-2xl font-bold tracking-tight">Your funding twins</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Startups that were where you are now: same problem, same kind of customer. Here&apos;s who backed each
            round on their path, so you can follow it.
          </p>
        </div>
        <PoweredByCala mode={data?.mode} />
      </div>

      {error && <ErrorBox message={error} />}
      {!data && !error && (
        <div className="flex items-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Finding startups like yours in Cala…
        </div>
      )}

      {data && profile && data.twins.length === 0 && (
        <div className="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">
          Cala didn&apos;t return close twins for your description. Try describing what you do and who you sell to
          in more specific words on <Link href="/onboarding" className="text-primary underline">My startup</Link>.
        </div>
      )}

      {data && profile && data.twins.length > 0 && (
        <div className="space-y-6">
          <Benchmark data={data} profile={profile} />

          <div className="space-y-3">
            {data.twins.map((t) => {
              const isCompetitor = profile.competitors.some((c) => c.toLowerCase() === t.company.toLowerCase());
              return (
                <div key={t.company} className="rounded-xl border border-border bg-card p-5">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div>
                      <span className="font-semibold">{t.company}</span>
                      {isCompetitor && (
                        <span className="ml-2 rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-rose-600 dark:text-rose-400">
                          your competitor
                        </span>
                      )}
                      <div className="text-xs text-muted-foreground">{t.description}</div>
                    </div>
                  </div>

                  {/* The path: one step per round */}
                  <div className="mt-4 flex flex-wrap items-stretch gap-2">
                    {t.rounds.map((r, i) => {
                      const atMyStage = stageKey(r.round) === profile.stage;
                      return (
                        <div key={r.id} className="flex items-center gap-2">
                          {i > 0 && <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
                          <div
                            className={cn(
                              "min-w-[170px] rounded-lg border px-3 py-2 text-xs",
                              atMyStage ? "border-primary/40 bg-primary/5" : "border-border bg-background",
                            )}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-semibold">{r.round}</span>
                              <span className="text-muted-foreground">{fmtEur(r.amountEurM)} · {fmtMonth(r.announced)}</span>
                            </div>
                            <div className="mt-1">
                              Led by{" "}
                              {r.leadInvestors.map((l, j) => (
                                <span key={l}>
                                  {j > 0 && ", "}
                                  <Link href={`/investors/${slugify(l)}`} className="font-medium text-primary hover:underline">
                                    {l}
                                  </Link>
                                </span>
                              ))}
                            </div>
                            <div className="mt-1">
                              <SourceLinks sources={r.sources} />
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="rounded-xl border border-border bg-card p-5">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <GitBranch className="h-4 w-4 text-primary" /> Who led rounds on your twins&apos; paths
            </h2>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {data.pathLeads.map((l) => (
                <Link
                  key={l.slug}
                  href={`/investors/${l.slug}`}
                  className="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-sm hover:bg-secondary/40"
                >
                  <span className="font-medium">{l.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {l.rounds.map((r) => `${r.twin} ${r.round.toLowerCase()}`).join(", ")}
                  </span>
                </Link>
              ))}
            </div>
          </div>

          <div className="flex justify-end">
            <Link href="/investors">
              <Button>
                See who to pitch for your {stageLabel(profile.stage).toLowerCase()} now <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
