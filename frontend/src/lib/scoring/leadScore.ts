/**
 * LEADLINE – Investor Lead Score Engine
 *
 * Deterministic scoring algorithm that evaluates the probability of an investor
 * leading a funding round for a given company. All weights are configurable.
 *
 * Score dimensions and weights:
 * 1. Historical lead rate             (0.30) – observed lead investment behaviour
 * 2. Stage compatibility              (0.25) – match between investor stage & company stage
 * 3. Sector fit                       (0.20) – alignment of investment thesis & sector
 * 4. Check-size compatibility         (0.15) – does the target raise fit their typical check?
 * 5. Geographic compatibility         (0.05) – location alignment
 * 6. Activity level                   (0.05) – recency of investment activity
 *
 * A high match score does NOT imply guaranteed fundraising success.
 * Missing data is penalised conservatively.
 */

import type { Investor, Company, LeadScore, ScoreDimension, DataConfidence } from "@/types";
import { INVESTORS, getIntroPathForInvestor } from "@/lib/data/seed";

export interface ScoringWeights {
  leadRate: number;
  stageCompatibility: number;
  sectorFit: number;
  checkSizeCompatibility: number;
  geographicCompatibility: number;
  activityLevel: number;
}

export const DEFAULT_WEIGHTS: ScoringWeights = {
  leadRate: 0.30,
  stageCompatibility: 0.25,
  sectorFit: 0.20,
  checkSizeCompatibility: 0.15,
  geographicCompatibility: 0.05,
  activityLevel: 0.05,
};

function clamp(value: number, min = 0, max = 100): number {
  return Math.max(min, Math.min(max, value));
}

function scoreLeadRate(investor: Investor): ScoreDimension {
  const rate = investor.dna.leadRate;
  const score = clamp(rate * 100);
  return {
    label: "Lead Investment Rate",
    score,
    weight: DEFAULT_WEIGHTS.leadRate,
    evidence: `${investor.name} leads ${Math.round(rate * 100)}% of their investments (${investor.dna.totalDeals} total deals analysed).`,
    confidence: "inferred",
  };
}

function scoreStageCompatibility(investor: Investor, company: Company): ScoreDimension {
  const pref = investor.dna.stagePreferences.find((p) => p.stage === company.stage);
  const score = pref ? clamp(pref.weight * 200) : 10; // penalty for no match
  const confidence: DataConfidence = pref ? "verified" : "inferred";
  return {
    label: "Stage Compatibility",
    score,
    weight: DEFAULT_WEIGHTS.stageCompatibility,
    evidence: pref
      ? `${investor.name} allocates ${Math.round(pref.weight * 100)}% of their portfolio to ${company.stage} investments.`
      : `No strong pattern of ${company.stage} investments found for ${investor.name}.`,
    confidence,
  };
}

function scoreSectorFit(investor: Investor, company: Company): ScoreDimension {
  // Check primary sector match
  const primaryPref = investor.dna.sectorPreferences.find((p) => p.sector === company.sector);

  // Check if any sector overlaps with company (AI-ML companies also relevant for SaaS investors, etc.)
  const relatedSectors: Record<string, string[]> = {
    "ai-ml": ["saas", "enterprise"],
    saas: ["ai-ml", "enterprise"],
    enterprise: ["saas", "ai-ml"],
    fintech: ["saas", "enterprise"],
    healthtech: ["saas", "ai-ml"],
  };

  const relatedPref = relatedSectors[company.sector]?.reduce((best, related) => {
    const p = investor.dna.sectorPreferences.find((pref) => pref.sector === related);
    return p && (!best || p.weight > best.weight) ? p : best;
  }, null as { sector: string; weight: number } | null);

  let score: number;
  let evidence: string;
  let confidence: DataConfidence;

  if (primaryPref && primaryPref.weight >= 0.3) {
    score = clamp(primaryPref.weight * 220);
    evidence = `${investor.name} has strong sector focus on ${company.sector} (${Math.round(primaryPref.weight * 100)}% of portfolio).`;
    confidence = "verified";
  } else if (primaryPref) {
    score = clamp(primaryPref.weight * 180);
    evidence = `${investor.name} has some exposure to ${company.sector} (${Math.round(primaryPref.weight * 100)}% of portfolio).`;
    confidence = "inferred";
  } else if (relatedPref) {
    score = clamp(relatedPref.weight * 100);
    evidence = `No direct ${company.sector} focus found, but ${investor.name} invests in related sectors.`;
    confidence = "inferred";
  } else {
    score = 15;
    evidence = `${investor.name}'s investment thesis shows limited alignment with ${company.sector}.`;
    confidence = "unverified";
  }

  return {
    label: "Sector Fit",
    score,
    weight: DEFAULT_WEIGHTS.sectorFit,
    evidence,
    confidence,
  };
}

function scoreCheckSize(investor: Investor, company: Company): ScoreDimension {
  const { min, max, typical } = investor.dna.avgCheckSize;
  const target = company.targetRaise;

  // Check if target raise fits within check size range
  // For a lead investor, typical check represents 20-40% of the round
  const leadCheckMin = target * 0.15;
  const leadCheckMax = target * 0.5;

  let score: number;
  let evidence: string;

  if (typical >= leadCheckMin && typical <= leadCheckMax) {
    // Perfect fit
    score = 90;
    evidence = `${investor.name}'s typical check ($${typical}M) aligns well with Meridian AI's $${target}M target raise.`;
  } else if (max >= leadCheckMin && min <= leadCheckMax) {
    // Partial fit
    score = 65;
    evidence = `${investor.name}'s check range ($${min}–$${max}M) partially overlaps with the implied lead check for a $${target}M round.`;
  } else if (max < leadCheckMin) {
    // Too small
    score = 25;
    evidence = `${investor.name} typically writes smaller checks ($${max}M max). The $${target}M round may require a larger lead check than their typical range.`;
  } else {
    // Too large
    score = 40;
    evidence = `${investor.name}'s minimum check ($${min}M) may be larger than optimal for a $${target}M round.`;
  }

  return {
    label: "Check-Size Compatibility",
    score,
    weight: DEFAULT_WEIGHTS.checkSizeCompatibility,
    evidence,
    confidence: "inferred",
  };
}

function scoreGeography(investor: Investor, company: Company): ScoreDimension {
  const companyGeo = company.location.toLowerCase().includes("san francisco") ||
    company.location.toLowerCase().includes("ca") ||
    company.location.toLowerCase().includes("us")
    ? "north-america"
    : "other";

  const geoMatch = investor.dna.geographyPreferences.find(
    (p) => p.geography === companyGeo || p.geography === "global"
  );

  const score = geoMatch ? clamp(geoMatch.weight * 150) : 20;

  return {
    label: "Geographic Compatibility",
    score,
    weight: DEFAULT_WEIGHTS.geographicCompatibility,
    evidence: geoMatch
      ? `${investor.name} allocates ${Math.round(geoMatch.weight * 100)}% to ${companyGeo} companies.`
      : `${investor.name} has limited investment history in ${companyGeo}.`,
    confidence: "inferred",
  };
}

function scoreActivity(investor: Investor): ScoreDimension {
  const lastActive = new Date(investor.dna.lastActiveDate);
  const monthsAgo = (Date.now() - lastActive.getTime()) / (1000 * 60 * 60 * 24 * 30);

  let activityScore: number;
  if (monthsAgo <= 1) activityScore = 95;
  else if (monthsAgo <= 3) activityScore = 80;
  else if (monthsAgo <= 6) activityScore = 60;
  else if (monthsAgo <= 12) activityScore = 40;
  else activityScore = 20;

  const freqBonus: Record<string, number> = {
    "very-active": 10,
    active: 5,
    moderate: 0,
    selective: -10,
  };

  const score = clamp(activityScore + (freqBonus[investor.dna.investmentFrequency] ?? 0));

  return {
    label: "Investment Activity",
    score,
    weight: DEFAULT_WEIGHTS.activityLevel,
    evidence: `${investor.name} was last active ${Math.round(monthsAgo)} months ago. Investment frequency: ${investor.dna.investmentFrequency}.`,
    confidence: "verified",
  };
}

function detectConflicts(investor: Investor, company: Company): {
  level: "none" | "low" | "medium" | "high" | "blocking";
  details: string;
} {
  const conflicts = investor.portfolio.filter(
    (p) => (p.conflictScore ?? 0) > 0.4
  );

  const directConflicts = investor.portfolio.filter(
    (p) => (p.conflictScore ?? 0) >= 0.75 && p.status === "active"
  );

  const knownCompetitors = company.competitors.map((c) => c.toLowerCase());
  const portfolioNames = investor.portfolio.map((p) => p.name.toLowerCase());
  const namedConflicts = knownCompetitors.filter((c) =>
    portfolioNames.some((p) => p.includes(c) || c.includes(p))
  );

  if (namedConflicts.length > 0 || directConflicts.length >= 1) {
    return {
      level: "blocking",
      details: `Direct portfolio conflict: ${[...namedConflicts, ...directConflicts.map((p) => p.name)].join(", ")}.`,
    };
  }
  if (conflicts.length >= 2) {
    return {
      level: "high",
      details: `${conflicts.length} adjacent portfolio companies with meaningful overlap.`,
    };
  }
  if (conflicts.length === 1) {
    return {
      level: "medium",
      details: `1 portfolio company with partial category overlap: ${conflicts[0].name}.`,
    };
  }
  return { level: "none", details: "No identified portfolio conflicts." };
}

export function calculateLeadScore(investor: Investor, company: Company): LeadScore {
  const dimensions: ScoreDimension[] = [
    scoreLeadRate(investor),
    scoreStageCompatibility(investor, company),
    scoreSectorFit(investor, company),
    scoreCheckSize(investor, company),
    scoreGeography(investor, company),
    scoreActivity(investor),
  ];

  // Weighted total
  const totalScore = clamp(
    Math.round(
      dimensions.reduce((sum, d) => sum + d.score * d.weight, 0)
    )
  );

  const { level: conflictStatus, details: conflictDetails } = detectConflicts(investor, company);

  // Apply conflict penalty
  const conflictPenalty: Record<string, number> = {
    none: 0,
    low: -5,
    medium: -15,
    high: -25,
    blocking: -50,
  };
  const adjustedScore = clamp(totalScore + (conflictPenalty[conflictStatus] ?? 0));

  // Activity level
  const activityLevel =
    investor.dna.investmentFrequency === "very-active" || investor.dna.investmentFrequency === "active"
      ? "high"
      : investor.dna.investmentFrequency === "moderate"
      ? "medium"
      : "low";

  // Intro path boosts
  const introPath = getIntroPathForInvestor(investor.id);
  const hasStrongIntro = introPath?.bestPath?.strength === "strong";
  const finalScore = clamp(adjustedScore + (hasStrongIntro ? 5 : 0));

  // Key strengths and risks
  const keyStrengths: string[] = [];
  const keyRisks: string[] = [];

  const topDimensions = [...dimensions].sort((a, b) => b.score - a.score);
  topDimensions.slice(0, 2).forEach((d) => {
    if (d.score >= 70) keyStrengths.push(d.label);
  });
  topDimensions.slice(-2).forEach((d) => {
    if (d.score < 50) keyRisks.push(d.label);
  });

  if (conflictStatus !== "none") keyRisks.push(`Portfolio conflict: ${conflictStatus}`);
  if (hasStrongIntro) keyStrengths.push("Warm introduction available");

  // Recommended action
  let recommendedAction: string;
  if (conflictStatus === "blocking") {
    recommendedAction = "Skip — direct portfolio conflict identified.";
  } else if (finalScore >= 80) {
    recommendedAction = hasStrongIntro
      ? "High priority. Request warm introduction immediately."
      : "High priority. Seek warm introduction through your network.";
  } else if (finalScore >= 60) {
    recommendedAction = "Strong candidate. Prepare investor brief and request introduction.";
  } else if (finalScore >= 40) {
    recommendedAction = "Moderate fit. Consider approaching after higher-scored investors.";
  } else {
    recommendedAction = "Low fit. Prioritise better-matched investors first.";
  }

  // Explanation
  const explanation = `${investor.name} at ${investor.firm} scores ${finalScore}/100 as a potential lead investor for Meridian AI's ${company.targetRaise}M Series A. ${
    dimensions[0].score >= 70 ? `Strong lead investment track record (${Math.round(investor.dna.leadRate * 100)}%). ` : ""
  }${conflictStatus !== "none" ? conflictDetails + " " : "No portfolio conflicts identified. "}${
    hasStrongIntro ? "A warm introduction path exists via First Round Capital." : ""
  }`;

  // Data confidence
  const confidences = dimensions.map((d) => d.confidence);
  const dataConfidence: DataConfidence = confidences.every((c) => c === "verified")
    ? "verified"
    : confidences.some((c) => c === "missing")
    ? "missing"
    : "inferred";

  return {
    investorId: investor.id,
    companyId: company.id,
    totalScore: finalScore,
    matchScore: adjustedScore,
    conflictStatus,
    activityLevel,
    dataConfidence,
    dimensions,
    explanation,
    keyStrengths,
    keyRisks,
    recommendedAction,
    calculatedAt: new Date().toISOString(),
  };
}

export function scoreAllInvestors(company: Company): Array<{ investor: Investor; score: LeadScore }> {
  return INVESTORS.map((investor) => ({
    investor,
    score: calculateLeadScore(investor, company),
  })).sort((a, b) => b.score.totalScore - a.score.totalScore);
}
