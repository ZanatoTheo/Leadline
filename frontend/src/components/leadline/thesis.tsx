"use client";

import { ArrowRight, Gauge, Rocket, Target, Users } from "lucide-react";
import type { InvestorThesis } from "@/lib/leadline/match-types";
import { fmtEur, fmtMonth } from "@/lib/leadline/format";
import { SourceLinks, TimingBadge } from "./shared";

function Box({ icon: Icon, title, children }: { icon: React.ComponentType<{ className?: string }>; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <Icon className="h-4 w-4 text-primary" /> {title}
      </h3>
      {children}
    </div>
  );
}

/** What Cala says about an investor: built without them typing anything. */
export function ThesisView({ thesis }: { thesis: InvestorThesis }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <Box icon={Target} title="What you lead">
          <p className="text-sm">
            Led <b>{thesis.roundsLed}</b> of {thesis.roundsLed + thesis.roundsJoined} rounds in 3 years (
            {Math.round(thesis.leadShare * 100)}%).
          </p>
          <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground">
            {thesis.stages.map((s) => (
              <li key={s.stage}>
                {s.stage}: {s.led} led
              </li>
            ))}
          </ul>
          {thesis.typicalLeadCheck.medianEurM != null && (
            <p className="mt-2 text-xs">
              Typical {thesis.stages[0]?.stage.toLowerCase()} lead: {fmtEur(thesis.typicalLeadCheck.minEurM)}–
              {fmtEur(thesis.typicalLeadCheck.maxEurM)} (median {fmtEur(thesis.typicalLeadCheck.medianEurM)})
            </p>
          )}
        </Box>
        <Box icon={Rocket} title="Where you invest">
          <div className="flex flex-wrap gap-1.5">
            {thesis.industries.map((i) => (
              <span key={i.industry} className="rounded-md border border-border bg-secondary px-2 py-0.5 text-xs">
                {i.industry} · {i.count}
              </span>
            ))}
          </div>
        </Box>
        <Box icon={Gauge} title="Deployment">
          <TimingBadge status={thesis.timing.status} />
          <p className="mt-2 text-sm">{thesis.timing.headline}</p>
          {thesis.timing.latestFund && (
            <div className="mt-1">
              <SourceLinks sources={thesis.timing.latestFund.sources} />
            </div>
          )}
        </Box>
      </div>

      <Box icon={Rocket} title={`Your breakouts (${thesis.breakouts.length}): companies that raised a bigger round after you came in`}>
        {thesis.breakouts.length === 0 ? (
          <p className="text-sm text-muted-foreground">No later rounds found yet for your portfolio in Cala.</p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {thesis.breakouts.map((b) => (
              <div key={b.company} className="rounded-lg border border-border px-3 py-2 text-xs">
                <div className="text-sm font-medium">{b.company}</div>
                <div className="text-muted-foreground">{b.description}</div>
                <div className="mt-1 flex flex-wrap items-center gap-1">
                  You: {b.entry.round} {fmtMonth(b.entry.announced)}
                  {b.later.map((l) => (
                    <span key={l.id} className="inline-flex items-center gap-1">
                      <ArrowRight className="h-3 w-3" /> {l.round} {fmtEur(l.amountEurM)} led by {l.leadInvestors.join(", ")}
                      <SourceLinks sources={l.sources} />
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Box>

      {thesis.coInvestors.length > 0 && (
        <Box icon={Users} title="Who joins when you lead">
          <p className="text-sm">
            {thesis.coInvestors.map((c) => `${c.name} (${c.together}×)`).join(", ")}
          </p>
        </Box>
      )}
    </div>
  );
}
