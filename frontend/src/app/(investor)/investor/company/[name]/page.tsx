"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, GitBranch, History, Loader2, Users } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { ErrorBox, PoweredByCala, postJson } from "@/components/leadline/shared";
import { ProsCons, RoundPath, Section, Stat } from "@/components/leadline/diligence";
import { useSession } from "@/components/leadline/session";
import type { CompanyDiligence } from "@/lib/leadline/match-types";
import { fmtEur } from "@/lib/leadline/format";

export default function CompanyDiligencePage() {
  const params = useParams<{ name: string }>();
  const company = decodeURIComponent(params.name);
  const { investorName } = useSession();
  const [data, setData] = useState<CompanyDiligence | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    postJson<CompanyDiligence>("/api/company", { company })
      .then(setData)
      .catch((e) => setError(e.message));
  }, [company]);

  const last = data?.rounds.at(-1);
  const total = data?.rounds.reduce((s, r) => s + (r.amountEurM ?? 0), 0) ?? 0;

  return (
    <AppLayout>
      <Link href="/investor" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to deal flow
      </Link>

      {error && <ErrorBox message={error} />}
      {!data && !error && (
        <div className="flex items-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Pulling {company}&apos;s history from Cala…
        </div>
      )}

      {data && last && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight">{data.company}</h1>
                {data.raisingSoon && (
                  <span className="rounded-md border border-sky-500/25 bg-sky-500/10 px-2 py-0.5 text-xs font-medium text-sky-700 dark:text-sky-400">
                    Likely raising soon
                  </span>
                )}
                {data.youBacked && (
                  <span className="rounded-md border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-400">
                    In your portfolio
                  </span>
                )}
              </div>
              <p className="mt-1">{data.description}</p>
              {data.industry && <p className="text-xs text-muted-foreground">{data.industry} · found in Cala, not on Leadline yet</p>}
            </div>
            <PoweredByCala mode={data.mode} />
          </div>

          <div className="grid gap-3 sm:grid-cols-4">
            <Stat value={last.round} label="latest round" />
            <Stat value={fmtEur(last.amountEurM)} label="raised in latest round" />
            <Stat value={fmtEur(total)} label="raised in total" />
            <Stat value={data.monthsSinceLast != null ? `${data.monthsSinceLast} mo` : "–"} label="since last round" />
          </div>

          <ProsCons strengths={data.strengths} risks={data.risks} />

          <Section title="Funding history" icon={History}>
            <RoundPath rounds={data.rounds} />
          </Section>

          <Section title="Backers" icon={Users}>
            <ul className="grid gap-1.5 text-sm sm:grid-cols-2">
              {data.backers.map((b) => (
                <li key={b.name} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2">
                  <span className={b.name === investorName ? "font-semibold text-primary" : "font-medium"}>
                    {b.name}
                    {b.name === investorName && " (you)"}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {[b.led && `led ${b.led}`, b.joined && `joined ${b.joined}`].filter(Boolean).join(", ")}
                  </span>
                </li>
              ))}
            </ul>
          </Section>

          <Section title="Similar companies and how they did" icon={GitBranch}>
            {data.similar.length === 0 ? (
              <p className="text-sm text-muted-foreground">Cala found no close look-alikes.</p>
            ) : (
              <div className="space-y-4">
                {data.similar.map((s) => (
                  <div key={s.company}>
                    <div className="mb-1.5 text-sm">
                      <span className="font-medium">{s.company}</span>
                      {s.inYourPortfolio && (
                        <span className="ml-2 rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-emerald-700 dark:text-emerald-400">
                          your portfolio
                        </span>
                      )}
                      <span className="text-xs text-muted-foreground"> · {s.description}</span>
                    </div>
                    <RoundPath rounds={s.rounds} />
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>
      )}
    </AppLayout>
  );
}
