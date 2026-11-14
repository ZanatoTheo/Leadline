"use client";

import { useEffect, useState } from "react";
import { Bell, Check, Handshake, Landmark, Loader2, Send, Sparkles, X } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { ErrorBox, PoweredByCala, postJson, useRequiredProfile } from "@/components/leadline/shared";
import { ActionItem, ProgressStrip, TodayGroup, greeting } from "@/components/leadline/today";
import { useSession } from "@/components/leadline/session";
import { useLeadline, useUnreadSignals } from "@/lib/leadline/store";
import type { Intro } from "@/lib/leadline/match-types";
import type { RankedInvestor, ShortlistResponse } from "@/lib/leadline/types";
import { stageLabel } from "@/lib/leadline/types";
import { daysAgoText, dealPhrase, fmtEur } from "@/lib/leadline/format";
import { ageDays } from "@/lib/leadline/rank";

/** Best investors to approach now: deploying first, then lead index; skip conflicts and anyone already contacted. */
function pitchNow(investors: RankedInvestor[], contacted: Set<string>): RankedInvestor[] {
  return investors
    .filter((i) => i.ledCount > 0 && i.conflict.level !== "direct" && !contacted.has(i.name))
    .sort(
      (a, b) =>
        Number(b.timingStatus === "deploying") - Number(a.timingStatus === "deploying") ||
        (b.twinsLedCount ?? 0) - (a.twinsLedCount ?? 0) ||
        b.score - a.score,
    )
    .slice(0, 3);
}

export default function FounderTodayPage() {
  const session = useSession();
  const profile = useRequiredProfile();
  const unreadSignals = useUnreadSignals();
  const signalsCheckedAt = useLeadline((s) => s.signalsCheckedAt);
  const [intros, setIntros] = useState<Intro[] | null>(null);
  const [shortlist, setShortlist] = useState<ShortlistResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!profile) return;
    fetch("/api/intros")
      .then((r) => r.json())
      .then((d) => setIntros(d.intros ?? []))
      .catch((e) => setError(e.message));
    postJson<ShortlistResponse>("/api/shortlist", profile)
      .then(setShortlist)
      .catch((e) => setError(e.message));
  }, [profile]);

  const all = intros ?? [];
  const invites = all.filter((i) => i.direction === "investor-to-founder" && i.status === "pending");
  const sent = all.filter((i) => i.direction === "founder-to-investor");
  const matched = all.filter((i) => i.status === "accepted");
  const passed = sent.filter((i) => i.status === "passed");
  const waiting = sent.filter((i) => i.status === "pending");
  const contacted = new Set(all.map((i) => i.investor));
  const recommendations = shortlist ? pitchNow(shortlist.investors, contacted) : [];
  const loading = !intros || !shortlist || !signalsCheckedAt;

  return (
    <AppLayout>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" suppressHydrationWarning>{greeting(session.name)}</h1>
          {profile && (
            <p className="mt-1 text-sm text-muted-foreground">
              {profile.startupName} · raising {fmtEur(profile.raiseEurM)} {stageLabel(profile.stage).toLowerCase()}. Here&apos;s
              what needs you today.
            </p>
          )}
        </div>
        <PoweredByCala mode={shortlist?.mode} />
      </div>

      {error && <ErrorBox message={error} />}

      <div className="mb-6">
        <ProgressStrip
          items={[
            { label: "intro requests sent", value: sent.length },
            { label: "waiting for an answer", value: waiting.length },
            { label: "matched", value: matched.length, tone: "good" },
            { label: "passed (with reasons)", value: passed.length },
            { label: "investors inviting you", value: invites.length, tone: invites.length ? "urgent" : undefined },
          ]}
        />
      </div>

      {loading && !error && (
        <div className="mb-4 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Checking Cala and your intros…
        </div>
      )}

      <div className="space-y-6">
        <TodayGroup title="Needs your answer" empty="Nothing waiting on you.">
          {invites.map((i) => (
            <ActionItem
              key={i.id}
              icon={Handshake}
              tone="urgent"
              title={<><b>{i.investor}</b> invited you to connect</>}
              detail={`${daysAgoText(ageDays(i.createdAt))}. Your email is only shared if you accept.`}
              href="/intros"
              cta="Review"
            />
          ))}
        </TodayGroup>

        <TodayGroup title="Replies to your intro requests" empty="No replies yet.">
          {matched.map((i) => (
            <ActionItem
              key={i.id}
              icon={Check}
              tone="good"
              title={<><b>{i.investor}</b> is interested</>}
              detail="They have your email. Reply fast: send your deck and propose times."
              href="/intros"
              cta="Open"
            />
          ))}
          {passed.map((i) => (
            <ActionItem
              key={i.id}
              icon={X}
              tone="muted"
              title={<><b>{i.investor}</b> passed: {i.passReason ?? "no reason given"}</>}
              detail="Use it: adjust who you pitch, your round size or your timing."
              href="/intros"
              cta="See feedback"
            />
          ))}
        </TodayGroup>

        <TodayGroup title="New in your market" empty="No new rounds or fund closes since you last looked.">
          {unreadSignals.slice(0, 4).map((s) => (
            <ActionItem
              key={s.id}
              icon={s.kind === "fund" ? Landmark : Bell}
              tone="info"
              title={
                s.kind === "fund" && s.fund ? (
                  <><b>{s.investor}</b> closed {s.fund.fundName}{s.fund.sizeEurM ? ` (${fmtEur(s.fund.sizeEurM)})` : ""}</>
                ) : (
                  <><b>{s.investor}</b> led {s.deal ? dealPhrase(s.deal) : "a round"}</>
                )
              }
              detail={[
                daysAgoText(s.daysAgo),
                s.kind === "fund" ? "fresh funds need to deploy" : null,
                s.conflict.level === "none" ? "no competitor in their portfolio" : `check conflict: ${s.conflict.company}`,
                s.synergyCount ? `${s.synergyCount} portfolio cos could buy from you` : null,
              ]
                .filter(Boolean)
                .join(" · ")}
              href={`/investors/${s.investorSlug}`}
              cta="See why"
            />
          ))}
        </TodayGroup>

        <TodayGroup title="Who to approach next" empty={shortlist ? "You've contacted everyone on your shortlist." : "Loading…"}>
          {recommendations.map((i) => (
            <ActionItem
              key={i.slug}
              icon={i.twinsLedCount ? Sparkles : Send}
              tone="urgent"
              title={<><b>{i.name}</b>: {i.explanation}</>}
              detail={[
                i.twinsLedCount ? `backed ${i.twinsLedCount} of your twins` : null,
                i.timingHeadline,
                i.synergyCount ? `${i.synergyCount} portfolio cos could buy from you` : null,
              ]
                .filter(Boolean)
                .join(" · ")}
              href={`/investors/${i.slug}`}
              cta="Request intro"
            />
          ))}
        </TodayGroup>
      </div>
    </AppLayout>
  );
}
