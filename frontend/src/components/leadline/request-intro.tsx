"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Check, Clock, Handshake, Loader2, Send, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { FitPoints, FitScore } from "./fit";
import { postJson, syncFounder, useRequiredProfileOptional } from "./shared";
import type { FitReport, Intro } from "@/lib/leadline/match-types";

/**
 * Lets a founder send an evidence-backed intro request instead of a cold email,
 * and shows them exactly what the investor will see first.
 */
export function RequestIntro({ investor, defaultNote }: { investor: string; defaultNote: string }) {
  const profile = useRequiredProfileOptional();
  const [fit, setFit] = useState<FitReport | null>(null);
  const [intro, setIntro] = useState<Intro | null>(null);
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState(defaultNote);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setNote(defaultNote), [defaultNote]);

  useEffect(() => {
    if (!profile) return;
    postJson<FitReport>("/api/fit", { profile, investor }).then(setFit).catch(() => {});
  }, [profile, investor]);

  useEffect(() => {
    fetch("/api/intros")
      .then((r) => r.json())
      .then((d: { intros?: Intro[] }) => setIntro((d.intros ?? []).find((i) => i.investor === investor) ?? null))
      .catch(() => {});
  }, [investor]);

  const send = async () => {
    setSending(true);
    setError(null);
    try {
      const id = await syncFounder();
      if (!id) throw new Error("Describe your startup first.");
      const r = await postJson<{ intro: Intro }>("/api/intros", { investor, note });
      setIntro(r.intro);
      setOpen(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  if (intro) {
    const map = {
      pending: { icon: Clock, text: `Intro requested. ${investor} sees your fit card and note.`, cls: "border-primary/25 bg-primary/5" },
      accepted: { icon: Check, text: `${investor} is interested. Your contact details are shared.`, cls: "border-emerald-500/25 bg-emerald-500/5" },
      passed: { icon: X, text: `${investor} passed: ${intro.passReason ?? "no reason given"}.`, cls: "border-border bg-secondary/40" },
    } as const;
    const s = map[intro.status];
    return (
      <div className={`flex items-center gap-2 rounded-lg border p-3 text-sm ${s.cls}`}>
        <s.icon className="h-4 w-4 shrink-0" />
        <span className="flex-1">{intro.direction === "investor-to-founder" ? `${investor} invited you to connect.` : s.text}</span>
        <Link href="/intros" className="text-xs font-medium text-primary underline">
          View intros
        </Link>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-primary/25 bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          {fit ? <FitScore score={fit.score} /> : <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <Handshake className="h-4 w-4 text-primary" /> Request an intro through Leadline
            </h2>
            <p className="mt-1 max-w-xl text-xs text-muted-foreground">
              Instead of a cold email, {investor} gets your note with a fit card built from their own Cala track
              record. Your email is only shared if they say yes, and if they pass you&apos;ll see why.
            </p>
          </div>
        </div>
        {!open && (
          <Button onClick={() => setOpen(true)}>
            <Send className="h-4 w-4" /> Request intro
          </Button>
        )}
      </div>

      {open && (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="space-y-2">
            <div className="text-xs font-semibold text-muted-foreground">Your note</div>
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={8} />
            <div className="flex gap-2">
              <Button onClick={send} disabled={sending || !note.trim()}>
                {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Send request
              </Button>
              <Button variant="ghost" onClick={() => setOpen(false)}>
                Cancel
              </Button>
            </div>
            {error && <p className="text-xs text-destructive">{error}</p>}
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold text-muted-foreground">What {investor} will see next to your note</div>
            {fit ? <FitPoints fit={fit} /> : <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>
        </div>
      )}
    </div>
  );
}
