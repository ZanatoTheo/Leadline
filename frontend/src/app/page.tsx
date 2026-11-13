"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowRight,
  Zap,
  TrendingUp,
  Shield,
  Share2,
  Brain,
  CheckCircle,
  Search,
  BarChart3,
  Activity,
  Briefcase,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const FOUNDER_FEATURES = [
  {
    icon: Brain,
    title: "Investor DNA",
    description:
      "Behavioural profiles built from historical investment patterns — not just stated thesis. Understand how an investor actually decides.",
  },
  {
    icon: Share2,
    title: "Syndicate Intelligence",
    description:
      "See which investors co-invest together. Know your round's likely composition before making your first call.",
  },
  {
    icon: TrendingUp,
    title: "Raise Simulator",
    description:
      "Adjust your raise parameters in real time and see how they affect your investor pool, check-size match, and introduction opportunities.",
  },
  {
    icon: Zap,
    title: "Fundraising Copilot",
    description:
      "AI that researches investors, drafts personalised outreach, and prepares meeting briefs — grounded in Leadline intelligence.",
  },
  {
    icon: Shield,
    title: "Conflict Detection",
    description:
      "Go beyond simple lists. Identify direct competitors, adjacent markets, and customer segment overlaps in every portfolio.",
  },
  {
    icon: Activity,
    title: "Evidence Radar",
    description:
      "Every recommendation is traceable. Source, confidence level, and verification date shown for every claim.",
  },
];

const MOCK_INVESTORS = [
  { name: "Lucinda Marsh", firm: "Accel",             score: 84, conflict: "none",     intro: true  },
  { name: "Priya Nair",    firm: "General Catalyst",  score: 79, conflict: "none",     intro: true  },
  { name: "Yemi Okonkwo",  firm: "Bessemer",          score: 76, conflict: "none",     intro: false },
  { name: "Marcus Webb",   firm: "Index Ventures",    score: 52, conflict: "blocking", intro: false },
];

function ScoreBar({ score }: { score: number }) {
  const color =
    score >= 80 ? "bg-emerald-500"
    : score >= 60 ? "bg-indigo-500"
    : score >= 40 ? "bg-amber-500"
    : "bg-red-500";
  const text =
    score >= 80 ? "text-emerald-600 dark:text-emerald-400"
    : score >= 60 ? "text-indigo-600 dark:text-indigo-400"
    : score >= 40 ? "text-amber-600 dark:text-amber-400"
    : "text-red-600 dark:text-red-400";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className={`text-sm font-semibold tabular-nums ${text}`}>{score}</span>
    </div>
  );
}

export default function LandingPage() {
  const [activeRow, setActiveRow] = useState(0);

  return (
    <div className="min-h-screen bg-background text-foreground">

      {/* Nav */}
      <nav className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <div className="h-6 w-6 rounded bg-primary flex items-center justify-center shadow-sm">
              <Zap className="h-3.5 w-3.5 text-primary-foreground" />
            </div>
            <span className="font-semibold text-sm">Leadline</span>
            <span className="text-[10px] text-muted-foreground border border-border rounded px-1.5 py-0.5 ml-1">
              Demo
            </span>
          </Link>
          <div className="hidden md:flex items-center gap-6 text-sm text-muted-foreground">
            <a href="#features"    className="hover:text-foreground transition-colors">Features</a>
            <a href="#how"         className="hover:text-foreground transition-colors">How it works</a>
            <a href="#preview"     className="hover:text-foreground transition-colors">Preview</a>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/dashboard">
              <Button variant="ghost" size="sm">Sign in</Button>
            </Link>
            <Link href="/onboarding">
              <Button size="sm">
                Get started <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-24 pb-16 px-6 border-b border-border">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 text-xs font-medium text-muted-foreground border border-border rounded-full px-3 py-1 mb-8 bg-card shadow-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            AI-powered fundraising intelligence
          </div>

          <h1 className="text-4xl md:text-6xl font-bold tracking-tight leading-tight mb-5">
            Don&apos;t just find investors.
            <br />
            <span className="text-primary">
              Understand and predict them.
            </span>
          </h1>

          <p className="text-lg text-muted-foreground max-w-xl mx-auto mb-10 leading-relaxed">
            Leadline answers the question every founder needs answered:{" "}
            <em className="text-foreground not-italic font-medium">
              Which investors are most likely to lead my round, and how do I reach them?
            </em>
          </p>

          {/* Two-track CTAs */}
          <div className="grid sm:grid-cols-2 gap-4 max-w-2xl mx-auto mb-10">
            <Link href="/onboarding">
              <div className="group rounded-xl border border-border bg-card p-5 text-left hover:border-primary/40 hover:shadow-md transition-all duration-200 hover:-translate-y-0.5 cursor-pointer h-full">
                <div className="flex items-center gap-3 mb-2.5">
                  <div className="h-9 w-9 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0">
                    <TrendingUp className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <div className="font-semibold text-sm">I&apos;m raising capital</div>
                    <div className="text-xs text-muted-foreground">For startup founders</div>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed mb-3">
                  Rank investors by lead probability, detect conflicts, and unlock warm introductions.
                </p>
                <div className="flex items-center gap-1 text-xs font-semibold text-primary group-hover:gap-2 transition-all">
                  Start for free <ArrowRight className="h-3.5 w-3.5" />
                </div>
              </div>
            </Link>

            <Link href="/investor-workspace">
              <div className="group rounded-xl border border-border bg-card p-5 text-left hover:border-primary/40 hover:shadow-md transition-all duration-200 hover:-translate-y-0.5 cursor-pointer h-full">
                <div className="flex items-center gap-3 mb-2.5">
                  <div className="h-9 w-9 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center shrink-0">
                    <Briefcase className="h-4 w-4 text-accent" />
                  </div>
                  <div>
                    <div className="font-semibold text-sm">I&apos;m investing</div>
                    <div className="text-xs text-muted-foreground">For venture investors</div>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed mb-3">
                  Discover high-signal deals that match your thesis before the crowd does.
                </p>
                <div className="flex items-center gap-1 text-xs font-semibold text-accent group-hover:gap-2 transition-all">
                  Explore workspace <ArrowRight className="h-3.5 w-3.5" />
                </div>
              </div>
            </Link>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-5 text-sm text-muted-foreground">
            {["Explainable recommendations", "Evidence-backed claims", "No fabricated data"].map(
              (item) => (
                <div key={item} className="flex items-center gap-1.5">
                  <CheckCircle className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                  {item}
                </div>
              )
            )}
          </div>
        </div>
      </section>

      {/* Demo preview */}
      <section id="preview" className="py-16 px-6 border-b border-border bg-secondary/20">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-8">
            <Badge variant="secondary" className="mb-3 text-xs">Founder view</Badge>
            <h2 className="text-2xl font-bold mb-2">Intelligence in action</h2>
            <p className="text-sm text-muted-foreground">
              Synthetic demonstration data — clearly labelled.
            </p>
          </div>

          <div className="rounded-xl border border-border bg-card overflow-hidden shadow-md">
            {/* Window chrome */}
            <div className="px-4 py-2.5 bg-secondary/60 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <div className="h-2.5 w-2.5 rounded-full bg-red-400" />
                <div className="h-2.5 w-2.5 rounded-full bg-amber-400" />
                <div className="h-2.5 w-2.5 rounded-full bg-green-400" />
                <span className="ml-3 text-xs text-muted-foreground">
                  Investors — Meridian AI · Series A · $12M
                </span>
              </div>
              <span className="text-xs text-muted-foreground">4 of 10</span>
            </div>

            {/* Table header */}
            <div className="px-5 py-2 bg-secondary/30 border-b border-border grid grid-cols-12 gap-4 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              <div className="col-span-3">Investor</div>
              <div className="col-span-3">Lead Score</div>
              <div className="col-span-2">Stage</div>
              <div className="col-span-2">Check</div>
              <div className="col-span-1">Conflict</div>
              <div className="col-span-1">Intro</div>
            </div>

            {/* Rows */}
            {MOCK_INVESTORS.map((inv, i) => (
              <div
                key={inv.name}
                onClick={() => setActiveRow(i)}
                className={cn(
                  "px-5 py-3.5 grid grid-cols-12 gap-4 items-center border-b border-border cursor-pointer transition-all",
                  activeRow === i
                    ? "bg-primary/5 border-l-2 border-l-primary"
                    : "hover:bg-secondary/30"
                )}
              >
                <div className="col-span-3 flex items-center gap-2.5">
                  <div className="h-7 w-7 rounded-lg bg-secondary border border-border flex items-center justify-center text-xs font-semibold shrink-0">
                    {inv.name[0]}
                  </div>
                  <div>
                    <div className="text-sm font-medium leading-tight">{inv.name}</div>
                    <div className="text-xs text-muted-foreground">{inv.firm}</div>
                  </div>
                </div>
                <div className="col-span-3"><ScoreBar score={inv.score} /></div>
                <div className="col-span-2 text-sm text-muted-foreground">Series A</div>
                <div className="col-span-2 text-sm text-muted-foreground">$8–25M</div>
                <div className="col-span-1">
                  <span className={cn("text-xs font-medium",
                    inv.conflict === "none" ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"
                  )}>
                    {inv.conflict === "none" ? "None" : "Blocking"}
                  </span>
                </div>
                <div className="col-span-1">
                  {inv.intro
                    ? <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">Warm</span>
                    : <span className="text-xs text-muted-foreground">—</span>
                  }
                </div>
              </div>
            ))}

            {/* Detail panel */}
            <div className="px-5 py-4 bg-secondary/20 border-t border-border">
              <div className="text-xs text-muted-foreground leading-relaxed max-w-2xl">
                {activeRow === 0 && "Score 84 — Accel leads 72% of their deals. Strong stage and sector fit. Warm introduction available via First Round Capital. Recommended action: request introduction this week."}
                {activeRow === 1 && "Score 79 — General Catalyst averages 3-week deal cycles. Strong AI thesis alignment. Co-lead potential with Accel. Introduction path via existing investors."}
                {activeRow === 2 && "Score 76 — Bessemer has no portfolio conflict. NRR of 142% maps directly to their cloud benchmarks. No warm introduction identified — consider cold outreach."}
                {activeRow === 3 && "Score 52 — BLOCKING CONFLICT: Index Ventures portfolio includes Totango, a direct competitor in customer success. Unlikely to participate in this round."}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-20 px-6 border-b border-border">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <Badge variant="secondary" className="mb-3 text-xs">Founder tools</Badge>
            <h2 className="text-2xl font-bold mb-3">Every tool you need for a disciplined raise</h2>
            <p className="text-muted-foreground max-w-xl mx-auto text-sm">
              Purpose-built features that give you a genuine edge — not a glorified CRM.
            </p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {FOUNDER_FEATURES.map((f) => (
              <div
                key={f.title}
                className="p-5 rounded-xl border border-border bg-card hover:border-primary/40 hover:shadow-md hover:-translate-y-0.5 transition-all duration-200"
              >
                <div className="h-9 w-9 rounded-lg bg-secondary border border-border flex items-center justify-center mb-3">
                  <f.icon className="h-4 w-4 text-primary" />
                </div>
                <h3 className="font-semibold text-sm mb-1.5">{f.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{f.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="py-20 px-6 border-b border-border bg-secondary/20">
        <div className="max-w-2xl mx-auto">
          <div className="text-center mb-12">
            <Badge variant="secondary" className="mb-3 text-xs">Founder journey</Badge>
            <h2 className="text-2xl font-bold mb-3">From zero to a prioritised investor list</h2>
          </div>
          <div className="space-y-6">
            {[
              { n: "1", title: "Describe your startup",    body: "Enter your company details, sector, stage, and fundraising requirements. Leadline builds a company intelligence profile." },
              { n: "2", title: "Get ranked investors",     body: "Every investor is scored on lead probability, stage fit, sector alignment, check size, and conflict status — with full explanations." },
              { n: "3", title: "Explore the landscape",    body: "Review investor DNA profiles, co-investment networks, and warm introduction paths across your target list." },
              { n: "4", title: "Execute with the Copilot", body: "Let the Copilot draft personalised outreach, prepare meeting briefs, and suggest follow-up actions grounded in real intelligence." },
            ].map((step, i, arr) => (
              <div key={step.n} className="flex gap-5">
                <div className="flex flex-col items-center">
                  <div className="h-9 w-9 rounded-full bg-primary/10 border-2 border-primary/30 flex items-center justify-center text-xs font-bold text-primary shrink-0">
                    {step.n}
                  </div>
                  {i < arr.length - 1 && <div className="flex-1 w-px bg-border mt-2" />}
                </div>
                <div className={cn("flex-1", i < arr.length - 1 ? "pb-6" : "")}>
                  <div className="font-semibold mb-1">{step.title}</div>
                  <p className="text-sm text-muted-foreground leading-relaxed">{step.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 px-6">
        <div className="max-w-xl mx-auto text-center">
          <h2 className="text-3xl font-bold mb-3">
            Run a smarter <span className="text-primary">fundraise.</span>
          </h2>
          <p className="text-muted-foreground mb-8">
            Stop approaching investors who will never lead your round.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link href="/onboarding">
              <Button size="lg" className="gap-2 px-7 shadow-sm">
                Start for free <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link href="/dashboard">
              <Button variant="outline" size="lg" className="gap-2 px-7">
                <BarChart3 className="h-4 w-4" /> Explore the demo
              </Button>
            </Link>
          </div>
          <p className="mt-6 text-xs text-muted-foreground">
            All data shown is synthetic demonstration data.
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border py-6 px-6">
        <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-3 text-xs text-muted-foreground">
          <Link href="/" className="flex items-center gap-2">
            <Zap className="h-3.5 w-3.5 text-primary" />
            <span className="font-medium text-foreground">Leadline</span>
            <span>· Fundraising Intelligence</span>
          </Link>
          <span>Synthetic demo data only. Not financial advice.</span>
        </div>
      </footer>
    </div>
  );
}

function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}
