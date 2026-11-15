"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, BarChart3, GitBranch, Loader2, Swords, Target, UserRound } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { ErrorBox, PoweredByCala, postJson } from "@/components/leadline/shared";
import { FitPoints, FitScore, PortfolioTwinPaths } from "@/components/leadline/fit";
import { IntroActions } from "@/components/leadline/intro-actions";
import { ProsCons, RoundPath, Section, Stat } from "@/components/leadline/diligence";
import { useSession } from "@/components/leadline/session";
import type { StartupDiligence } from "@/lib/leadline/match-types";
import { daysAgoText, fmtEur, fmtMonth } from "@/lib/leadline/format";
import { ageDays } from "@/lib/leadline/rank";
import { stageKey } from "@/lib/leadline/twins";
import { regionLabel, sectorLabel, stageLabel } from "@/lib/leadline/types";

export default function StartupDiligencePage() {
  const { id } = useParams<{ id: string }>();
  const { investorName } = useSession();
  const [data, setData] = useState<StartupDiligence | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await postJson<StartupDiligence>("/api/startup", { founderId: id }));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const p = data?.founder.profile;

  return (
    <AppLayout>
      <Link href="/investor" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to deal flow
      </Link>

      {error && <ErrorBox message={error} />}
      {!data && !error && (
        <div className="flex items-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Running due diligence in Cala…
        </div>
      )}

      {data && p && (
        <div className="space-y-5">
          {/* Header + decision */}
          <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
            <div className="flex items-start gap-4">
              <FitScore score={data.fit.score} />
              <div>
                <h1 className="text-2xl font-bold tracking-tight">{p.startupName}</h1>
                <p className="mt-1">{p.oneLiner}</p>
                <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                  {[
                    `${stageLabel(p.stage)} · raising ${fmtEur(p.raiseEurM)}`,
                    sectorLabel(p.sector),
                    p.location || regionLabel(p.region),
                    p.customers && `Sells to ${p.customers}`,
                  ]
                    .filter(Boolean)
                    .map((t) => (
                      <span key={t as string} className="rounded-md border border-border bg-secondary px-2 py-0.5">
                        {t}
                      </span>
                    ))}
                </div>
                <p className="mt-2 text-xs text-muted-foreground">Fit with {investorName}: {data.fit.headline}</p>
              </div>
            </div>
            <div className="space-y-3 rounded-xl border border-primary/25 bg-card p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold">Your decision</span>
                <PoweredByCala mode={data.mode} />
              </div>
              {data.intro?.direction === "founder-to-investor" && data.intro.note && (
                <div className="rounded-lg bg-primary/5 p-2.5 text-xs">
                  <div className="mb-1 font-semibold text-primary">
                    {data.founder.founderName || "Founder"} wrote, {daysAgoText(ageDays(data.intro.createdAt))}:
                  </div>
                  <p className="line-clamp-6 whitespace-pre-line">{data.intro.note}</p>
                </div>
              )}
              <IntroActions founder={data.founder} intro={data.intro} email={data.founder.email} onChange={load} />
            </div>
          </div>

          <ProsCons strengths={data.strengths} risks={data.risks} />

          <Section title={`Fit with ${investorName}`} icon={Target}>
            <div className="space-y-3">
              <PortfolioTwinPaths fit={data.fit} />
              <FitPoints fit={data.fit} />
            </div>
          </Section>

          <Section title={`The market: ${stageLabel(p.stage)} rounds in ${sectorLabel(p.sector)}, ${regionLabel(p.region)}`} icon={BarChart3}>
            <div className="grid gap-3 sm:grid-cols-4">
              <Stat value={data.market.rounds} label="comparable rounds, last 18 months" />
              <Stat value={fmtEur(data.market.totalEurM)} label="raised in those rounds" />
              <Stat value={fmtEur(data.market.medianEurM)} label="median round size" />
              <Stat value={data.market.twinsFundedLast24m} label="close look-alikes funded, last 2 years" />
            </div>
          </Section>

          <Section title="How similar startups did after this stage" icon={GitBranch}>
            {data.twins.twins.length === 0 ? (
              <p className="text-sm text-muted-foreground">Cala found no close look-alikes.</p>
            ) : (
              <div className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  {data.twins.reachedNext} of {data.twins.twins.length} raised their next round
                  {data.twins.monthsToNext ? ` after about ${data.twins.monthsToNext} months` : ""}. Highlighted: rounds at
                  the stage {p.startupName} is raising now.
                </p>
                {data.twins.twins.map((t) => (
                  <div key={t.company}>
                    <div className="mb-1.5 text-sm">
                      <span className="font-medium">{t.company}</span>
                      {p.competitors.some((c) => c.toLowerCase() === t.company.toLowerCase()) && (
                        <span className="ml-2 rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-rose-600 dark:text-rose-400">
                          named competitor
                        </span>
                      )}
                      <span className="text-xs text-muted-foreground"> · {t.description}</span>
                    </div>
                    <RoundPath rounds={t.rounds} highlight={(r) => stageKey(r.round) === p.stage} />
                  </div>
                ))}
              </div>
            )}
          </Section>

          <div className="grid gap-4 md:grid-cols-2">
            <Section title="Who else may want to lead this round" icon={Swords}>
              {data.otherLeads.length === 0 ? (
                <p className="text-sm text-muted-foreground">No other regular leads found for rounds like this.</p>
              ) : (
                <ul className="space-y-1.5 text-sm">
                  {data.otherLeads.map((o) => (
                    <li key={o.name} className="flex items-center justify-between gap-3">
                      <span className="font-medium">{o.name}</span>
                      <span className="text-xs text-muted-foreground">
                        led {o.ledCount} similar{o.lastLed ? `, last ${fmtMonth(o.lastLed)}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-2 text-xs text-muted-foreground">Move first if you want the lead.</p>
            </Section>

            <Section title="Founder and team" icon={UserRound}>
              <ul className="space-y-1 text-sm">
                <li>
                  <span className="text-muted-foreground">Founder: </span>
                  {data.founder.founderName || "Not shared"}
                </li>
                <li>
                  <span className="text-muted-foreground">Based in: </span>
                  {p.location || regionLabel(p.region)}
                </li>
                <li>
                  <span className="text-muted-foreground">Named competitors: </span>
                  {p.competitors.join(", ") || "None given"}
                </li>
                <li>
                  <span className="text-muted-foreground">Contact: </span>
                  {data.founder.email ?? "Shared once you both say yes"}
                </li>
              </ul>
              {data.competitorRounds.length > 0 && (
                <div className="mt-3 space-y-1 text-xs text-muted-foreground">
                  {data.competitorRounds.slice(0, 3).map((r) => (
                    <div key={r.id}>
                      {r.company}: {fmtEur(r.amountEurM)} {r.round}, {fmtMonth(r.announced)}, led by {r.leadInvestors.join(", ")}
                    </div>
                  ))}
                </div>
              )}
            </Section>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
