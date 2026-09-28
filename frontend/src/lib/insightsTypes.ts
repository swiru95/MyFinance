/** LLM-insights types, kept out of lib/types.ts so feature work does not
 *  collide there. Mirrors backend/src/schemas/insight.py - see
 *  backend/src/services/{ladder,insights}.py for how each field is built.
 *  WP-L2 (frontend) was written against the WP-L1 (backend) spec while that
 *  backend work was still in progress, so shapes here are the contract, not
 *  a read of the implementation. */

export type InsightKind = "profile" | "digest" | "next_steps" | "wallet_pdf";

/** pending -> running -> translating -> done, or failed from any of them -
 *  the same job shape /reports uses (services/llm.complete underneath). */
export type InsightState =
  | "pending"
  | "running"
  | "translating"
  | "done"
  | "failed";

export interface Insight {
  id: number;
  created_at: string;
  kind: InsightKind;
  /** "2026-09" for a digest, "" for profile/next_steps. */
  period: string;
  status: InsightState;
  language: string;
  /** Markdown in `language`. */
  content: string;
  content_en: string;
  data: Record<string, unknown> | null;
  /** `data` with only its prose fields translated to Polish - set only for
   *  a "pl" profile/next_steps job, and only when the translation call
   *  succeeded; null otherwise (including every "en" job), in which case
   *  the tab falls back to `data` and shows a note. See
   *  services/insights.py:localize_data. */
  data_localized: Record<string, unknown> | null;
  snapshot: Record<string, unknown> | null;
  /** Numbers in `content` that could not be matched against `snapshot`. */
  ungrounded: string[];
  model: string;
  translator: string;
  error: string;
}

export type InsightSummary = Pick<
  Insight,
  "id" | "kind" | "period" | "status" | "created_at" | "language"
>;

export interface InsightStatus {
  configured: boolean;
  model: string;
  translator: string;
}

// ---- profile questionnaire (ProfileAnswers in the backend spec) ----

export type Goal =
  | "retire_early"
  | "buy_home"
  | "kids_education"
  | "financial_safety"
  | "travel"
  | "business";
export type Household = "single" | "couple" | "family";
export type StabilityFeel = "low" | "medium" | "high";
export type DrawdownReaction = "sell_all" | "sell_some" | "hold" | "buy_more";
export type LossTolerancePct = 5 | 10 | 20 | 30 | 50;
export type FireInterest = "none" | "curious" | "planning" | "committed";
export type Experience = "none" | "basic" | "intermediate" | "advanced";

export const GOALS: Goal[] = [
  "retire_early",
  "buy_home",
  "kids_education",
  "financial_safety",
  "travel",
  "business",
];
export const HOUSEHOLDS: Household[] = ["single", "couple", "family"];
export const STABILITY_FEELS: StabilityFeel[] = ["low", "medium", "high"];
export const DRAWDOWN_REACTIONS: DrawdownReaction[] = [
  "sell_all",
  "sell_some",
  "hold",
  "buy_more",
];
export const LOSS_TOLERANCES: LossTolerancePct[] = [5, 10, 20, 30, 50];
export const FIRE_INTERESTS: FireInterest[] = [
  "none",
  "curious",
  "planning",
  "committed",
];
export const EXPERIENCES: Experience[] = [
  "none",
  "basic",
  "intermediate",
  "advanced",
];

export interface ProfileAnswers {
  goals: Goal[];
  horizon_years: number | null;
  household: Household | null;
  dependents: number | null;
  income_stability_feel: StabilityFeel | null;
  drawdown_reaction: DrawdownReaction | null;
  loss_tolerance_pct: LossTolerancePct | null;
  fire_interest: FireInterest | null;
  experience: Experience | null;
}

/** Shown until GET /profile/answers returns something, and whenever it 404s
 *  because nobody has answered yet. */
export const EMPTY_PROFILE_ANSWERS: ProfileAnswers = {
  goals: [],
  horizon_years: null,
  household: null,
  dependents: null,
  income_stability_feel: null,
  drawdown_reaction: null,
  loss_tolerance_pct: null,
  fire_interest: null,
  experience: null,
};

export type RiskLevel = "low" | "medium" | "high";
/** Same four styles the wallet assessment (/report, ReportStyle) judges
 *  holdings against - the profile job is asked to suggest one of these. */
export type SuggestedStyle = "safe" | "balanced" | "risky" | "long_term";

/** Insight.data shape for a done "profile" job. */
export interface ProfileData {
  stated_tolerance: RiskLevel;
  capacity: RiskLevel;
  revealed: RiskLevel;
  mismatches: {
    about: string;
    stated: string;
    actual: string;
    why_it_matters: string;
  }[];
  priorities: string[];
  suggested_style: SuggestedStyle;
  summary_md: string;
}

/** Insight.data shape for a done "next_steps" job. */
export interface NextStepsData {
  steps: { key: string; title: string; why_md: string }[];
}

// ---- ladder (deterministic "next best step") ----

export type RungKey =
  | "starter_buffer"
  | "envelope_covered"
  | "emergency_fund"
  | "ppk_on"
  | "ikze_used"
  | "ike_used"
  | "fire_configured"
  | "savings_rate_on_track"
  | "data_fresh";

export type RungStatus =
  | "done"
  | "in_progress"
  | "todo"
  | "not_applicable"
  | "unknown";

export interface Rung {
  key: RungKey;
  order: number;
  status: RungStatus;
  /** A handful of keys (services/ladder.py) carry a list rather than a
   *  scalar - e.g. data_fresh's stale_assets - so this stays a union rather
   *  than narrowing to number | string. See LadderChecklist's FIGURE_KIND
   *  for how each key is rendered. */
  figures: Record<string, number | string | string[] | null>;
  /** A server-computed explanation key. Titles and one-line "why" copy are
   *  instead owned client-side in components/insights/ladderCopy.ts, keyed
   *  by (rung key, status) - see that file for why. `why_key` is kept on the
   *  type to match the API contract even though the UI does not read it. */
  why_key: string;
}

export type StepFeedbackState = "done" | "dismissed" | "later";

export interface StepFeedback {
  state: StepFeedbackState;
  at: string;
}

export interface LadderResponse {
  rungs: Rung[];
  feedback: Record<string, StepFeedback>;
}
