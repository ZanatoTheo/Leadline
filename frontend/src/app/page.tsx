"use client";

import Link from "next/link";
import { ArrowRight, Bell, FileSearch, Gauge, GitBranch, Handshake, ListOrdered, Mail, ShieldAlert, Target, Users, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PoweredByCala, useCalaMode } from "@/components/leadline/shared";

const STEPS = [
  {
    icon: FileSearch,
    title: "Describe your startup once",
    body: "What you do, who you sell to, your stage and raise. Thirty seconds, no deck upload.",
  },
  {
    icon: GitBranch,
    title: "Meet your funding twins",
    body: "Startups that were exactly where you are, and every round they raised since: who led it, how much, how long it took.",
  },
  {
    icon: ListOrdered,
    title: "Know who to pitch, and why",
    body: "Investors who lead rounds like yours, with a sourced brief on each: why them, why now, why you.",
  },
  {
    icon: Bell,
    title: "Hear it first",
    body: "Leadline watches Cala and alerts you when someone leads a round like yours or closes a new fund.",
  },
];

const DETAILS = [
  {
    icon: Target,
    title: "Why them",
    body: "Counts the rounds an investor led, not just joined, weighted by recency, and shows which of your twins they backed.",
  },
  {
    icon: Gauge,
    title: "Why now",
    body: "Fresh fund closes and lead pace show who is actively deploying, and who is late in an old fund.",
  },
  {
    icon: Handshake,
    title: "Why you",
    body: "Finds portfolio companies that could be your customers, so you pitch value to their portfolio, not just a request for money.",
  },
  {
    icon: Users,
    title: "Round builder",
    body: "Once a lead says yes, see who usually joins their rounds, so you can fill the rest of the round fast.",
  },
  {
    icon: ShieldAlert,
    title: "Conflict check",
    body: "Flags investors who already back a competitor, before you waste a pitch.",
  },
  {
    icon: Mail,
    title: "Outreach with proof",
    body: "Drafts that cite their twin deal, the portfolio fit and their new fund, each with a source you can check.",
  },
];

export default function LandingPage() {
  const mode = useCalaMode();
  return (
    <div className="min-h-screen bg-background text-foreground">
      <nav className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-primary shadow-sm">
              <Zap className="h-3.5 w-3.5 text-primary-foreground" />
            </div>
            <span className="text-sm font-semibold">Leadline</span>
          </Link>
          <div className="flex items-center gap-3">
            <a href="#investors" className="hidden text-sm text-muted-foreground hover:text-foreground md:inline">For investors</a>
            <a href="#pricing" className="hidden text-sm text-muted-foreground hover:text-foreground md:inline">Pricing</a>
            <Link href="/login">
              <Button size="sm" variant="ghost">Log in</Button>
            </Link>
            <Link href="/signup?role=founder">
              <Button size="sm">
                Get started <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      <section className="border-b border-border px-6 pb-16 pt-20">
        <div className="mx-auto max-w-3xl text-center">
          <h1 className="text-4xl font-bold leading-tight tracking-tight md:text-5xl">
            Follow the startups that were <span className="text-primary">exactly where you are</span>.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-muted-foreground">
            Don&apos;t guess who&apos;ll fund you. Leadline finds the startups that were exactly where you are, shows
            who backed them, and tells you which of those investors need you right now.
          </p>
          <div className="mt-8 flex justify-center gap-3">
            <Link href="/signup?role=founder">
              <Button size="lg">
                Find my funding twins <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          </div>
          <div className="mt-6 flex justify-center">
            <PoweredByCala mode={mode} />
          </div>
        </div>

        <div className="mx-auto mt-12 max-w-xl rounded-xl border border-primary/30 bg-card p-5 text-left shadow-sm">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <GitBranch className="h-3.5 w-3.5 text-primary" /> Example brief
          </div>
          <p className="text-sm">
            <span className="font-semibold">Fjord Ventures</span> led seed rounds for 2 of your twins, closed a new €60M
            fund 7 months ago, and 3 of their portfolio companies are manufacturers, your customers.
          </p>
          <div className="mt-3 flex items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground">
              <Mail className="h-3 w-3" /> Draft intro
            </span>
            <span className="text-xs text-muted-foreground">Sourced from Cala</span>
          </div>
        </div>
      </section>

      <section className="border-b border-border px-6 py-16">
        <div className="mx-auto max-w-5xl">
          <h2 className="mb-8 text-center text-2xl font-bold tracking-tight">From &quot;who funds companies like mine?&quot; to a sent email</h2>
          <div className="grid gap-4 md:grid-cols-4">
            {STEPS.map((s, i) => (
              <div key={s.title} className="rounded-xl border border-border bg-card p-5">
                <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-primary">
                  <s.icon className="h-4 w-4" /> Step {i + 1}
                </div>
                <h3 className="font-semibold">{s.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-6 py-16">
        <div className="mx-auto grid max-w-5xl gap-4 md:grid-cols-3">
          {DETAILS.map((d) => (
            <div key={d.title} className="p-2">
              <d.icon className="mb-2 h-5 w-5 text-primary" />
              <h3 className="font-semibold">{d.title}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{d.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="investors" className="border-t border-border bg-secondary/30 px-6 py-16">
        <div className="mx-auto max-w-5xl">
          <div className="mx-auto max-w-2xl text-center">
            <div className="text-xs font-semibold uppercase tracking-wide text-primary">For investors</div>
            <h2 className="mt-2 text-2xl font-bold tracking-tight">Inbound that already fits what you lead</h2>
            <p className="mt-3 text-muted-foreground">
              Pick your fund. Leadline reads your thesis from your actual rounds in Cala: what you lead, your check
              size, which companies broke out. Then it brings you founders who look like your winners, each with a
              fit score you can check line by line.
            </p>
          </div>
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {[
              { icon: Target, title: "Fit cards, not cold emails", body: "Every request arrives with sourced evidence: look-alikes in your portfolio, check-size fit, conflicts, and portfolio companies that could be their customers." },
              { icon: GitBranch, title: "Next twins", body: "Startups in Cala that look like your breakouts, flagged when they're 12+ months past their last round and likely raising soon." },
              { icon: Handshake, title: "Double opt-in, one-click pass", body: "Contacts are shared only when both sides say yes. Passing takes one click and tells the founder why, so they get feedback, not silence." },
            ].map((x) => (
              <div key={x.title} className="rounded-xl border border-border bg-card p-5">
                <x.icon className="mb-2 h-5 w-5 text-primary" />
                <h3 className="font-semibold">{x.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{x.body}</p>
              </div>
            ))}
          </div>
          <div className="mt-8 flex justify-center">
            <Link href="/signup?role=investor">
              <Button variant="outline" size="lg">
                I&apos;m an investor <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      <section id="pricing" className="border-t border-border px-6 py-16">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-center text-2xl font-bold tracking-tight">Pricing</h2>
          <div className="mt-8 grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-border bg-card p-6">
              <div className="text-sm font-semibold">Founders</div>
              <div className="mt-2 text-3xl font-bold">Free</div>
              <ul className="mt-4 space-y-1.5 text-sm text-muted-foreground">
                <li>Funding twins and raise benchmarks</li>
                <li>Investor briefs: why them, why now, why you</li>
                <li>Signals for new rounds and fund closes</li>
                <li>Intro requests with pass reasons</li>
              </ul>
            </div>
            <div className="rounded-xl border-2 border-primary bg-card p-6">
              <div className="text-sm font-semibold text-primary">Investors · Leadline Pro</div>
              <div className="mt-2 text-3xl font-bold">
                €249<span className="text-base font-normal text-muted-foreground"> / partner / month</span>
              </div>
              <ul className="mt-4 space-y-1.5 text-sm text-muted-foreground">
                <li>Pre-qualified inbound with sourced fit cards</li>
                <li>Next twins: startups like your breakouts, before they raise</li>
                <li>Invite founders directly, double opt-in</li>
                <li>Thesis kept current from Cala automatically</li>
              </ul>
            </div>
          </div>
          <p className="mt-4 text-center text-xs text-muted-foreground">
            Founders stay free so the best ones are on Leadline. Investors pay for deal flow that already fits.
          </p>
        </div>
      </section>

      <footer className="border-t border-border px-6 py-6">
        <div className="mx-auto flex max-w-5xl items-center justify-between text-xs text-muted-foreground">
          <span>Leadline · built for the Cala challenge</span>
          <PoweredByCala mode={mode} />
        </div>
      </footer>
    </div>
  );
}
