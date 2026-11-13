"use client";

import { use } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle,
  AlertTriangle,
  ExternalLink,
  Info,
  TrendingUp,
  Users,
  Clock,
  MapPin,
  DollarSign,
  Activity,
  Shield,
  Sparkles,
  Network,
  ChevronRight,
  FileText,
} from "lucide-react";
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
} from "recharts";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  INVESTORS,
  DEMO_COMPANY,
  getIntroPathForInvestor,
  getSyndicateRelationships,
  getInvestorById,
} from "@/lib/data/seed";
import { calculateLeadScore } from "@/lib/scoring/leadScore";
import {
  formatStage,
  formatSector,
  formatCheckSize,
  formatCurrency,
  scoreColor,
  conflictColor,
  confidenceBadge,
  timeAgo,
} from "@/lib/utils";

function ScoreDimensionBar({
  label,
  score,
  weight,
  evidence,
  confidence,
}: {
  label: string;
  score: number;
  weight: number;
  evidence: string;
  confidence: string;
}) {
  const color =
    score >= 80 ? "bg-emerald-400" : score >= 60 ? "bg-indigo-400" : score >= 40 ? "bg-amber-400" : "bg-rose-400";
  const textColor =
    score >= 80 ? "text-emerald-400" : score >= 60 ? "text-indigo-400" : score >= 40 ? "text-amber-400" : "text-rose-400";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{label}</span>
          <span className="text-xs text-muted-foreground">
            ({Math.round(weight * 100)}% weight)
          </span>
          <span className={`evidence-badge ${confidenceBadge(confidence)}`}>
            {confidence}
          </span>
        </div>
        <span className={`text-sm font-bold tabular-nums ${textColor}`}>{score}</span>
      </div>
      <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color} transition-all duration-700`}
          style={{ width: `${score}%` }}
        />
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed">{evidence}</p>
    </div>
  );
}

export default function InvestorProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const investor = getInvestorById(id);

  if (!investor) {
    return (
      <AppLayout>
        <div className="text-center py-24 text-muted-foreground">
          Investor not found.
          <Link href="/investors" className="block mt-3 text-primary text-sm">
            ← Back to investors
          </Link>
        </div>
      </AppLayout>
    );
  }

  const score = calculateLeadScore(investor, DEMO_COMPANY);
  const introPath = getIntroPathForInvestor(investor.id);
  const syndicateRels = getSyndicateRelationships(investor.id);

  const radarData = score.dimensions.map((d) => ({
    subject: d.label.split(" ").slice(0, 2).join(" "),
    score: d.score,
    fullMark: 100,
  }));

  const scoreColor2 =
    score.totalScore >= 80
      ? "#34d399"
      : score.totalScore >= 60
      ? "#818cf8"
      : score.totalScore >= 40
      ? "#fbbf24"
      : "#fb7185";

  return (
    <AppLayout>
      {/* Back */}
      <div className="mb-5">
        <Link href="/investors">
          <Button variant="ghost" size="sm" className="gap-1.5">
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to investor discovery
          </Button>
        </Link>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-start gap-4">
          <div className="h-14 w-14 rounded-xl bg-secondary border border-border flex items-center justify-center text-xl font-bold shrink-0">
            {investor.name[0]}
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h1 className="text-2xl font-bold">{investor.name}</h1>
              {investor.isActivelyInvesting && (
                <Badge variant="success">Actively investing</Badge>
              )}
              {score.conflictStatus === "blocking" && (
                <Badge variant="destructive">Portfolio conflict</Badge>
              )}
            </div>
            <div className="text-muted-foreground text-sm mb-2">
              {investor.title} · {investor.firm}
            </div>
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <MapPin className="h-3 w-3" /> {investor.location}
              </span>
              <span className="flex items-center gap-1">
                <Activity className="h-3 w-3" /> Last active {timeAgo(investor.dna.lastActiveDate)}
              </span>
              {investor.recentActivity && (
                <span className="text-indigo-400 font-medium">{investor.recentActivity}</span>
              )}
            </div>
          </div>
        </div>

        {/* Score badge */}
        <div className="flex flex-col items-center">
          <div className="relative h-20 w-20">
            <svg width="80" height="80" className="-rotate-90 absolute inset-0">
              <circle cx="40" cy="40" r="34" fill="none" stroke="hsl(var(--border))" strokeWidth="5" />
              <circle
                cx="40"
                cy="40"
                r="34"
                fill="none"
                stroke={scoreColor2}
                strokeWidth="5"
                strokeDasharray={2 * Math.PI * 34}
                strokeDashoffset={2 * Math.PI * 34 * (1 - score.totalScore / 100)}
                strokeLinecap="round"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-2xl font-bold" style={{ color: scoreColor2 }}>
                {score.totalScore}
              </span>
              <span className="text-[9px] text-muted-foreground uppercase tracking-wide">
                Lead Score
              </span>
            </div>
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            {score.dataConfidence === "verified" ? "Verified" : "Inferred"} data
          </div>
        </div>
      </div>

      {/* Recommended action banner */}
      <div
        className={`mb-5 px-4 py-3 rounded-lg border flex items-center gap-3 ${
          score.conflictStatus === "blocking"
            ? "border-rose-500/20 bg-rose-500/5"
            : score.totalScore >= 70
            ? "border-emerald-500/20 bg-emerald-500/5"
            : "border-border bg-secondary/30"
        }`}
      >
        {score.conflictStatus === "blocking" ? (
          <AlertTriangle className="h-4 w-4 text-rose-400 shrink-0" />
        ) : score.totalScore >= 70 ? (
          <Sparkles className="h-4 w-4 text-emerald-400 shrink-0" />
        ) : (
          <Info className="h-4 w-4 text-muted-foreground shrink-0" />
        )}
        <div className="flex-1 text-sm">{score.recommendedAction}</div>
        {score.conflictStatus !== "blocking" && (
          <Link href="/copilot">
            <Button size="sm" variant="outline" className="gap-1.5 text-xs shrink-0">
              <Sparkles className="h-3 w-3" />
              Generate outreach
            </Button>
          </Link>
        )}
      </div>

      {/* Tabs */}
      <Tabs defaultValue="dna">
        <TabsList className="mb-5">
          <TabsTrigger value="dna">Investor DNA</TabsTrigger>
          <TabsTrigger value="score">Lead Score</TabsTrigger>
          <TabsTrigger value="portfolio">Portfolio</TabsTrigger>
          <TabsTrigger value="network">Network</TabsTrigger>
          <TabsTrigger value="evidence">Evidence</TabsTrigger>
        </TabsList>

        {/* DNA Tab */}
        <TabsContent value="dna">
          <div className="grid lg:grid-cols-3 gap-5">
            <div className="lg:col-span-2 space-y-5">
              {/* Bio */}
              <Card>
                <CardContent className="pt-5">
                  <p className="text-sm leading-relaxed text-muted-foreground mb-4">{investor.bio}</p>
                  <div className="border-t border-border pt-4">
                    <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                      Investment thesis
                    </div>
                    <p className="text-sm leading-relaxed">{investor.thesisSummary}</p>
                  </div>
                </CardContent>
              </Card>

              {/* Behavioural summary */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-indigo-400" />
                    Behavioural analysis
                    <Badge variant="secondary" className="text-[9px] h-4">INFERRED</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-relaxed text-muted-foreground mb-4">
                    {investor.dna.behavioralSummary}
                  </p>
                  <div className="space-y-2">
                    {investor.dna.observedPatterns.map((pattern) => (
                      <div key={pattern} className="flex items-start gap-2 text-xs text-muted-foreground">
                        <div className="h-1.5 w-1.5 rounded-full bg-indigo-400 mt-1.5 shrink-0" />
                        {pattern}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Stats column */}
            <div className="space-y-4">
              {/* Stats card */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Investment metrics</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {[
                    {
                      label: "Lead rate",
                      value: `${Math.round(investor.dna.leadRate * 100)}%`,
                      good: investor.dna.leadRate >= 0.6,
                    },
                    {
                      label: "Total deals",
                      value: investor.dna.totalDeals.toString(),
                      good: true,
                    },
                    {
                      label: "Successful exits",
                      value: investor.dna.successfulExits.toString(),
                      good: true,
                    },
                    {
                      label: "Typical check",
                      value: formatCurrency(investor.dna.avgCheckSize.typical),
                      good: true,
                    },
                    {
                      label: "Avg deal cycle",
                      value:
                        investor.dna.decisionSpeed === "fast"
                          ? "3–4 weeks"
                          : investor.dna.decisionSpeed === "moderate"
                          ? "6–8 weeks"
                          : "10–14 weeks",
                      good: investor.dna.decisionSpeed === "fast",
                    },
                    {
                      label: "Investment freq",
                      value: investor.dna.investmentFrequency,
                      good: ["active", "very-active"].includes(investor.dna.investmentFrequency),
                    },
                  ].map((item) => (
                    <div key={item.label} className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">{item.label}</span>
                      <span
                        className={`text-sm font-semibold capitalize ${
                          item.good ? "text-foreground" : "text-muted-foreground"
                        }`}
                      >
                        {item.value}
                      </span>
                    </div>
                  ))}
                </CardContent>
              </Card>

              {/* Value-add */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Value-add areas</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-1.5">
                    {investor.dna.valueAddAreas.map((area) => (
                      <Badge key={area} variant="secondary" className="text-[10px]">
                        {area}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* Fund info */}
              {investor.fund && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Fund details</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground">Fund name</span>
                      <span className="font-medium">{investor.fund.name}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground">Fund size</span>
                      <span className="font-medium">{formatCurrency(investor.fund.size)}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground">Vintage</span>
                      <span className="font-medium">{investor.fund.vintage}</span>
                    </div>
                    <div className="mt-2">
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-muted-foreground">Deployed</span>
                        <span className="font-medium">{investor.fund.deployedPercent}%</span>
                      </div>
                      <Progress
                        value={investor.fund.deployedPercent}
                        className="h-1.5"
                        indicatorClassName={
                          investor.fund.deployedPercent < 50 ? "bg-emerald-400" : "bg-amber-400"
                        }
                      />
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </TabsContent>

        {/* Score Tab */}
        <TabsContent value="score">
          <div className="grid lg:grid-cols-5 gap-5">
            <div className="lg:col-span-3 space-y-5">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    Score breakdown
                    <Badge variant="secondary" className="text-[9px] h-4">
                      {score.dataConfidence.toUpperCase()}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-5">
                  {score.dimensions.map((d) => (
                    <ScoreDimensionBar key={d.label} {...d} />
                  ))}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Score explanation</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {score.explanation}
                  </p>
                  <div className="mt-4 grid grid-cols-2 gap-4">
                    <div>
                      <div className="text-xs font-semibold text-emerald-400 mb-2 uppercase tracking-wide">
                        Strengths
                      </div>
                      {score.keyStrengths.map((s) => (
                        <div key={s} className="flex items-center gap-2 text-xs text-muted-foreground mb-1.5">
                          <CheckCircle className="h-3 w-3 text-emerald-400 shrink-0" />
                          {s}
                        </div>
                      ))}
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-rose-400 mb-2 uppercase tracking-wide">
                        Risks
                      </div>
                      {score.keyRisks.length > 0 ? (
                        score.keyRisks.map((r) => (
                          <div key={r} className="flex items-center gap-2 text-xs text-muted-foreground mb-1.5">
                            <AlertTriangle className="h-3 w-3 text-rose-400 shrink-0" />
                            {r}
                          </div>
                        ))
                      ) : (
                        <div className="text-xs text-muted-foreground">No major risks identified.</div>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Radar chart */}
            <div className="lg:col-span-2">
              <Card className="h-full">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Score dimensions</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={260}>
                    <RadarChart data={radarData}>
                      <PolarGrid stroke="hsl(var(--border))" />
                      <PolarAngleAxis
                        dataKey="subject"
                        tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                      />
                      <PolarRadiusAxis
                        angle={30}
                        domain={[0, 100]}
                        tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 9 }}
                      />
                      <Radar
                        name="Score"
                        dataKey="score"
                        stroke={scoreColor2}
                        fill={scoreColor2}
                        fillOpacity={0.15}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        {/* Portfolio Tab */}
        <TabsContent value="portfolio">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Portfolio companies</CardTitle>
              <p className="text-xs text-muted-foreground">
                Conflict score indicates category overlap with Meridian AI. Synthetic data only.
              </p>
            </CardHeader>
            <CardContent className="p-0">
              {investor.portfolio.map((company) => (
                <div
                  key={company.id}
                  className={`px-5 py-4 border-t border-border first:border-0 flex items-center gap-4 ${
                    (company.conflictScore ?? 0) >= 0.75 ? "bg-rose-500/5" : ""
                  }`}
                >
                  <div className="h-8 w-8 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold shrink-0">
                    {company.name[0]}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-sm font-medium">{company.name}</span>
                      <Badge
                        variant={company.investmentRole === "lead" ? "default" : "secondary"}
                        className="text-[9px] h-4"
                      >
                        {company.investmentRole}
                      </Badge>
                      {(company.conflictScore ?? 0) >= 0.75 && (
                        <Badge variant="destructive" className="text-[9px] h-4">
                          Direct conflict
                        </Badge>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground">{company.description}</div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-xs text-muted-foreground mb-1">
                      {formatCurrency(company.raised)} raised
                    </div>
                    {(company.conflictScore ?? 0) > 0 && (
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] text-muted-foreground">Conflict</span>
                        <div className="w-16 h-1 bg-secondary rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              (company.conflictScore ?? 0) >= 0.75
                                ? "bg-rose-400"
                                : (company.conflictScore ?? 0) >= 0.4
                                ? "bg-amber-400"
                                : "bg-indigo-400"
                            }`}
                            style={{ width: `${(company.conflictScore ?? 0) * 100}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Network Tab */}
        <TabsContent value="network">
          <div className="grid lg:grid-cols-2 gap-5">
            {/* Intro paths */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Network className="h-4 w-4 text-emerald-400" />
                  Introduction paths
                </CardTitle>
              </CardHeader>
              <CardContent>
                {introPath ? (
                  <div className="space-y-4">
                    {introPath.paths.map((path) => (
                      <div
                        key={path.connectionName}
                        className={`p-3 rounded-lg border ${
                          path.strength === "strong"
                            ? "border-emerald-500/20 bg-emerald-500/5"
                            : "border-border bg-secondary/20"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-semibold">{path.connectionName}</span>
                          <Badge
                            variant={path.strength === "strong" ? "success" : "secondary"}
                            className="text-[9px] h-4"
                          >
                            {path.strength}
                          </Badge>
                        </div>
                        <div className="text-xs text-muted-foreground">{path.connectionRole}</div>
                        <div className="mt-2 text-xs space-y-1">
                          <div>
                            <span className="text-muted-foreground">Your relationship: </span>
                            {path.relationshipToFounder}
                          </div>
                          <div>
                            <span className="text-muted-foreground">Their relationship: </span>
                            {path.relationshipToInvestor}
                          </div>
                          {path.notes && (
                            <div className="mt-2 text-indigo-400 italic">{path.notes}</div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground py-4 text-center">
                    No identified warm introduction paths. Consider cold outreach or network expansion.
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Syndicate relationships */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Users className="h-4 w-4 text-indigo-400" />
                  Co-investment relationships
                </CardTitle>
              </CardHeader>
              <CardContent>
                {syndicateRels.length > 0 ? (
                  <div className="space-y-3">
                    {syndicateRels.map((rel) => {
                      const partnerId =
                        rel.sourceId === investor.id ? rel.targetId : rel.sourceId;
                      const partner = INVESTORS.find((inv) => inv.id === partnerId);
                      if (!partner) return null;
                      return (
                        <div key={partnerId} className="flex items-center gap-3 py-2 border-b border-border last:border-0">
                          <div className="h-8 w-8 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold shrink-0">
                            {partner.name[0]}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium">{partner.name}</div>
                            <div className="text-xs text-muted-foreground">
                              {partner.firm} · {rel.coInvestments} co-investments
                            </div>
                          </div>
                          <Badge
                            variant={
                              rel.strength === "strong"
                                ? "success"
                                : rel.strength === "moderate"
                                ? "default"
                                : "secondary"
                            }
                            className="text-[9px] h-4 shrink-0"
                          >
                            {rel.strength}
                          </Badge>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground py-4 text-center">
                    No co-investment relationships identified in demo data.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Evidence Tab */}
        <TabsContent value="evidence">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-start gap-3">
                <div>
                  <CardTitle className="text-sm flex items-center gap-2 mb-1">
                    <Shield className="h-4 w-4 text-indigo-400" />
                    Evidence Radar — Source transparency
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">
                    Every claim is classified by confidence level. All data is synthetic
                    demonstration data, not verified real-world intelligence.
                  </p>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {investor.evidence.map((e) => (
                <div key={e.id} className="px-5 py-4 border-t border-border first:border-0">
                  <div className="flex items-start justify-between gap-3 mb-1.5">
                    <span className="text-sm font-medium flex-1">{e.claim}</span>
                    <span className={`evidence-badge shrink-0 ${confidenceBadge(e.confidence)}`}>
                      {e.confidence}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span>Source: {e.source}</span>
                    <span>Verified: {e.verifiedDate}</span>
                  </div>
                  {e.details && (
                    <p className="mt-1.5 text-xs text-muted-foreground leading-relaxed bg-secondary/30 rounded-lg p-2.5">
                      {e.details}
                    </p>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </AppLayout>
  );
}
