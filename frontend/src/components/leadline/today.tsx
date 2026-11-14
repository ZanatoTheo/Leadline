"use client";

import Link from "next/link";
import { Children } from "react";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

export type Tone = "urgent" | "good" | "info" | "muted";

const TONES: Record<Tone, string> = {
  urgent: "border-l-primary",
  good: "border-l-emerald-500",
  info: "border-l-sky-500",
  muted: "border-l-border",
};

/** One line on the Today page: what happened, and the one thing to do next. */
export function ActionItem({
  icon: Icon,
  tone,
  title,
  detail,
  href,
  cta,
  badge,
}: {
  icon: React.ComponentType<{ className?: string }>;
  tone: Tone;
  title: React.ReactNode;
  detail?: React.ReactNode;
  href: string;
  cta: string;
  badge?: React.ReactNode;
}) {
  return (
    <div className={cn("flex items-center gap-4 rounded-lg border border-border border-l-4 bg-card px-4 py-3", TONES[tone])}>
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="text-sm">{title}</div>
        {detail && <div className="mt-0.5 text-xs text-muted-foreground">{detail}</div>}
      </div>
      {badge}
      <Link
        href={href}
        className="inline-flex shrink-0 items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
      >
        {cta} <ArrowRight className="h-3 w-3" />
      </Link>
    </div>
  );
}

/** A compact row of counts, e.g. sent → matched → passed. */
export function ProgressStrip({ items }: { items: { label: string; value: number | string; tone?: Tone }[] }) {
  return (
    <div className="flex flex-wrap divide-x divide-border overflow-hidden rounded-lg border border-border bg-card">
      {items.map((i) => (
        <div key={i.label} className="min-w-[110px] flex-1 px-4 py-2.5">
          <div
            className={cn(
              "text-lg font-bold tabular-nums",
              i.tone === "good" && "text-emerald-600 dark:text-emerald-400",
              i.tone === "urgent" && "text-primary",
            )}
          >
            {i.value}
          </div>
          <div className="text-xs text-muted-foreground">{i.label}</div>
        </div>
      ))}
    </div>
  );
}

export function TodayGroup({ title, children, empty }: { title: string; children: React.ReactNode; empty: string }) {
  const items = Children.toArray(children);
  return (
    <section className="space-y-2">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h2>
      {items.length ? items : <p className="text-sm text-muted-foreground">{empty}</p>}
    </section>
  );
}

export function greeting(name: string): string {
  const h = new Date().getHours();
  const part = h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  return `${part}${name ? `, ${name.split(" ")[0]}` : ""}`;
}
