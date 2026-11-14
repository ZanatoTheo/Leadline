"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, Gauge, GitBranch, Handshake, Loader2, Mail, Target, Users } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/button";
import {
  ConflictBadge,
  DealClaim,
  ErrorBox,
  PoweredByCala,
  ScoreBar,
  SourceLinks,
  TimingBadge,
  postJson,
  useRequiredProfile,
} from "@/components/leadline/shared";
import { cn } from "@/lib/utils";
import { RequestIntro } from "@/components/leadline/request-intro";
import { draftOutreach } from "@/lib/leadline/outreach";
import { fmtDate, fmtEur } from "@/lib/leadline/format";
import type { Deal, InvestorBrief } from "@/lib/leadline/types";
import { sectorLabel, slugify, stageLabel } from "@/lib/leadline/types";

type BriefResponse = InvestorBrief & { mode: "live" | "simulated" };

function Card({
  icon: Icon,
  title,
  tone = "default",
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  tone?: "default" | "good" | "warn" | "muted";
  children: React.ReactNode;
}) {
  return (
    <section
      className={cn(
        "rounded-xl border bg-card p-5",
        tone === "good" && "border-emerald-500/25",
        tone === "warn" && "border-amber-500/25",
        tone === "default" && "border-border",
        tone === "muted" && "border-border",
      )}
    >
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Icon className="h-4 w-4 text-primary" /> {title}
      </h2>
      {children}
    </section>
  );
}

function DealList({ deals, role }: { deals: Deal[]; role: "Led" | "Joined" }) {
  if (!deals.length) return <p className="text-sm text-muted-foreground">None in the matching rounds.</p>;
  return (
    <div className="space-y-3">
      {deals.map((d) => (
        <div key={d.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-sm">
          <div className="min-w-0">
            <span className="font-medium">
              {role} {d.company}&apos;s {fmtEur(d.amountEurM)} {d.round.toLowerCase()}
            </span>
            <span className="text-muted-foreground">, {fmtDate(d.announced)}</span>
            {d.companyDescription && <div className="text-xs text-muted-foreground">{d.companyDescription}</div>}
          </div>
          <SourceLinks sources={d.sources} />
        </div>
      ))}
    </div>
  );
}

export default function InvestorPage() {
  const { slug } = useParams<{ slug: string }>();
  const profile = useRequiredProfile();
  const [data, setData] = useState<BriefResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!profile) return;
    const ctrl = new AbortController();
    setData(null);
    postJson<BriefResponse>("/api/investor", { profile, slug }, ctrl.signal)
      .then(setData)
      .catch((e) => e.name !== "AbortError" && setError(e.message));
    return () => ctrl.abort();
  }, [profile, slug]);

  const inv = data?.investor;

  return (
    <AppLayout>
      <Link href="/investors" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to shortlist
      </Link>

      {error && <ErrorBox message={error} />}
      {!data && !error && (
        <div className="flex items-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Building the brief from Cala…
        </div>
      )}

      {data && inv && profile && (
        <div className="space-y-5">
          {/* Header */}
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-xs font-medium text-muted-foreground">
                {data.rank > 0
                  ? `#${data.rank} of ${data.of} investors in ${stageLabel(profile.stage)} ${sectorLabel(profile.sector)}`
                  : `On your twins' path · doesn't lead at ${stageLabel(profile.stage).toLowerCase()} in this data`}
              </div>
              <h1 className="mt-1 text-2xl font-bold tracking-tight">{inv.name}</h1>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {data.rank > 0 && <ScoreBar score={inv.score} />}
                <TimingBadge status={data.timing.status} />
                <ConflictBadge conflict={inv.conflict} />
              </div>
            </div>
            <div className="flex flex-col items-end gap-2">
              <Link href={`/outreach/${inv.slug}`}>
                <Button variant="outline">
                  <Mail className="h-4 w-4" /> Draft an email instead
                </Button>
              </Link>
              <PoweredByCala mode={data.mode} />
            </div>
          </div>

          {inv.conflict.level !== "none" && (
            <div
              className={cn(
                "rounded-lg border p-4 text-sm",
                inv.conflict.level === "direct" ? "border-rose-500/25 bg-rose-500/5" : "border-amber-500/25 bg-amber-500/5",
              )}
            >
              <div className="font-semibold">
                {inv.conflict.level === "direct" ? "Portfolio conflict" : "Possible portfolio conflict"}
              </div>
              <p className="mt-1">
                {inv.conflict.reason} <SourceLinks sources={inv.conflict.sources} />
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Many funds won&apos;t lead a round for a direct competitor of a portfolio company.
              </p>
            </div>
          )}

          <RequestIntro
            investor={inv.name}
            defaultNote={draftOutreach(profile, data).body.split("\n").slice(2, -3).join("\n").trim()}
          />

          {/* The three-part brief */}
          <div className="grid gap-4 lg:grid-cols-3">
            <Card icon={Target} title="Why them">
              <p className="text-sm">{inv.explanation}</p>
              {data.twinsLed.length > 0 && (
                <div className="mt-3 space-y-1.5">
                  <div className="flex items-center gap-1 text-xs font-semibold text-violet-700 dark:text-violet-400">
                    <GitBranch className="h-3 w-3" /> Led rounds for your twins
                  </div>
                  {data.twinsLed.map((d) => (
                    <div key={d.id}>
                      <DealClaim deal={d} />
                    </div>
                  ))}
                </div>
              )}
              {data.twinsLed.length === 0 && inv.ledDeals[0] && (
                <div className="mt-3">
                  <DealClaim deal={inv.ledDeals[0]} />
                </div>
              )}
            </Card>

            <Card icon={Gauge} title="Why now" tone={data.timing.status === "deploying" ? "good" : "muted"}>
              <p className="text-sm font-medium">{data.timing.headline}</p>
              <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                {data.timing.reasons.map((r) => (
                  <li key={r}>• {r}</li>
                ))}
              </ul>
              {data.timing.latestFund && (
                <div className="mt-2">
                  <SourceLinks sources={data.timing.latestFund.sources} />
                </div>
              )}
            </Card>

            <Card icon={Handshake} title="Why you" tone={data.synergies.length ? "good" : "muted"}>
              {data.synergies.length ? (
                <>
                  <p className="text-sm">
                    <b>{data.synergies.length}</b> of their portfolio companies look like your customers
                    {profile.customers ? ` (${profile.customers})` : ""}. You can help their portfolio, not just ask
                    for money.
                  </p>
                  <div className="mt-2 space-y-1.5">
                    {data.synergies.slice(0, 4).map((s) => (
                      <div key={s.company} className="text-xs">
                        <span className="font-medium">{s.company}</span>: {s.description} <SourceLinks sources={s.sources} />
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {profile.customers
                    ? `No portfolio companies that look like ${profile.customers} found.`
                    : "Add who you sell to on My startup to find portfolio companies that could be your customers."}
                </p>
              )}
            </Card>
          </div>

          {/* Round builder */}
          <Card icon={Users} title={`Round builder: who invests alongside ${inv.name} when they lead`}>
            {data.coInvestors.length === 0 ? (
              <p className="text-sm text-muted-foreground">No repeat co-investors in their led rounds.</p>
            ) : (
              <>
                <div className="grid gap-2 sm:grid-cols-2">
                  {data.coInvestors.map((c) => (
                    <Link
                      key={c.name}
                      href={`/investors/${slugify(c.name)}`}
                      className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2 hover:bg-secondary/40"
                    >
                      <span className="text-sm font-medium">{c.name}</span>
                      <span className="flex items-center gap-2">
                        <span className="h-1.5 w-16 overflow-hidden rounded-full bg-secondary">
                          <span className="block h-full rounded-full bg-primary" style={{ width: `${(c.together / c.of) * 100}%` }} />
                        </span>
                        <span className="text-xs tabular-nums text-muted-foreground">
                          {c.together} of {c.of} rounds
                        </span>
                      </span>
                    </Link>
                  ))}
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  Once {inv.name} commits, these are the investors most likely to fill the rest of your round.
                </p>
              </>
            )}
          </Card>

          {data.rank > 0 && (
            <>
              <Card icon={Target} title={`${stageLabel(profile.stage)} rounds in your space they led (${inv.ledDeals.length})`}>
                <DealList deals={inv.ledDeals} role="Led" />
              </Card>
              {inv.joinedDeals.length > 0 && (
                <Card icon={Users} title={`Joined without leading (${inv.joinedDeals.length})`}>
                  <DealList deals={inv.joinedDeals} role="Joined" />
                </Card>
              )}
            </>
          )}

          <Card icon={Handshake} title={`Portfolio in Cala, last 3 years (${data.portfolio.length})`}>
            <div className="grid gap-3 sm:grid-cols-2">
              {data.portfolio.slice(0, 30).map((p) => (
                <div key={p.company} className="text-sm">
                  <span className="font-medium">{p.company}</span>
                  {p.industry && <span className="text-xs text-muted-foreground"> · {p.industry}</span>}{" "}
                  <SourceLinks sources={p.sources.slice(0, 1)} />
                  {p.description && <div className="text-xs text-muted-foreground">{p.description}</div>}
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </AppLayout>
  );
}
