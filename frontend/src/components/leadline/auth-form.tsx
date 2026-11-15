"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Briefcase, Loader2, Rocket, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useLeadline } from "@/lib/leadline/store";

type Role = "founder" | "investor";
const HOME: Record<Role, string> = { founder: "/today", investor: "/investor/today" };

const ROLES: { role: Role; title: string; body: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { role: "founder", title: "I'm a founder", body: "Find who to pitch, with proof, and request intros.", icon: Rocket },
  { role: "investor", title: "I'm an investor", body: "Get founders who fit what you actually lead.", icon: Briefcase },
];

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const params = useSearchParams();
  const clear = useLeadline((s) => s.clear);
  const [role, setRole] = useState<Role>(params.get("role") === "investor" ? "investor" : "founder");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demoLogin, setDemoLogin] = useState(false);

  useEffect(() => {
    fetch("/api/auth/me")
      .then((r) => r.json())
      .then((d) => {
        setDemoLogin(!!d.demoLogin);
        // Already logged in: go straight to your side.
        if (d.user) window.location.replace(HOME[d.user.role as Role]);
      })
      .catch(() => {});
  }, []);

  const go = (r: Role) => {
    clear();
    window.location.assign(HOME[r]);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(mode === "signup" ? { role, name, email, password } : { email, password }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error ?? "Something went wrong.");
      go(d.role);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  const demo = async (r: Role) => {
    setBusy(true);
    const res = await fetch("/api/auth/demo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: r }),
    });
    if (res.ok) go(r);
    else setBusy(false);
  };

  return (
    <div className="min-h-screen bg-background">
      <nav className="border-b border-border">
        <div className="mx-auto flex h-14 max-w-md items-center px-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-primary">
              <Zap className="h-3.5 w-3.5 text-primary-foreground" />
            </div>
            <span className="text-sm font-semibold">Leadline</span>
          </Link>
        </div>
      </nav>

      <main className="mx-auto max-w-md px-6 py-10">
        <h1 className="text-2xl font-bold tracking-tight">{mode === "signup" ? "Create your account" : "Log in"}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {mode === "signup"
            ? "Founders and investors get separate workspaces. Pick yours."
            : "You'll land in your own workspace: founder or investor."}
        </p>

        <form onSubmit={submit} className="mt-6 space-y-4">
          {mode === "signup" && (
            <div className="grid grid-cols-2 gap-2">
              {ROLES.map((r) => (
                <button
                  type="button"
                  key={r.role}
                  onClick={() => setRole(r.role)}
                  className={cn(
                    "rounded-xl border p-3 text-left transition-colors",
                    role === r.role ? "border-primary bg-primary/5 ring-1 ring-primary/30" : "border-border hover:bg-secondary/40",
                  )}
                >
                  <r.icon className={cn("mb-1.5 h-4 w-4", role === r.role ? "text-primary" : "text-muted-foreground")} />
                  <div className="text-sm font-semibold">{r.title}</div>
                  <div className="text-xs text-muted-foreground">{r.body}</div>
                </button>
              ))}
            </div>
          )}

          {mode === "signup" && (
            <label className="block space-y-1.5">
              <span className="text-sm font-medium">Your name</span>
              <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required />
            </label>
          )}
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Email</span>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
          </label>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Password</span>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              minLength={mode === "signup" ? 8 : undefined}
              required
            />
          </label>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <Button type="submit" className="w-full" disabled={busy}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {mode === "signup" ? `Create ${role} account` : "Log in"}
          </Button>
        </form>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          {mode === "signup" ? (
            <>
              Already have an account?{" "}
              <Link href={`/login?role=${role}`} className="text-primary underline">
                Log in
              </Link>
            </>
          ) : (
            <>
              New here?{" "}
              <Link href={`/signup?role=${role}`} className="text-primary underline">
                Create an account
              </Link>
            </>
          )}
        </p>

        {demoLogin && (
          <div className="mt-8 rounded-xl border border-dashed border-border p-4">
            <div className="text-xs font-semibold text-muted-foreground">Demo accounts (development only)</div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <Button variant="outline" size="sm" disabled={busy} onClick={() => demo("founder")}>
                <Rocket className="h-3.5 w-3.5" /> Founder: Carbonlens
              </Button>
              <Button variant="outline" size="sm" disabled={busy} onClick={() => demo("investor")}>
                <Briefcase className="h-3.5 w-3.5" /> Investor: Sam at Bidra
              </Button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
