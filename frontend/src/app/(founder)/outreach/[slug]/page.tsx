"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check, Copy, Loader2, Mail } from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  ConflictBadge,
  ErrorBox,
  PoweredByCala,
  SourceLinks,
  postJson,
  useRequiredProfile,
} from "@/components/leadline/shared";
import { useSession } from "@/components/leadline/session";
import { draftOutreach } from "@/lib/leadline/outreach";
import type { InvestorBrief } from "@/lib/leadline/types";

type BriefResponse = InvestorBrief & { mode: "live" | "simulated" };

function OutreachEditor() {
  const { slug } = useParams<{ slug: string }>();
  const focusDeal = useSearchParams().get("deal") ?? undefined;
  const profile = useRequiredProfile();
  const founderName = useSession().name;
  const [data, setData] = useState<BriefResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [copied, setCopied] = useState(false);

  const draft = useMemo(
    () => (data && profile ? draftOutreach(profile, data, focusDeal, founderName) : null),
    [data, profile, focusDeal, founderName],
  );

  useEffect(() => {
    if (!profile) return;
    const ctrl = new AbortController();
    postJson<BriefResponse>("/api/investor", { profile, slug }, ctrl.signal)
      .then(setData)
      .catch((e) => e.name !== "AbortError" && setError(e.message));
    return () => ctrl.abort();
  }, [profile, slug]);

  useEffect(() => {
    if (draft) {
      setSubject(draft.subject);
      setBody(draft.body);
    }
  }, [draft]);

  const copy = async () => {
    await navigator.clipboard.writeText(`Subject: ${subject}\n\n${body}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <>
      <Link href={`/investors/${slug}`} className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to investor
      </Link>
      {error && <ErrorBox message={error} />}
      {!data && !error && (
        <div className="flex items-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Writing a draft from their deals, portfolio and funds…
        </div>
      )}
      {data && draft && (
        <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h1 className="text-2xl font-bold tracking-tight">Outreach to {data.investor.name}</h1>
              <PoweredByCala mode={data.mode} />
            </div>
            <Input value={subject} onChange={(e) => setSubject(e.target.value)} aria-label="Subject" />
            <Textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={18}
              className="font-mono text-[13px] leading-relaxed"
              aria-label="Email body"
            />
            <div className="flex gap-2">
              <Button onClick={copy}>
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {copied ? "Copied" : "Copy email"}
              </Button>
              <a href={`mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`}>
                <Button variant="outline">
                  <Mail className="h-4 w-4" /> Open in mail app
                </Button>
              </a>
            </div>
          </div>

          <aside className="space-y-4">
            <div className="rounded-xl border border-border bg-card p-4">
              <h2 className="text-sm font-semibold">Facts in this draft</h2>
              <p className="mt-1 text-xs text-muted-foreground">Every claim comes from Cala. Check each one before sending.</p>
              <div className="mt-3 space-y-2.5">
                {draft.facts.length === 0 && <p className="text-sm text-muted-foreground">No sourced facts to cite.</p>}
                {draft.facts.map((f) => (
                  <div key={f.text} className="text-sm">
                    {f.text} <SourceLinks sources={f.sources} />
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <h2 className="text-sm font-semibold">Before you send</h2>
              <div className="mt-2">
                <ConflictBadge conflict={data.investor.conflict} />
              </div>
              {data.investor.conflict.reason && (
                <p className="mt-2 text-xs text-muted-foreground">{data.investor.conflict.reason}</p>
              )}
              {data.coInvestors[0] && (
                <p className="mt-2 text-xs text-muted-foreground">
                  If they say yes, {data.coInvestors[0].name} joined {data.coInvestors[0].together} of their{" "}
                  {data.coInvestors[0].of} led rounds. Line them up next.
                </p>
              )}
            </div>
          </aside>
        </div>
      )}
    </>
  );
}

export default function OutreachPage() {
  return (
    <AppLayout>
      <Suspense>
        <OutreachEditor />
      </Suspense>
    </AppLayout>
  );
}
