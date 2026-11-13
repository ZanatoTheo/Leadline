// ============================================================
// LEADLINE – Core TypeScript Types
// All data is synthetic demonstration data unless stated.
// ============================================================

export type FundingStage =
  | "pre-seed"
  | "seed"
  | "series-a"
  | "series-b"
  | "series-c"
  | "growth";

export type Sector =
  | "ai-ml"
  | "saas"
  | "fintech"
  | "healthtech"
  | "climate"
  | "consumer"
  | "enterprise"
  | "deeptech"
  | "marketplace"
  | "cybersecurity"
  | "edtech"
  | "proptech";

export type Geography = "north-america" | "europe" | "asia" | "latam" | "global";

export type DataConfidence = "verified" | "inferred" | "unverified" | "missing";

export type InvestmentRole = "lead" | "follow" | "co-lead";

export type ConflictLevel = "none" | "low" | "medium" | "high" | "blocking";

export type AlertType =
  | "new-investor"
  | "investor-active"
  | "conflict-change"
  | "intro-opportunity"
  | "momentum-shift";

// ─── Evidence ────────────────────────────────────────────────

export interface EvidenceItem {
  id: string;
  claim: string;
  source: string;
  sourceUrl?: string;
  verifiedDate: string;
  confidence: DataConfidence;
  details?: string;
}

// ─── Investor DNA ─────────────────────────────────────────────

export interface InvestorDNA {
  leadRate: number; // 0–1, % of deals where they lead
  avgCheckSize: { min: number; max: number; typical: number }; // in $M
  avgTimeBetweenDeals: number; // months
  stagePreferences: { stage: FundingStage; weight: number }[];
  sectorPreferences: { sector: Sector; weight: number }[];
  geographyPreferences: { geography: Geography; weight: number }[];
  topCoInvestors: string[]; // investor IDs
  investmentFrequency: "very-active" | "active" | "moderate" | "selective";
  decisionSpeed: "fast" | "moderate" | "deliberate";
  valueAddAreas: string[];
  behavioralSummary: string;
  observedPatterns: string[];
  lastActiveDate: string;
  totalDeals: number;
  successfulExits: number;
}

// ─── Portfolio Company ─────────────────────────────────────────

export interface PortfolioCompany {
  id: string;
  name: string;
  sector: Sector;
  stage: FundingStage;
  description: string;
  website?: string;
  raised: number; // $M total raised
  status: "active" | "exited" | "failed";
  investmentDate: string;
  investmentRole: InvestmentRole;
  conflictScore?: number; // 0–1
}

// ─── Investor ─────────────────────────────────────────────────

export interface Investor {
  id: string;
  name: string;
  firm: string;
  firmId: string;
  title: string;
  bio: string;
  imageUrl?: string;
  linkedinUrl?: string;
  twitterUrl?: string;
  website: string;
  location: string;
  geography: Geography[];
  stages: FundingStage[];
  sectors: Sector[];
  dna: InvestorDNA;
  portfolio: PortfolioCompany[];
  evidence: EvidenceItem[];
  tags: string[];
  isActivelyInvesting: boolean;
  recentActivity?: string;
  thesisSummary: string;
  notableInvestments: string[];
  fund?: {
    name: string;
    size: number; // $M
    vintage: number;
    deployedPercent: number;
  };
}

// ─── Syndicate Relationship ────────────────────────────────────

export interface SyndicateRelationship {
  sourceId: string;
  targetId: string;
  coInvestments: number;
  lastCoInvestment: string;
  strength: "strong" | "moderate" | "weak";
  typicalRole: { source: InvestmentRole; target: InvestmentRole };
  evidence: EvidenceItem[];
}

// ─── Company (Startup) ────────────────────────────────────────

export interface Company {
  id: string;
  name: string;
  tagline: string;
  description: string;
  website?: string;
  location: string;
  sector: Sector;
  stage: FundingStage;
  founded: number;
  employees: number;
  revenue?: number; // $M ARR
  growth?: number; // % YoY
  targetRaise: number; // $M
  raised: number; // $M total raised
  runway: number; // months
  competitors: string[];
  existingInvestors: string[];
  advisors: string[];
  productDescription: string;
  customerSegment: string;
  businessModel: string;
  keyMetrics: { label: string; value: string }[];
}

// ─── Lead Score ───────────────────────────────────────────────

export interface ScoreDimension {
  label: string;
  score: number; // 0–100
  weight: number; // 0–1
  evidence: string;
  confidence: DataConfidence;
}

export interface LeadScore {
  investorId: string;
  companyId: string;
  totalScore: number; // 0–100 weighted
  matchScore: number; // 0–100 (fit)
  conflictStatus: ConflictLevel;
  activityLevel: "high" | "medium" | "low";
  dataConfidence: DataConfidence;
  dimensions: ScoreDimension[];
  explanation: string;
  keyStrengths: string[];
  keyRisks: string[];
  recommendedAction: string;
  calculatedAt: string;
}

// ─── Introduction Path ────────────────────────────────────────

export interface IntroPath {
  investorId: string;
  paths: {
    connectionName: string;
    connectionRole: string;
    relationshipToFounder: string;
    relationshipToInvestor: string;
    strength: "strong" | "moderate" | "weak";
    notes?: string;
  }[];
  bestPath?: {
    connectionName: string;
    strength: "strong" | "moderate" | "weak";
  };
}

// ─── Alert ────────────────────────────────────────────────────

export interface Alert {
  id: string;
  type: AlertType;
  title: string;
  description: string;
  investorId?: string;
  investorName?: string;
  severity: "info" | "opportunity" | "warning";
  createdAt: string;
  read: boolean;
  action?: string;
}

// ─── Fundraising Stage ────────────────────────────────────────

export type PipelineStage =
  | "target"
  | "researching"
  | "outreach-sent"
  | "intro-requested"
  | "first-meeting"
  | "follow-up"
  | "term-sheet"
  | "closed"
  | "passed";

export interface PipelineItem {
  id: string;
  investorId: string;
  investorName: string;
  firm: string;
  stage: PipelineStage;
  lastActivity: string;
  nextAction: string;
  notes: string;
  leadScore: number;
}

// ─── Simulator Config ─────────────────────────────────────────

export interface SimulatorConfig {
  targetRaise: number; // $M
  stage: FundingStage;
  sectors: Sector[];
  geographies: Geography[];
  timelineMonths: number;
  excludeConflicts: boolean;
  preferLeadInvestors: boolean;
  minCheckSize?: number;
  maxCheckSize?: number;
}

export interface SimulatorResult {
  config: SimulatorConfig;
  matchingInvestors: number;
  conflictsFound: number;
  warmIntroOpportunities: number;
  checkSizeCompatible: number;
  syndicatePotential: number;
  topInvestorIds: string[];
  tradeoffs: string[];
  recommendation: string;
}

// ─── Copilot Message ──────────────────────────────────────────

export interface CopilotMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  investorId?: string;
  action?: "research" | "outreach" | "brief" | "followup" | "questions";
}

// ─── App State ────────────────────────────────────────────────

export interface AppState {
  company: Company | null;
  onboardingComplete: boolean;
  pipeline: PipelineItem[];
  alerts: Alert[];
}
