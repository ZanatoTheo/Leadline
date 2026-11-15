"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Check, Clock, Inbox, Loader2, MessageSquareWarning, Send, X } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/button";
import { ErrorBox, postJson, useRequiredProfile, useRequiredProfileOptional } from "@/components/leadline/shared";
import { FitPoints, FitScore } from "@/components/leadline/fit";
import type { FitReport, Intro } from "@/lib/leadline/match-types";
import { daysAgoText } from "@/lib/leadline/format";
import { ageDays } from "@/lib/leadline/rank";
import { slugify } from "@/lib/leadline/types";

function StatusPill({ intro }: { intro: Intro }) {
  if (intro.status === "accepted")
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-400">
        <Check className="h-3 w-3" /> Matched
      </span>
    );
  if (intro.status === "passed")
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-0.5 text-xs font-medium text-muted-foreground">
        <X className="h-3 w-3" /> Passed
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
      <Clock className="h-3 w-3" /> Waiting
    </span>
  );
}

function Invite({ intro, onAnswer }: { intro: Intro; onAnswer: (status: "accepted" | "passed") => Promise<void> }) {
  const profile = useRequiredProfileOptional();
  const [fit, setFit] = useState<FitReport | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (profile) postJson<FitReport>("/api/fit", { profile, investor: intro.investor }).then(setFit).catch(() => {});
  }, [profile, intro.investor]);

  return (
    <div className="rounded-xl border border-primary/30 bg-card p-5">
      <div className="flex items-start gap-4">
        {fit && <FitScore score={fit.score} />}
        <div className="min-w-0 flex-1 space-y-3">
          <div>
            <Link href={`/investors/${slugify(intro.investor)}`} className="text-lg font-semibold hover:underline">
              {intro.investor}
            </Link>{" "}
            <span className="text-xs text-muted-foreground">invited you, {daysAgoText(ageDays(intro.createdAt))}</span>
          </div>
          <p className="whitespace-pre-line rounded-lg border border-border bg-secondary/40 p-3 text-sm">{intro.note}</p>
          {fit && (
            <div>
              <div className="mb-1 text-xs font-semibold text-muted-foreground">Is {intro.investor} right for you? From Cala:</div>
              <FitPoints fit={fit} />
            </div>
          )}
          {intro.status === "pending" ? (
            <div className="flex gap-2">
              <Button
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  await onAnswer("accepted");
                  setBusy(false);
                }}
              >
                <Check className="h-4 w-4" /> Accept: share my email
              </Button>
              <Button
                variant="outline"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  await onAnswer("passed");
                  setBusy(false);
                }}
              >
                Not now
              </Button>
            </div>
          ) : (
            <StatusPill intro={intro} />
          )}
        </div>
      </div>
    </div>
  );
}

export default function IntrosPage() {
  const profile = useRequiredProfile();
  const [intros, setIntros] = useState<Intro[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await fetch("/api/intros").then((r) => r.json());
      setIntros(d.intros ?? []);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (profile) load();
  }, [profile, load]);

  const answer = (id: string) => async (status: "accepted" | "passed") => {
    const res = await fetch("/api/intros", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, status }),
    });
    if (!res.ok) setError((await res.json()).error);
    await load();
  };

  const invites = (intros ?? []).filter((i) => i.direction === "investor-to-founder");
  const sent = (intros ?? []).filter((i) => i.direction === "founder-to-investor");
  const reasons = sent.filter((i) => i.status === "passed" && i.passReason);
  const reasonCounts = [...new Set(reasons.map((r) => r.passReason!))].map((r) => ({
    reason: r,
    count: reasons.filter((x) => x.passReason === r).length,
  }));

  return (
    <AppLayout>
      <div className="mb-6 max-w-2xl">
        <h1 className="text-2xl font-bold tracking-tight">Intros</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Double opt-in: your email is shared only when you and the investor both say yes. Investors who pass tell
          you why.
        </p>
      </div>

      {error && <ErrorBox message={error} />}
      {intros === null && !error && (
        <div className="flex items-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </div>
      )}

      {intros && (
        <div className="space-y-8">
          <section className="space-y-3">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <Inbox className="h-4 w-4 text-primary" /> Investors who reached out ({invites.length})
            </h2>
            {invites.length === 0 && (
              <p className="text-sm text-muted-foreground">
                None yet. Investors whose track record fits you can invite you when you&apos;re discoverable (on My
                startup).
              </p>
            )}
            {invites.map((i) => (
              <Invite key={i.id} intro={i} onAnswer={answer(i.id)} />
            ))}
          </section>

          <section className="space-y-3">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <Send className="h-4 w-4 text-primary" /> Requests you sent ({sent.length})
            </h2>
            {sent.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Open an investor from{" "}
                <Link href="/investors" className="text-primary underline">
                  Who to pitch
                </Link>{" "}
                and request an intro.
              </p>
            )}
            <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
              {sent.map((i) => (
                <div key={i.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
                  <div>
                    <Link href={`/investors/${slugify(i.investor)}`} className="font-medium hover:underline">
                      {i.investor}
                    </Link>
                    <div className="text-xs text-muted-foreground">
                      Sent {daysAgoText(ageDays(i.createdAt))}
                      {i.status === "passed" && i.passReason && ` · Their reason: ${i.passReason}`}
                      {i.status === "accepted" && " · They have your email and will be in touch"}
                    </div>
                  </div>
                  <StatusPill intro={i} />
                </div>
              ))}
            </div>
          </section>

          {reasonCounts.length > 0 && (
            <section className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-5">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <MessageSquareWarning className="h-4 w-4 text-amber-500" /> What investors are telling you
              </h2>
              <ul className="mt-2 space-y-1 text-sm">
                {reasonCounts.map((r) => (
                  <li key={r.reason}>
                    <b>{r.count}×</b> {r.reason}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted-foreground">
                Feedback founders rarely get. Use it to adjust your round size, timing or who you pitch.
              </p>
            </section>
          )}
        </div>
      )}
    </AppLayout>
  );
}
