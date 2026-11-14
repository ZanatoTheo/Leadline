"use client";

import { useState } from "react";
import { Check, Clock, Mail, Send, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { PASS_REASONS, type Intro, type PublicFounder } from "@/lib/leadline/match-types";
import { stageLabel } from "@/lib/leadline/types";
import { postJson } from "./shared";

/** Investor answers an intro request; the server checks it's theirs to answer. */
export async function answerIntro(id: string, status: "accepted" | "passed", passReason?: string) {
  const res = await fetch("/api/intros", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, status, passReason }),
  });
  if (!res.ok) throw new Error((await res.json()).error);
}

/** Investor invites a discoverable founder to connect. */
export async function inviteFounder(founderId: string, note: string) {
  await postJson("/api/intros", { founderId, note });
}

/**
 * The investor's side of an intro: match status, Interested / Pass with a
 * reason for incoming requests, or an invite for founders not yet contacted.
 */
export function IntroActions({
  founder,
  intro,
  email,
  onChange,
}: {
  founder: PublicFounder;
  intro?: Intro | null;
  email?: string;
  onChange: () => Promise<void> | void;
}) {
  const p = founder.profile;
  const [passing, setPassing] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [note, setNote] = useState(
    `Hi ${founder.founderName || "there"}, ${p.startupName} looks a lot like companies we've backed. Open to a quick call about your ${stageLabel(p.stage).toLowerCase()}?`,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const incoming = intro?.direction === "founder-to-investor";

  return (
    <div className="space-y-2">
      {intro?.status === "accepted" && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-emerald-500/25 bg-emerald-500/5 p-3 text-sm">
          <Check className="h-4 w-4 text-emerald-500" />
          Matched.{" "}
          {email ? (
            <a href={`mailto:${email}`} className="font-medium text-primary underline">
              {founder.founderName || "Founder"} · {email}
            </a>
          ) : (
            "The founder will reach out."
          )}
        </div>
      )}
      {intro?.status === "passed" && (
        <div className="text-sm text-muted-foreground">
          {incoming ? `You passed: ${intro.passReason ?? "no reason"}` : `${p.startupName} declined your invite.`}
        </div>
      )}
      {intro?.status === "pending" && !incoming && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Clock className="h-4 w-4" /> Invite sent. Waiting for {p.startupName} to accept.
        </div>
      )}

      {intro?.status === "pending" && incoming && (
        <>
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy} onClick={() => run(() => answerIntro(intro.id, "accepted"))}>
              <Check className="h-4 w-4" /> Interested: share contacts
            </Button>
            <Button variant="outline" disabled={busy} onClick={() => setPassing((v) => !v)}>
              <X className="h-4 w-4" /> Pass
            </Button>
          </div>
          {passing && (
            <div className="flex flex-wrap gap-1.5">
              <span className="w-full text-xs text-muted-foreground">
                One click. The founder sees the reason, which helps them more than silence.
              </span>
              {PASS_REASONS.map((r) => (
                <button
                  key={r}
                  disabled={busy}
                  onClick={() => run(() => answerIntro(intro.id, "passed", r))}
                  className="rounded-md border border-border px-2.5 py-1 text-xs hover:bg-secondary"
                >
                  {r}
                </button>
              ))}
            </div>
          )}
        </>
      )}

      {!intro &&
        (inviting ? (
          <>
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
            <div className="flex gap-2">
              <Button disabled={busy || !note.trim()} onClick={() => run(() => inviteFounder(founder.id, note))}>
                <Send className="h-4 w-4" /> Send invite
              </Button>
              <Button variant="ghost" onClick={() => setInviting(false)}>
                Cancel
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">Contacts are only shared if {p.startupName} accepts.</p>
          </>
        ) : (
          <Button variant="outline" onClick={() => setInviting(true)}>
            <Mail className="h-4 w-4" /> Invite to connect
          </Button>
        ))}

      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
