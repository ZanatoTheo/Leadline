"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2, Search, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorBox, PoweredByCala, postJson, useCalaMode } from "@/components/leadline/shared";
import { ThesisView } from "@/components/leadline/thesis";
import { useSession } from "@/components/leadline/session";
import type { InvestorThesis } from "@/lib/leadline/match-types";

export default function InvestorSetupPage() {
  const router = useRouter();
  const mode = useCalaMode();
  const session = useSession();
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<{ id: string; name: string }[]>([]);
  const [picked, setPicked] = useState<string | null>(null);
  const [thesis, setThesis] = useState<InvestorThesis | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (picked || query.trim().length < 2) {
      setOptions([]);
      return;
    }
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      fetch(`/api/funds?q=${encodeURIComponent(query)}`, { signal: ctrl.signal })
        .then((r) => r.json())
        .then((d) => setOptions(d.funds ?? []))
        .catch(() => {});
    }, 200);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [query, picked]);

  const pick = (name: string) => {
    setPicked(name);
    setQuery(name);
    setThesis(null);
    setError(null);
    postJson<InvestorThesis>("/api/thesis", { investor: name })
      .then(setThesis)
      .catch((e) => setError(e.message));
  };

  const confirm = async () => {
    if (!picked) return;
    setSaving(true);
    setError(null);
    try {
      await postJson("/api/investor-fund", { investor: picked });
      // Full reload so the server layout picks up the fund on your account.
      window.location.assign("/investor/today");
    } catch (e) {
      setError(`${picked} wasn't saved to your account. Press the button again to retry. ${(e as Error).message}`);
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <nav className="border-b border-border">
        <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-primary">
              <Zap className="h-3.5 w-3.5 text-primary-foreground" />
            </div>
            <span className="text-sm font-semibold">Leadline</span>
            <span className="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">for investors</span>
          </Link>
          <PoweredByCala mode={mode} />
        </div>
      </nav>

      <main className="mx-auto max-w-4xl px-6 py-10">
        <h1 className="text-2xl font-bold tracking-tight">
          {session.investorName ? `Switch fund (currently ${session.investorName})` : `Welcome ${session.name}. Which fund are you?`}
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          No thesis form to fill in. Leadline reads what you actually do from your rounds in Cala: what you lead, at
          which check size, and which of your companies broke out. Then it finds founders who fit.
        </p>

        <div className="relative mt-6 max-w-md">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPicked(null);
              setThesis(null);
            }}
            placeholder="Start typing your fund's name, e.g. Fjord"
            className="pl-9"
            autoFocus
          />
          {options.length > 0 && (
            <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-border bg-card shadow-md">
              {options.map((o) => (
                <button
                  key={o.id}
                  onClick={() => pick(o.name)}
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-secondary"
                >
                  {o.name}
                </button>
              ))}
            </div>
          )}
        </div>

        {error && <div className="mt-6"><ErrorBox message={error} /></div>}
        {picked && !thesis && !error && (
          <div className="mt-8 flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Reading {picked}&apos;s rounds, funds and breakouts in Cala…
          </div>
        )}

        {thesis && (
          <div className="mt-8 space-y-5">
            <h2 className="text-lg font-semibold">Here&apos;s {thesis.investor}, according to Cala</h2>
            <ThesisView thesis={thesis} />
            <div className="flex items-center justify-end gap-3">
              <span className="text-xs text-muted-foreground">Something wrong? Every line links to its source.</span>
              <Button onClick={confirm} disabled={saving}>
                That&apos;s us. Show me founders who fit <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
