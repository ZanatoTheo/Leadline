"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ArrowLeft,
  Zap,
  Building2,
  Target,
  Users,
  CheckCircle,
  Loader2,
  Sparkles,
  TrendingUp,
  DollarSign,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";

type Step = "company" | "product" | "fundraising" | "connections" | "analysis";

const STAGES = [
  { value: "pre-seed", label: "Pre-Seed" },
  { value: "seed", label: "Seed" },
  { value: "series-a", label: "Series A" },
  { value: "series-b", label: "Series B" },
  { value: "series-c", label: "Series C" },
];

const SECTORS = [
  "AI / ML", "SaaS", "Fintech", "Healthtech", "Climate Tech",
  "Consumer", "Enterprise", "Deep Tech", "Marketplace", "Cybersecurity",
];

const ANALYSIS_STEPS = [
  { label: "Analysing company profile...", delay: 0 },
  { label: "Classifying sector and competitors...", delay: 1200 },
  { label: "Scanning investor database...", delay: 2400 },
  { label: "Computing lead probability scores...", delay: 3600 },
  { label: "Detecting portfolio conflicts...", delay: 4800 },
  { label: "Mapping introduction paths...", delay: 5600 },
  { label: "Generating company intelligence brief...", delay: 6400 },
];

function StepIndicator({ step, current }: { step: Step; current: Step }) {
  const steps: Step[] = ["company", "product", "fundraising", "connections", "analysis"];
  const labels = ["Company", "Product", "Raise", "Network", "Analysis"];
  const currentIdx = steps.indexOf(current);
  const stepIdx = steps.indexOf(step);
  const isDone = stepIdx < currentIdx;
  const isActive = stepIdx === currentIdx;

  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className={`h-8 w-8 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all ${
          isDone
            ? "bg-emerald-500/20 border-emerald-500 text-emerald-400"
            : isActive
            ? "bg-primary/20 border-primary text-primary"
            : "bg-secondary/50 border-border text-muted-foreground"
        }`}
      >
        {isDone ? <CheckCircle className="h-4 w-4" /> : stepIdx + 1}
      </div>
      <span className={`text-[10px] font-medium ${isActive ? "text-primary" : isDone ? "text-emerald-400" : "text-muted-foreground"}`}>
        {labels[stepIdx]}
      </span>
    </div>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState<Step>("company");
  const [analysisStep, setAnalysisStep] = useState(-1);
  const [form, setForm] = useState({
    companyName: "Meridian AI",
    website: "https://meridian.ai",
    location: "San Francisco, CA",
    founded: "2022",
    description:
      "AI-powered customer success platform that predicts churn 90 days in advance and recommends personalised retention playbooks for SaaS companies.",
    stage: "series-a",
    sector: "AI / ML",
    employees: "28",
    revenue: "2.4",
    growth: "180",
    targetRaise: "12",
    runway: "14",
    existingInvestors: "First Round Capital, Y Combinator",
    competitors: "Gainsight, ChurnZero, Totango",
    advisors: "Former VP Customer Success Salesforce, Ex-CTO Intercom",
    customerSegment: "Mid-market B2B SaaS companies",
    businessModel: "Annual SaaS subscription, $2.5–$15K/mo",
  });

  const updateForm = (key: string, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const startAnalysis = () => {
    setCurrentStep("analysis");
    ANALYSIS_STEPS.forEach((step, i) => {
      setTimeout(() => setAnalysisStep(i), step.delay);
    });
    setTimeout(() => {
      router.push("/dashboard");
    }, 7500);
  };

  const steps: Step[] = ["company", "product", "fundraising", "connections", "analysis"];
  const currentIdx = steps.indexOf(currentStep);
  const progress = ((currentIdx) / (steps.length - 1)) * 100;

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <div className="border-b border-border px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-7 w-7 rounded-lg bg-primary/20 border border-primary/30 flex items-center justify-center">
            <Zap className="h-3.5 w-3.5 text-primary" />
          </div>
          <span className="font-bold">Leadline</span>
        </div>
        <div className="text-sm text-muted-foreground">
          Onboarding — {Math.round(progress)}% complete
        </div>
      </div>

      {/* Progress */}
      <Progress value={progress} className="h-0.5 rounded-none" />

      {/* Steps */}
      <div className="flex justify-center gap-6 py-5 border-b border-border">
        {steps.slice(0, 4).map((s) => (
          <StepIndicator key={s} step={s} current={currentStep} />
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 flex items-start justify-center px-6 py-12">
        <div className="w-full max-w-xl">

          {/* Step 1: Company */}
          {currentStep === "company" && (
            <div className="animate-fade-in space-y-6">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Building2 className="h-5 w-5 text-primary" />
                  <h1 className="text-2xl font-bold">Tell us about your company</h1>
                </div>
                <p className="text-muted-foreground">
                  Leadline uses this to build your company intelligence profile and
                  score investor fit.
                </p>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium mb-1.5 block">Company name</label>
                  <Input
                    value={form.companyName}
                    onChange={(e) => updateForm("companyName", e.target.value)}
                    placeholder="Acme Inc."
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-sm font-medium mb-1.5 block">Website</label>
                    <Input
                      value={form.website}
                      onChange={(e) => updateForm("website", e.target.value)}
                      placeholder="https://..."
                    />
                  </div>
                  <div>
                    <label className="text-sm font-medium mb-1.5 block">Location</label>
                    <Input
                      value={form.location}
                      onChange={(e) => updateForm("location", e.target.value)}
                      placeholder="San Francisco, CA"
                    />
                  </div>
                </div>
                <div>
                  <label className="text-sm font-medium mb-1.5 block">Brief description</label>
                  <Textarea
                    value={form.description}
                    onChange={(e) => updateForm("description", e.target.value)}
                    rows={3}
                    placeholder="What does your company do?"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-sm font-medium mb-1.5 block">Founded</label>
                    <Input
                      value={form.founded}
                      onChange={(e) => updateForm("founded", e.target.value)}
                      placeholder="2022"
                    />
                  </div>
                  <div>
                    <label className="text-sm font-medium mb-1.5 block">Employees</label>
                    <Input
                      value={form.employees}
                      onChange={(e) => updateForm("employees", e.target.value)}
                      placeholder="25"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Step 2: Product */}
          {currentStep === "product" && (
            <div className="animate-fade-in space-y-6">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles className="h-5 w-5 text-primary" />
                  <h1 className="text-2xl font-bold">Product & market</h1>
                </div>
                <p className="text-muted-foreground">
                  This shapes how we classify your sector and identify portfolio conflicts.
                </p>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium mb-2 block">Sector</label>
                  <div className="flex flex-wrap gap-2">
                    {SECTORS.map((s) => (
                      <button
                        key={s}
                        onClick={() => updateForm("sector", s)}
                        className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-all ${
                          form.sector === s
                            ? "bg-primary/15 border-primary/40 text-primary"
                            : "border-border text-muted-foreground hover:border-primary/30 hover:text-foreground"
                        }`}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="text-sm font-medium mb-1.5 block">Customer segment</label>
                  <Input
                    value={form.customerSegment}
                    onChange={(e) => updateForm("customerSegment", e.target.value)}
                    placeholder="Who buys your product?"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium mb-1.5 block">
                    Known competitors{" "}
                    <span className="text-muted-foreground font-normal">(comma separated)</span>
                  </label>
                  <Input
                    value={form.competitors}
                    onChange={(e) => updateForm("competitors", e.target.value)}
                    placeholder="Competitor A, Competitor B"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium mb-1.5 block">Business model</label>
                  <Input
                    value={form.businessModel}
                    onChange={(e) => updateForm("businessModel", e.target.value)}
                    placeholder="Annual SaaS subscription..."
                  />
                </div>
              </div>
            </div>
          )}

          {/* Step 3: Fundraising */}
          {currentStep === "fundraising" && (
            <div className="animate-fade-in space-y-6">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Target className="h-5 w-5 text-primary" />
                  <h1 className="text-2xl font-bold">Fundraising requirements</h1>
                </div>
                <p className="text-muted-foreground">
                  Used to match investors by check size and filter stage compatibility.
                </p>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium mb-2 block">Funding stage</label>
                  <div className="flex flex-wrap gap-2">
                    {STAGES.map((s) => (
                      <button
                        key={s.value}
                        onClick={() => updateForm("stage", s.value)}
                        className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-all ${
                          form.stage === s.value
                            ? "bg-primary/15 border-primary/40 text-primary"
                            : "border-border text-muted-foreground hover:border-primary/30 hover:text-foreground"
                        }`}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-sm font-medium mb-1.5 block">
                      Target raise <span className="text-muted-foreground">($M)</span>
                    </label>
                    <Input
                      value={form.targetRaise}
                      onChange={(e) => updateForm("targetRaise", e.target.value)}
                      placeholder="12"
                      type="number"
                    />
                  </div>
                  <div>
                    <label className="text-sm font-medium mb-1.5 block">
                      Current ARR <span className="text-muted-foreground">($M)</span>
                    </label>
                    <Input
                      value={form.revenue}
                      onChange={(e) => updateForm("revenue", e.target.value)}
                      placeholder="2.4"
                      type="number"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-sm font-medium mb-1.5 block">
                      YoY growth <span className="text-muted-foreground">(%)</span>
                    </label>
                    <Input
                      value={form.growth}
                      onChange={(e) => updateForm("growth", e.target.value)}
                      placeholder="180"
                      type="number"
                    />
                  </div>
                  <div>
                    <label className="text-sm font-medium mb-1.5 block">
                      Runway <span className="text-muted-foreground">(months)</span>
                    </label>
                    <Input
                      value={form.runway}
                      onChange={(e) => updateForm("runway", e.target.value)}
                      placeholder="14"
                      type="number"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Step 4: Connections */}
          {currentStep === "connections" && (
            <div className="animate-fade-in space-y-6">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Users className="h-5 w-5 text-primary" />
                  <h1 className="text-2xl font-bold">Network & relationships</h1>
                </div>
                <p className="text-muted-foreground">
                  Used to discover warm introduction paths. Leadline only uses information
                  you share explicitly.
                </p>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium mb-1.5 block">
                    Existing investors{" "}
                    <span className="text-muted-foreground font-normal">(comma separated)</span>
                  </label>
                  <Input
                    value={form.existingInvestors}
                    onChange={(e) => updateForm("existingInvestors", e.target.value)}
                    placeholder="Investor A, Fund B"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium mb-1.5 block">
                    Advisors{" "}
                    <span className="text-muted-foreground font-normal">(optional)</span>
                  </label>
                  <Input
                    value={form.advisors}
                    onChange={(e) => updateForm("advisors", e.target.value)}
                    placeholder="Former CTO at X, VP Sales at Y"
                  />
                </div>

                {/* What we find */}
                <div className="rounded-lg border border-border bg-secondary/30 p-4 space-y-2">
                  <div className="text-sm font-medium mb-2 flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-primary" />
                    What Leadline will discover
                  </div>
                  {[
                    "Co-investment relationships between your existing investors and new targets",
                    "Portfolio executives who know target investors",
                    "Warm introduction paths through advisor relationships",
                    "Strength and relevance of each connection",
                  ].map((item) => (
                    <div key={item} className="flex items-start gap-2 text-xs text-muted-foreground">
                      <CheckCircle className="h-3.5 w-3.5 text-emerald-400 shrink-0 mt-0.5" />
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Step 5: Analysis */}
          {currentStep === "analysis" && (
            <div className="animate-fade-in space-y-8">
              <div className="text-center">
                <div className="h-14 w-14 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center mx-auto mb-4">
                  <Sparkles className="h-7 w-7 text-primary animate-pulse" />
                </div>
                <h1 className="text-2xl font-bold mb-2">Analysing your startup</h1>
                <p className="text-muted-foreground">
                  AI agents are building your fundraising intelligence profile.
                </p>
              </div>

              <div className="rounded-xl border border-border bg-card p-5 space-y-3">
                {ANALYSIS_STEPS.map((step, i) => (
                  <div
                    key={step.label}
                    className={`flex items-center gap-3 transition-all duration-300 ${
                      analysisStep >= i ? "opacity-100" : "opacity-0"
                    }`}
                  >
                    {analysisStep === i && analysisStep < ANALYSIS_STEPS.length - 1 ? (
                      <Loader2 className="h-4 w-4 text-primary animate-spin shrink-0" />
                    ) : analysisStep > i ? (
                      <CheckCircle className="h-4 w-4 text-emerald-400 shrink-0" />
                    ) : (
                      <div className="h-4 w-4 shrink-0" />
                    )}
                    <span className={`text-sm ${analysisStep > i ? "text-muted-foreground line-through" : "text-foreground"}`}>
                      {step.label}
                    </span>
                  </div>
                ))}
              </div>

              {analysisStep >= ANALYSIS_STEPS.length - 1 && (
                <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-5 animate-fade-in">
                  <div className="flex items-start gap-3">
                    <CheckCircle className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold text-emerald-400 mb-1">Analysis complete</div>
                      <div className="text-sm text-muted-foreground">
                        Found 10 investors. 5 high-match leads identified. 2 blocking conflicts
                        detected. 3 warm introduction paths available.
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Navigation */}
          {currentStep !== "analysis" && (
            <div className="flex items-center justify-between mt-8 pt-6 border-t border-border">
              <Button
                variant="ghost"
                onClick={() => {
                  const prev = steps[currentIdx - 1];
                  if (prev) setCurrentStep(prev);
                }}
                disabled={currentIdx === 0}
              >
                <ArrowLeft className="h-4 w-4" />
                Back
              </Button>

              {currentIdx < steps.length - 2 ? (
                <Button
                  onClick={() => {
                    const next = steps[currentIdx + 1];
                    if (next) setCurrentStep(next);
                  }}
                >
                  Continue
                  <ArrowRight className="h-4 w-4" />
                </Button>
              ) : (
                <Button onClick={startAnalysis}>
                  <Sparkles className="h-4 w-4" />
                  Run fundraising analysis
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
