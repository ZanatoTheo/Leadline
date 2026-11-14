// Types for the two-sided part of Leadline: investor thesis, fit reports,
// founder records and double opt-in intros.

import type { Conflict, Deal, FounderProfile, Source, Synergy, Timing } from "./types";

export interface FounderRecord {
  id: string;
  profile: FounderProfile;
  founderName: string;
  email: string;
  /** Opted in to be found by investors whose thesis fits. */
  discoverable: boolean;
  updatedAt: string;
}

/** What the investor sees about a founder (no contact details until matched). */
export interface PublicFounder {
  id: string;
  profile: FounderProfile;
  founderName: string;
}

export type IntroStatus = "pending" | "accepted" | "passed";

export const PASS_REASONS = [
  "Too early for us",
  "Outside our sector focus",
  "Round size doesn't fit",
  "Portfolio conflict",
  "Not deploying right now",
  "Want to see more traction",
] as const;

export interface Intro {
  id: string;
  founderId: string;
  investor: string;
  direction: "founder-to-investor" | "investor-to-founder";
  note: string;
  status: IntroStatus;
  passReason?: string;
  createdAt: string;
  respondedAt?: string;
}

/** A portfolio company that looks like the founder, with what happened next. */
export interface PortfolioTwin {
  company: string;
  description: string;
  rounds: Deal[];
}

export interface FitReport {
  investor: string;
  score: number; // 0–100
  headline: string;
  portfolioTwins: PortfolioTwin[];
  stage: {
    ledAtStage: number;
    minEurM: number | null;
    maxEurM: number | null;
    medianEurM: number | null;
    raiseFits: boolean | null;
  };
  conflict: Conflict;
  synergies: Synergy[];
  timing: Timing;
  points: { label: string; good: boolean; detail: string; sources: Source[] }[];
}

export interface Breakout {
  company: string;
  description: string;
  entry: Deal; // the investor's first round in it
  later: Deal[]; // rounds raised after entry
}

export interface InvestorThesis {
  investor: string;
  mode: "live" | "simulated";
  roundsLed: number;
  roundsJoined: number;
  leadShare: number;
  stages: { stage: string; led: number }[];
  industries: { industry: string; count: number }[];
  typicalLeadCheck: { minEurM: number | null; maxEurM: number | null; medianEurM: number | null };
  breakouts: Breakout[];
  timing: Timing;
  coInvestors: { name: string; together: number }[];
}

export interface NextTwin {
  company: string;
  description: string;
  looksLike: string; // breakout company it resembles
  rounds: Deal[];
  lastRound: Deal;
  monthsSinceLast: number;
  raisingSoon: boolean;
  backers: string[];
}

export interface DiscoverResponse {
  mode: "live" | "simulated";
  founders: { founder: PublicFounder; fit: FitReport; intro?: Intro }[];
  nextTwins: NextTwin[];
}

/** A point for or against investing, with the evidence behind it. */
export interface DiligencePoint {
  text: string;
  sources: Source[];
}

/** Everything an investor sees on a Leadline founder's page. */
export interface StartupDiligence {
  mode: "live" | "simulated";
  founder: PublicFounder & { email?: string };
  intro: Intro | null;
  fit: FitReport;
  twins: import("./types").TwinsResponse;
  market: {
    rounds: number; // comparable rounds, last 18 months
    totalEurM: number;
    medianEurM: number | null;
    twinsFundedLast24m: number;
  };
  /** Other investors most likely to compete with you to lead this round. */
  otherLeads: { name: string; ledCount: number; lastLed: string | null }[];
  competitorRounds: Deal[];
  strengths: DiligencePoint[];
  risks: DiligencePoint[];
}

/** An investor's view of a startup found in Cala (not on Leadline). */
export interface CompanyDiligence {
  mode: "live" | "simulated";
  company: string;
  description: string;
  industry: string;
  rounds: Deal[]; // oldest first
  backers: { name: string; led: number; joined: number }[];
  monthsSinceLast: number | null;
  raisingSoon: boolean;
  youBacked: boolean;
  similar: { company: string; description: string; rounds: Deal[]; inYourPortfolio: boolean }[];
  strengths: DiligencePoint[];
  risks: DiligencePoint[];
}
