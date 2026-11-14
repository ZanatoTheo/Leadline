"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Sparkles, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { DEMO_PERSONA, useLeadline } from "@/lib/leadline/store";
import { REGIONS, SECTORS, STAGES, type FounderProfile } from "@/lib/leadline/types";
import { PoweredByCala, syncFounder, useCalaMode, useHydrated, useRequiredProfileOptional } from "@/components/leadline/shared";
import { useSession } from "@/components/leadline/session";

const EMPTY: FounderProfile = {
  startupName: "",
  oneLiner: "",
  sector: "climate",
  stage: "seed",
  location: "",
  region: "europe",
  raiseEurM: 1.5,
  competitors: [],
  customers: "",
};

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
    </label>
  );
}

const selectClass =
  "flex h-9 w-full rounded-lg border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export default function OnboardingPage() {
  const router = useRouter();
  const hydrated = useHydrated();
  const session = useSession();
  const saved = useRequiredProfileOptional();
  const setProfile = useLeadline((s) => s.setProfile);
  const setDiscoverableStore = useLeadline((s) => s.setDiscoverable);
  const [discoverable, setDiscoverable] = useState(session.discoverable);
  const [saving, setSaving] = useState(false);
  const mode = useCalaMode();
  const [form, setForm] = useState<FounderProfile>(EMPTY);
  const [competitors, setCompetitors] = useState("");

  useEffect(() => {
    if (hydrated && saved) {
      setForm({ ...EMPTY, ...saved, customers: saved.customers ?? "" });
      setCompetitors(saved.competitors.join(", "));
    }
  }, [hydrated, saved]);

  const set = <K extends keyof FounderProfile>(key: K, value: FounderProfile[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const fillDemo = () => {
    setForm(DEMO_PERSONA);
    setCompetitors(DEMO_PERSONA.competitors.join(", "));
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfile({
      ...form,
      competitors: competitors.split(",").map((c) => c.trim()).filter(Boolean),
    });
    setDiscoverableStore(discoverable);
    setSaving(true);
    // Save to your account so investors can receive your intro requests.
    await syncFounder().catch(() => null);
    router.push("/today");
  };

  const valid = form.startupName.trim() && form.oneLiner.trim() && form.raiseEurM > 0;

  return (
    <div className="min-h-screen bg-background">
      <nav className="border-b border-border">
        <div className="mx-auto flex h-14 max-w-2xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-primary">
              <Zap className="h-3.5 w-3.5 text-primary-foreground" />
            </div>
            <span className="text-sm font-semibold">Leadline</span>
          </Link>
          <PoweredByCala mode={mode} />
        </div>
      </nav>

      <main className="mx-auto max-w-2xl px-6 py-10">
        <h1 className="text-2xl font-bold tracking-tight">Describe your startup once</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Leadline finds the startups that were where you are, shows who backed them, and keeps watching
          Cala for investors who are ready to lead your round.
        </p>

        <button
          type="button"
          onClick={fillDemo}
          className="mt-5 inline-flex items-center gap-2 rounded-lg border border-dashed border-primary/40 bg-primary/5 px-3 py-2 text-sm text-primary hover:bg-primary/10"
        >
          <Sparkles className="h-4 w-4" />
          Use demo persona: first-time founder raising a €1.5M climate tech seed
        </button>

        <form onSubmit={submit} className="mt-6 space-y-5 rounded-xl border border-border bg-card p-6">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Startup name">
              <Input value={form.startupName} onChange={(e) => set("startupName", e.target.value)} placeholder="Acme" required />
            </Field>
            <Field label="Based in">
              <Input value={form.location} onChange={(e) => set("location", e.target.value)} placeholder="Berlin, Germany" />
            </Field>
          </div>

          <Field label="What you do, in one sentence" hint="Used to spot investors who already back something similar.">
            <Textarea
              value={form.oneLiner}
              onChange={(e) => set("oneLiner", e.target.value)}
              placeholder="Measures and cuts Scope 3 emissions for mid-size manufacturers"
              rows={2}
              required
            />
          </Field>

          <Field label="Who you sell to" hint="Used to find investors whose portfolio companies could become your customers.">
            <Input
              value={form.customers}
              onChange={(e) => set("customers", e.target.value)}
              placeholder="mid-size manufacturers"
            />
          </Field>

          <div className="grid gap-5 sm:grid-cols-3">
            <Field label="Sector">
              <select className={selectClass} value={form.sector} onChange={(e) => set("sector", e.target.value as FounderProfile["sector"])}>
                {SECTORS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </Field>
            <Field label="Round">
              <select className={selectClass} value={form.stage} onChange={(e) => set("stage", e.target.value as FounderProfile["stage"])}>
                {STAGES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </Field>
            <Field label="Investor region">
              <select className={selectClass} value={form.region} onChange={(e) => set("region", e.target.value as FounderProfile["region"])}>
                {REGIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </Field>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Raising (€M)">
              <Input
                type="number"
                min={0.1}
                step={0.1}
                value={form.raiseEurM || ""}
                onChange={(e) => set("raiseEurM", parseFloat(e.target.value) || 0)}
                required
              />
            </Field>
            <Field label="Main competitors" hint="Comma-separated. We flag investors who back them.">
              <Input value={competitors} onChange={(e) => setCompetitors(e.target.value)} placeholder="Tracely, …" />
            </Field>
          </div>

          <label className="flex items-start gap-2.5 rounded-lg border border-border p-3 text-sm">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 accent-[hsl(var(--primary))]"
              checked={discoverable}
              onChange={(e) => setDiscoverable(e.target.checked)}
            />
            <span>
              <span className="font-medium">Let investors who fit find me</span>
              <span className="block text-xs text-muted-foreground">
                Investors whose Cala track record matches you can invite you to connect. Your email ({session.email}) is
                only shared if you accept.
              </span>
            </span>
          </label>

          <Button type="submit" className="w-full" disabled={!valid || saving}>
            Find my funding twins <ArrowRight className="h-4 w-4" />
          </Button>
        </form>
      </main>
    </div>
  );
}
