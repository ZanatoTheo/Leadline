"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Inbox, Loader2, Radar, Sparkles, X } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { ErrorBox, PoweredByCala, postJson } from "@/components/leadline/shared";
import { FitScore } from "@/components/leadline/fit";
import { ActionItem, ProgressStrip, TodayGroup, greeting } from "@/components/leadline/today";
import { useSession } from "@/components/leadline/session";
import type { DiscoverResponse } from "@/lib/leadline/match-types";
import { daysAgoText, fmtEur } from "@/lib/leadline/format";
import { ageDays } from "@/lib/leadline/rank";
import { stageLabel } from "@/lib/leadline/types";

export default function InvestorTodayPage() {
  const session = useSession();
  const router = useRouter();
  const [data, setData] = useState<DiscoverResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session.investorName) {
      router.replace("/investor/setup");
      return;
    }
    postJson<DiscoverResponse>("/api/discover", {}).then(setData).catch((e) => setError(e.message));
  }, [session.investorName, router]);

  const founders = data?.founders ?? [];
  const requests = founders.filter((f) => f.intro?.direction === "founder-to-investor" && f.intro.status === "pending");
  const matches = founders.filter((f) => f.intro?.status === "accepted");
  const declined = founders.filter((f) => f.intro?.direction === "investor-to-founder" && f.intro.status === "passed");
  const toInvite = founders.filter((f) => !f.intro && f.fit.score >= 60).slice(0, 3);
  const raisingSoon = (data?.nextTwins ?? []).filter((t) => t.raisingSoon).slice(0, 3);
  const inbound = founders.filter((f) => f.intro?.direction === "founder-to-investor");
  const avgFit = inbound.length ? Math.round(inbound.reduce((s, f) => s + f.fit.score, 0) / inbound.length) : null;

  return (
    <AppLayout>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" suppressHydrationWarning>{greeting(session.name)}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {session.investorName}. Here&apos;s what needs you today, matched against what you actually lead.
          </p>
        </div>
        <PoweredByCala mode={data?.mode} />
      </div>

      {error && <ErrorBox message={error} />}

      <div className="mb-6">
        <ProgressStrip
          items={[
            { label: "intro requests waiting", value: requests.length, tone: requests.length ? "urgent" : undefined },
            { label: "matches", value: matches.length, tone: "good" },
            { label: "average fit of inbound", value: avgFit ?? "–" },
            { label: "look-alikes raising soon", value: raisingSoon.length },
            { label: "founders who fit, not contacted", value: founders.filter((f) => !f.intro && f.fit.score >= 60).length },
          ]}
        />
      </div>

      {!data && !error && (
        <div className="mb-4 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Matching founders against your rounds in Cala…
        </div>
      )}

      {data && (
        <div className="space-y-6">
          <TodayGroup title="Needs your answer" empty="No intro requests waiting.">
            {requests.map((f) => (
              <ActionItem
                key={f.founder.id}
                icon={Inbox}
                tone="urgent"
                title={
                  <>
                    <b>{f.founder.profile.startupName}</b> asked for an intro ·{" "}
                    {stageLabel(f.founder.profile.stage)} {fmtEur(f.founder.profile.raiseEurM)}
                  </>
                }
                detail={`${daysAgoText(ageDays(f.intro!.createdAt))} · ${f.fit.headline}`}
                href={`/investor/startup/${f.founder.id}`}
                cta="Decide"
                badge={<FitScore score={f.fit.score} />}
              />
            ))}
          </TodayGroup>

          <TodayGroup title="Matches" empty="No matches yet.">
            {matches.map((f) => (
              <ActionItem
                key={f.founder.id}
                icon={Check}
                tone="good"
                title={
                  <>
                    <b>{f.founder.profile.startupName}</b>{" "}
                    {f.intro!.direction === "investor-to-founder" ? "accepted your invite" : "is matched"}
                  </>
                }
                detail="Contacts are shared. Book the first call."
                href={`/investor/startup/${f.founder.id}`}
                cta="Get email"
              />
            ))}
            {declined.map((f) => (
              <ActionItem
                key={f.founder.id}
                icon={X}
                tone="muted"
                title={<><b>{f.founder.profile.startupName}</b> declined your invite</>}
                href={`/investor/startup/${f.founder.id}`}
                cta="View"
              />
            ))}
          </TodayGroup>

          <TodayGroup title="Before anyone else leads" empty="No look-alikes of your breakouts are due to raise.">
            {raisingSoon.map((t) => (
              <ActionItem
                key={t.company}
                icon={Radar}
                tone="info"
                title={<><b>{t.company}</b> looks like your {t.looksLike} and is likely raising</>}
                detail={`${t.monthsSinceLast} months since their ${t.lastRound.round} (${fmtEur(t.lastRound.amountEurM)}) · ${t.description}`}
                href={`/investor/company/${encodeURIComponent(t.company)}`}
                cta="Diligence"
              />
            ))}
          </TodayGroup>

          <TodayGroup title="Founders who fit you" empty="No uncontacted founders with a strong fit right now.">
            {toInvite.map((f) => (
              <ActionItem
                key={f.founder.id}
                icon={Sparkles}
                tone="urgent"
                title={<><b>{f.founder.profile.startupName}</b>: {f.founder.profile.oneLiner}</>}
                detail={f.fit.headline}
                href={`/investor/startup/${f.founder.id}`}
                cta="Invite"
                badge={<FitScore score={f.fit.score} />}
              />
            ))}
          </TodayGroup>
        </div>
      )}
    </AppLayout>
  );
}
