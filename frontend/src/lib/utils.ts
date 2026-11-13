import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number, decimals = 0): string {
  if (amount >= 1000) return `$${(amount / 1000).toFixed(1)}B`;
  if (amount >= 1) return `$${amount.toFixed(decimals)}M`;
  return `$${(amount * 1000).toFixed(0)}K`;
}

export function formatCheckSize(min: number, max: number): string {
  return `${formatCurrency(min)} – ${formatCurrency(max)}`;
}

export function formatStage(stage: string): string {
  const map: Record<string, string> = {
    "pre-seed": "Pre-Seed",
    seed: "Seed",
    "series-a": "Series A",
    "series-b": "Series B",
    "series-c": "Series C",
    growth: "Growth",
  };
  return map[stage] ?? stage;
}

export function formatSector(sector: string): string {
  const map: Record<string, string> = {
    "ai-ml": "AI / ML",
    saas: "SaaS",
    fintech: "Fintech",
    healthtech: "Healthtech",
    climate: "Climate Tech",
    consumer: "Consumer",
    enterprise: "Enterprise",
    deeptech: "Deep Tech",
    marketplace: "Marketplace",
    cybersecurity: "Cybersecurity",
    edtech: "EdTech",
    proptech: "PropTech",
  };
  return map[sector] ?? sector;
}

export function formatGeography(geo: string): string {
  const map: Record<string, string> = {
    "north-america": "North America",
    europe: "Europe",
    asia: "Asia",
    latam: "Latin America",
    global: "Global",
  };
  return map[geo] ?? geo;
}

export function scoreColor(score: number): string {
  if (score >= 80) return "text-emerald-400";
  if (score >= 60) return "text-indigo-400";
  if (score >= 40) return "text-amber-400";
  return "text-rose-400";
}

export function scoreBg(score: number): string {
  if (score >= 80) return "bg-emerald-500/10 border-emerald-500/20";
  if (score >= 60) return "bg-indigo-500/10 border-indigo-500/20";
  if (score >= 40) return "bg-amber-500/10 border-amber-500/20";
  return "bg-rose-500/10 border-rose-500/20";
}

export function conflictColor(level: string): string {
  const map: Record<string, string> = {
    none: "text-emerald-400",
    low: "text-indigo-400",
    medium: "text-amber-400",
    high: "text-rose-400",
    blocking: "text-rose-500",
  };
  return map[level] ?? "text-muted-foreground";
}

export function confidenceBadge(confidence: string): string {
  const map: Record<string, string> = {
    verified: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    inferred: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
    unverified: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    missing: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  };
  return map[confidence] ?? "";
}

export function truncate(str: string, len: number): string {
  if (str.length <= len) return str;
  return str.slice(0, len) + "…";
}

export function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

export function getInitials(name: string): string {
  return name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
