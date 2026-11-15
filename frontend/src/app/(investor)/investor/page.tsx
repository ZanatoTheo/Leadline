"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/components/leadline/session";
import { Check, ChevronRight, Inbox, Loader2, Radar, Sparkles } from "lucide-react";
import Link from "next/link";
import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/button";
import { ErrorBox, PoweredByCala, postJson } from "@/components/leadline/shared";
import { IntroActions } from "@/components/leadline/intro-actions";
import { FitPoints, FitScore, PortfolioTwinPaths } from "@/components/leadline/fit";
import { cn } from "@/lib/utils";
import { type DiscoverResponse, type FitReport, type Intro, type PublicFounder } from "@/lib/leadline/match-types";
import { daysAgoText, fmtEur, fmtMonth } from "@/lib/leadline/format";
import { sectorLabel, stageLabel } from "@/lib/leadline/types";
import { ageDays } from "@/lib/leadline/rank";

type InvestorIntro = Intro & { founder: (PublicFounder & { email?: string }) | null };
type Tab = "requests" | "discover" | "matches";

/** The logged-in investor's fund; sends them to setup if they haven't picked one. */
function useInvestorGuard(): string | null {
  const { investorName } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (!investorName) router.replace("/investor/setup");
  }, [investorName, router]);
  return investorName;
}

function FounderCard({
  founder,
  fit,
  intro,
  email,
  onChange,
}: {
  founder: PublicFounder;
  fit: FitReport;
  intro?: Intro;
  email?: string;
  onChange: () => Promise<void>;
}) {
  const p = founder.profile;
  const incoming = intro?.direction === "founder-to-investor";
  const href = `/investor/startup/${founder.id}`;
  return (
    <div className="rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary/30">
      <div className="flex items-start gap-4">
        <FitScore score={fit.score} />
        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <Link href={href} className="text-lg font-semibold hover:text-primary hover:underline">
                  {p.startupName}
                </Link>
                <span className="text-xs text-muted-foreground">
                  {stageLabel(p.stage)} · raising {fmtEur(p.raiseEurM)} · {sectorLabel(p.sector)}
                  {p.location ? ` · ${p.location}` : ""}
                </span>
              </div>
              <p className="text-sm">{p.oneLiner}</p>
              {p.customers && <p className="text-xs text-muted-foreground">Sells to {p.customers}</p>}
            </div>
            <Link href={href}>
              <Button variant="outline" size="sm">
                Full due diligence <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </div>

          {incoming && intro?.note && (
            <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm">
              <div className="mb-1 text-xs font-semibold text-primary">
                {founder.founderName || "The founder"} wrote, {daysAgoText(ageDays(intro.createdAt))}:
              </div>
              <p className="whitespace-pre-line">{intro.note}</p>
            </div>
          )}

          <PortfolioTwinPaths fit={fit} />
          <FitPoints fit={fit} />
          <IntroActions founder={founder} intro={intro} email={email} onChange={onChange} />
        </div>
      </div>
    </div>
  );
}

export default function InvestorDealFlowPage() {
  const investor = useInvestorGuard();
  const [tab, setTab] = useState<Tab>("requests");
  const [discover, setDiscover] = useState<DiscoverResponse | null>(null);
  const [intros, setIntros] = useState<InvestorIntro[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!investor) return;
    try {
      const [d, i] = await Promise.all([
        postJson<DiscoverResponse>("/api/discover", {}),
        fetch("/api/intros").then((r) => r.json()),
      ]);
      setDiscover(d);
      setIntros(i.intros ?? []);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [investor]);

  useEffect(() => {
    load();
  }, [load]);

  // While the agent builds this fund's first ranking, check again every 20 seconds.
  const building = discover?.ranking === "building";
  useEffect(() => {
    if (!building) return;
    const t = setInterval(load, 20_000);
    return () => clearInterval(t);
  }, [building, load]);

  const emailFor = (introId?: string) => intros.find((i) => i.id === introId)?.founder?.email;
  const founders = discover?.founders ?? [];
  const requests = founders.filter((f) => f.intro?.direction === "founder-to-investor" && f.intro.status !== "accepted");
  const matches = founders.filter((f) => f.intro?.status === "accepted");
  const discoverable = founders.filter((f) => !f.intro || (f.intro.direction === "investor-to-founder" && f.intro.status !== "accepted"));
  const pending = requests.filter((f) => f.intro?.status === "pending").length;

  const tabs: { key: Tab; label: string; icon: React.ComponentType<{ className?: string }>; count: number }[] = [
    { key: "requests", label: "Intro requests", icon: Inbox, count: pending },
    { key: "discover", label: "Discover", icon: Radar, count: discoverable.length + (discover?.nextTwins.length ?? 0) },
    { key: "matches", label: "Matches", icon: Check, count: matches.length },
  ];

  return (
    <AppLayout>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-2xl font-bold tracking-tight">Deal flow{investor ? ` for ${investor}` : ""}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Founders who fit what you actually lead, each with a fit score you can check line by line against
            Cala. Contacts are shared only when both sides say yes.
          </p>
        </div>
        <PoweredByCala mode={discover?.mode} />
      </div>

      <div className="mb-5 flex gap-1 border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm transition-colors",
              tab === t.key ? "border-primary font-semibold text-primary" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            <t.icon className="h-4 w-4" /> {t.label}
            {t.count > 0 && (
              <span className="rounded-md bg-primary/10 px-1.5 text-[11px] font-semibold tabular-nums text-primary">{t.count}</span>
            )}
          </button>
        ))}
      </div>

      {error && <ErrorBox message={error} />}
      {!discover && !error && (
        <div className="flex items-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Matching founders against your rounds in Cala…
        </div>
      )}

      {discover && tab === "requests" && (
        <div className="space-y-4">
          {requests.length === 0 && (
            <div className="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">
              No intro requests yet. Founders send one when Leadline shows them you&apos;re a fit. Meanwhile, check
              Discover.
            </div>
          )}
          {requests.map((f) => (
            <FounderCard key={f.founder.id} founder={f.founder} fit={f.fit} intro={f.intro} onChange={load} />
          ))}
        </div>
      )}

      {discover && tab === "matches" && (
        <div className="space-y-4">
          {matches.length === 0 && (
            <div className="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">
              No matches yet.
            </div>
          )}
          {matches.map((f) => (
            <FounderCard key={f.founder.id} founder={f.founder} fit={f.fit} intro={f.intro} email={emailFor(f.intro?.id)} onChange={load} />
          ))}
        </div>
      )}

      {discover && tab === "discover" && (
        <div className="space-y-6">
          <section className="space-y-3">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <Sparkles className="h-4 w-4 text-primary" /> Founders on Leadline who fit you ({discoverable.length})
            </h2>
            {discoverable.length === 0 &&
              (building ? (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" /> Your agent is reading {investor}&apos;s rounds and
                  ranking founders. This takes a few minutes; this list updates by itself.
                </p>
              ) : discover?.ranking === "failed" ? (
                <p className="text-sm text-muted-foreground">
                  Your agent couldn&apos;t rank founders for {investor} this time. Pick the fund again to retry.
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">No opted-in founders match your thesis right now.</p>
              ))}
            {discoverable.map((f) => (
              <FounderCard key={f.founder.id} founder={f.founder} fit={f.fit} intro={f.intro} onChange={load} />
            ))}
          </section>

          <section className="space-y-3">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <Radar className="h-4 w-4 text-primary" /> Next twins: startups that look like your breakouts
              </h2>
              <p className="text-xs text-muted-foreground">
                Found in Cala, not on Leadline yet. &quot;Raising soon&quot; means 12+ months since their last round.
              </p>
            </div>
            {discover.nextTwins.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No look-alikes yet. This needs a portfolio company that later raised a bigger round, and the data has none
                for your fund.
              </p>
            )}
            <div className="grid gap-3 md:grid-cols-2">
              {discover.nextTwins.map((t) => (
                <Link
                  key={t.company}
                  href={`/investor/company/${encodeURIComponent(t.company)}`}
                  className="block rounded-xl border border-border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-secondary/30"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="font-semibold">{t.company}</div>
                      <div className="text-xs text-muted-foreground">{t.description}</div>
                    </div>
                    {t.raisingSoon && (
                      <span className="shrink-0 rounded-md border border-sky-500/25 bg-sky-500/10 px-2 py-0.5 text-xs font-medium text-sky-700 dark:text-sky-400">
                        Raising soon
                      </span>
                    )}
                  </div>
                  <div className="mt-2 text-xs">
                    Looks like your <span className="font-medium">{t.looksLike}</span>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Last round: {t.lastRound.round} {fmtEur(t.lastRound.amountEurM)}, {fmtMonth(t.lastRound.announced)} (
                    {t.monthsSinceLast} months ago)
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">Backed by {t.backers.join(", ") || "unknown"}</div>
                  <div className="mt-2 flex items-center gap-1 text-xs font-medium text-primary">
                    View due diligence <ChevronRight className="h-3 w-3" />
                  </div>
                </Link>
              ))}
            </div>
          </section>
        </div>
      )}
    </AppLayout>
  );
}
