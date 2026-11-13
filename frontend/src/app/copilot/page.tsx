"use client";

import { useState, useRef, useEffect } from "react";
import {
  Bot,
  Send,
  User,
  Sparkles,
  FileText,
  Mail,
  Calendar,
  MessageSquare,
  RefreshCw,
  Loader2,
  CheckCircle,
  ChevronDown,
  Zap,
  AlertCircle,
} from "lucide-react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { INVESTORS, DEMO_COMPANY } from "@/lib/data/seed";
import { calculateLeadScore } from "@/lib/scoring/leadScore";
import { timeAgo, formatCurrency } from "@/lib/utils";

type Action = "research" | "outreach" | "brief" | "followup" | "questions";

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  action?: Action;
  investorId?: string;
}

const QUICK_ACTIONS = [
  {
    id: "research" as Action,
    label: "Research investor",
    icon: FileText,
    description: "Deep analysis of an investor's profile and investment patterns",
    color: "text-indigo-400",
  },
  {
    id: "outreach" as Action,
    label: "Draft outreach",
    icon: Mail,
    description: "Personalised introduction email grounded in investor intelligence",
    color: "text-emerald-400",
  },
  {
    id: "brief" as Action,
    label: "Meeting brief",
    icon: Calendar,
    description: "Investor-specific brief with talking points and questions",
    color: "text-amber-400",
  },
  {
    id: "followup" as Action,
    label: "Post-meeting follow-up",
    icon: MessageSquare,
    description: "Personalised follow-up email after investor meetings",
    color: "text-purple-400",
  },
];

// Demo responses for each action
const DEMO_RESPONSES: Record<Action, (investorId: string) => string> = {
  research: (investorId) => {
    const investor = INVESTORS.find((i) => i.id === investorId);
    if (!investor) return "Investor not found in database.";
    const score = calculateLeadScore(investor, DEMO_COMPANY);
    return `## Research: ${investor.name} · ${investor.firm}

**Lead Score: ${score.totalScore}/100** ${score.totalScore >= 75 ? "✓ High priority" : ""}

### Investment DNA
${investor.dna.behavioralSummary}

### Key patterns observed
${investor.dna.observedPatterns.map((p) => `- ${p}`).join("\n")}

### Why ${investor.firm} fits Meridian AI
${score.explanation}

### Recommended approach
${score.recommendedAction}

### Potential conversation angles
- ${investor.dna.valueAddAreas[0]}: ${investor.name} has strong operational expertise here, which aligns with Meridian AI's Series A scaling challenges
- Reference ${investor.notableInvestments[0]}: Ask about their experience scaling that company's B2B go-to-market
- Highlight NRR (142%): This directly maps to their stated interest in strong retention businesses

---
*⚠️ This research is based on synthetic demonstration data. Verify all claims before use in real investor communications.*`;
  },
  outreach: (investorId) => {
    const investor = INVESTORS.find((i) => i.id === investorId);
    if (!investor) return "Investor not found.";
    return `## Personalised outreach draft — ${investor.name} at ${investor.firm}

**Subject:** Introduction — Meridian AI · AI-powered customer success · Series A

---

Hi ${investor.name.split(" ")[0]},

[First Round Capital / Your warm intro contact] thought we should connect.

I'm the founder of Meridian AI — we build an AI-powered customer success platform that predicts churn 90 days in advance for mid-market SaaS companies. We're seeing strong early traction: $2.4M ARR, 142% NRR, 15% month-on-month growth.

I noticed ${investor.firm}'s recent focus on AI-augmented enterprise workflows — specifically your investment in ${investor.portfolio[investor.portfolio.length - 1]?.name ?? "AI SaaS companies"}. Our approach is similar in that the AI doesn't replace the customer success manager — it augments them with predictions they couldn't otherwise have.

A few data points that might be relevant:
- 48 enterprise customers including two $100K+ ARR accounts
- Average payback period: 8 months (down from 14 months last quarter)
- The AI model improves automatically with each new customer dataset

We're raising a $12M Series A and have strong interest from other tier-1 investors. I'd love 20 minutes to share our story and get your perspective.

Best,
[Founder Name]
CEO, Meridian AI

---
*⚠️ This draft uses synthetic data. Customise before sending. Never send without review.*`;
  },
  brief: (investorId) => {
    const investor = INVESTORS.find((i) => i.id === investorId);
    if (!investor) return "Investor not found.";
    return `## Investor meeting brief — ${investor.name} · ${investor.firm}

### Meeting context
${investor.isActivelyInvesting ? "✓ Actively deploying capital" : "⚠ Check fund status"}
Last active: ${investor.dna.lastActiveDate}
Typical decision timeline: ${investor.dna.decisionSpeed === "fast" ? "3–4 weeks" : investor.dna.decisionSpeed === "moderate" ? "6–8 weeks" : "10+ weeks"}

### Their investment priorities
${investor.thesisSummary}

### What they care about most
${investor.dna.observedPatterns.slice(0, 3).map((p) => `- ${p}`).join("\n")}

### Key talking points for Meridian AI
1. **AI differentiation**: Lead with the proprietary churn model trained on 48 customer datasets. This aligns with their thesis on data-moat businesses.
2. **NRR story (142%)**: This is a top metric for ${investor.firm}. Lead with this — it demonstrates product stickiness and pricing power.
3. **Series A validation**: Frame the $12M as the right amount for 24-month runway to reach $10M ARR, with Series B line of sight.

### Questions to ask them
1. "What's your thesis on AI applied to the customer success category specifically?"
2. "You backed [${investor.notableInvestments[0]}] — what GTM learnings from that company would you apply here?"
3. "What would need to be true at the end of this Series A for you to be excited about leading the B round?"

### Potential concerns to address proactively
- Market competition: Gainsight is a category leader but serves enterprise; Meridian targets mid-market with 10x better UX
- AI differentiation: The model is trained on proprietary multi-tenant data, not generic ML

---
*⚠️ Brief uses synthetic data. Verify investor's current focus areas before meeting.*`;
  },
  followup: (investorId) => {
    const investor = INVESTORS.find((i) => i.id === investorId);
    if (!investor) return "Investor not found.";
    return `## Post-meeting follow-up draft — ${investor.name}

**Subject:** Great to connect — Meridian AI follow-up

---

Hi ${investor.name.split(" ")[0]},

Thank you for the time today — genuinely valuable conversation.

As promised, a few follow-up items:

**1. The question you asked about data moat**
You asked how our churn model stays ahead of competitors who could build something similar. The key is network effects: each new customer's data improves the model for all customers. After 48 customers, our precision is demonstrably higher than a model trained on generic CRM data.

**2. The case study you asked about**
Attaching the case study from [Customer X] — 23% reduction in churn within 90 days of implementation. Happy to do a customer reference call.

**3. Next steps I suggested**
I'll send over our data room access this week. If you're aligned on the thesis, I'd suggest a partner presentation within the next two weeks — we're running a tight process.

Looking forward to continuing the conversation.

[Founder Name]
CEO, Meridian AI

---
*⚠️ Customise with actual meeting details before sending. This is a template only.*`;
  },
  questions: (investorId) => {
    return "Questions feature — use 'Meeting brief' for a comprehensive set of investor-specific questions.";
  },
};

const SYSTEM_MESSAGE: Message = {
  id: "system-1",
  role: "system",
  content: `Leadline Fundraising Copilot is active. I can help you:
- **Research** specific investors using their DNA profile and investment patterns
- **Draft personalised outreach** grounded in investor intelligence
- **Prepare meeting briefs** with talking points and investor-specific questions
- **Generate follow-up emails** after investor meetings

Select an investor and choose an action below, or type a question directly.

⚠️ All content generated uses synthetic demonstration data. Never send communications without review. Verify all claims against real sources before use.`,
  timestamp: new Date(),
};

export default function CopilotPage() {
  const [messages, setMessages] = useState<Message[]>([SYSTEM_MESSAGE]);
  const [selectedInvestorId, setSelectedInvestorId] = useState(INVESTORS[0].id);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState<Action | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const selectedInvestor = INVESTORS.find((i) => i.id === selectedInvestorId);

  const addMessage = (role: "user" | "assistant", content: string, action?: Action) => {
    setMessages((prev) => [
      ...prev,
      {
        id: Date.now().toString(),
        role,
        content,
        timestamp: new Date(),
        action,
        investorId: selectedInvestorId,
      },
    ]);
  };

  const executeAction = async (action: Action) => {
    if (!selectedInvestor) return;
    setPendingAction(action);

    const actionLabels: Record<Action, string> = {
      research: `Research ${selectedInvestor.name} at ${selectedInvestor.firm}`,
      outreach: `Draft outreach email to ${selectedInvestor.name}`,
      brief: `Prepare meeting brief for ${selectedInvestor.name}`,
      followup: `Generate post-meeting follow-up for ${selectedInvestor.name}`,
      questions: `Generate meeting questions for ${selectedInvestor.name}`,
    };

    addMessage("user", actionLabels[action], action);
    setIsLoading(true);

    // Simulate AI processing
    await new Promise((r) => setTimeout(r, 1200));

    const response = DEMO_RESPONSES[action](selectedInvestorId);
    addMessage("assistant", response, action);
    setIsLoading(false);
    setPendingAction(null);
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    const userInput = input.trim();
    setInput("");
    addMessage("user", userInput);
    setIsLoading(true);

    await new Promise((r) => setTimeout(r, 800));

    // Simple demo response
    const response = `I can help with that. For detailed investor-specific analysis, please use the quick action buttons above to research ${selectedInvestor?.name}, draft outreach, or prepare meeting materials.

For general questions about your fundraise or Leadline's features, I'm happy to assist. What would you like to know?

*Note: This Copilot runs in demo mode. Connect an OpenAI API key in .env.local for full AI capabilities.*`;

    addMessage("assistant", response);
    setIsLoading(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <AppLayout>
      <div className="mb-5">
        <h1 className="text-2xl font-bold mb-1">Copilot</h1>
        <p className="text-muted-foreground text-sm">
          AI agent that researches investors, drafts personalised outreach, and prepares meeting materials
          — all grounded in Leadline intelligence. Requires approval before any external communication.
        </p>
      </div>

      <div className="grid lg:grid-cols-4 gap-5 h-[calc(100vh-220px)] min-h-[600px]">
        {/* Sidebar */}
        <div className="space-y-4">
          {/* Investor selector */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Target investor</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <ScrollArea className="h-48">
                {INVESTORS.map((inv) => {
                  const score = calculateLeadScore(inv, DEMO_COMPANY);
                  return (
                    <button
                      key={inv.id}
                      onClick={() => setSelectedInvestorId(inv.id)}
                      className={`w-full flex items-center gap-2.5 px-4 py-3 border-b border-border/50 last:border-0 hover:bg-secondary/30 transition-colors text-left ${
                        selectedInvestorId === inv.id ? "bg-primary/10" : ""
                      }`}
                    >
                      <div className="h-7 w-7 rounded-lg bg-secondary flex items-center justify-center text-xs font-bold shrink-0">
                        {inv.name[0]}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium truncate">{inv.name}</div>
                        <div className="text-[10px] text-muted-foreground">{inv.firm}</div>
                      </div>
                      <span
                        className={`text-xs font-bold shrink-0 ${
                          score.conflictStatus === "blocking"
                            ? "text-rose-400"
                            : score.totalScore >= 70
                            ? "text-emerald-400"
                            : "text-muted-foreground"
                        }`}
                      >
                        {score.conflictStatus === "blocking" ? "⛔" : score.totalScore}
                      </span>
                    </button>
                  );
                })}
              </ScrollArea>
            </CardContent>
          </Card>

          {/* Quick actions */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Quick actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 p-3">
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action.id}
                  onClick={() => executeAction(action.id)}
                  disabled={isLoading}
                  className="w-full flex items-start gap-2.5 p-2.5 rounded-lg border border-border hover:border-primary/30 hover:bg-secondary/40 transition-all text-left disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <action.icon className={`h-4 w-4 ${action.color} shrink-0 mt-0.5`} />
                  <div>
                    <div className="text-xs font-medium">{action.label}</div>
                    <div className="text-[10px] text-muted-foreground leading-tight mt-0.5">
                      {action.description}
                    </div>
                  </div>
                </button>
              ))}
            </CardContent>
          </Card>

          {/* Agent status */}
          <Card>
            <CardContent className="pt-4 space-y-2">
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                Active agents
              </div>
              {[
                { name: "Investor Research", status: "ready" },
                { name: "Outreach Generator", status: "ready" },
                { name: "Evidence Verifier", status: "ready" },
              ].map((agent) => (
                <div key={agent.name} className="flex items-center gap-2">
                  <div
                    className={`h-1.5 w-1.5 rounded-full ${
                      agent.status === "ready" ? "bg-emerald-400" : "bg-amber-400 animate-pulse"
                    }`}
                  />
                  <span className="text-xs text-muted-foreground">{agent.name}</span>
                  <span className="text-[10px] text-emerald-400 ml-auto">
                    {agent.status}
                  </span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        {/* Chat area */}
        <div className="lg:col-span-3 flex flex-col rounded-xl border border-border bg-card overflow-hidden">
          {/* Chat header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <div className="flex items-center gap-2">
              <div className="h-7 w-7 rounded-lg bg-primary/15 border border-primary/20 flex items-center justify-center">
                <Bot className="h-4 w-4 text-primary" />
              </div>
              <div>
                <div className="text-sm font-semibold">Fundraising Copilot</div>
                <div className="text-[10px] text-muted-foreground">
                  {selectedInvestor ? `Focused on ${selectedInvestor.name} · ${selectedInvestor.firm}` : "No investor selected"}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              <span className="text-xs text-muted-foreground">Demo mode</span>
            </div>
          </div>

          {/* Messages */}
          <ScrollArea className="flex-1 p-4" ref={scrollRef}>
            <div className="space-y-4">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  {msg.role !== "user" && (
                    <div className="h-7 w-7 rounded-lg bg-primary/15 border border-primary/20 flex items-center justify-center shrink-0 mt-0.5">
                      {msg.role === "system" ? (
                        <Zap className="h-3.5 w-3.5 text-primary" />
                      ) : (
                        <Bot className="h-3.5 w-3.5 text-primary" />
                      )}
                    </div>
                  )}

                  <div
                    className={`max-w-[85%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-primary/15 border border-primary/20 text-foreground"
                        : msg.role === "system"
                        ? "bg-secondary/50 border border-border text-muted-foreground text-xs"
                        : "bg-card border border-border"
                    }`}
                  >
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                    <div className="text-[10px] text-muted-foreground mt-2 opacity-60">
                      {msg.timestamp.toLocaleTimeString()}
                    </div>
                  </div>

                  {msg.role === "user" && (
                    <div className="h-7 w-7 rounded-lg bg-secondary flex items-center justify-center shrink-0 mt-0.5">
                      <User className="h-3.5 w-3.5 text-muted-foreground" />
                    </div>
                  )}
                </div>
              ))}

              {isLoading && (
                <div className="flex gap-3">
                  <div className="h-7 w-7 rounded-lg bg-primary/15 border border-primary/20 flex items-center justify-center shrink-0">
                    <Loader2 className="h-3.5 w-3.5 text-primary animate-spin" />
                  </div>
                  <div className="bg-card border border-border rounded-xl px-4 py-3">
                    <div className="flex gap-1">
                      <div className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce [animation-delay:-0.3s]" />
                      <div className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce [animation-delay:-0.15s]" />
                      <div className="h-2 w-2 rounded-full bg-muted-foreground/40 animate-bounce" />
                    </div>
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>

          {/* Warning banner */}
          <div className="mx-4 mb-2 flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/5 border border-amber-500/20 text-xs text-amber-400">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
            All generated content requires your review before sending. Demo mode — using synthetic data only.
          </div>

          {/* Input */}
          <div className="p-4 border-t border-border">
            <div className="flex gap-2">
              <Textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`Ask about ${selectedInvestor?.name ?? "an investor"} or type a fundraising question...`}
                rows={2}
                className="resize-none text-sm"
                disabled={isLoading}
              />
              <Button
                onClick={handleSend}
                disabled={!input.trim() || isLoading}
                className="shrink-0"
                size="icon"
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
            <div className="text-[10px] text-muted-foreground mt-1.5">
              Press Enter to send · Shift+Enter for new line
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
