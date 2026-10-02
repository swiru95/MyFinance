/** How a holding is valued. "interest" accrues Polish statutory interest on a
 *  principal; everything else is a spot amount or a live-priced quantity.
 *  "gold" is the pre-existing metal kind (always XAU); "metal" generalises it
 *  to the other three precious metals (units: XAU/XAG/XPT/XPD) - see
 *  backend routes/helpers.compute_value. */
export type AssetKind = "currency" | "gold" | "metal" | "crypto" | "interest";

/** Statutory basis for kind="interest": art. 481 §2 KC (+5.5pp) or art. 359 §2 KC (+3.5pp). */
export type InterestBasis = "" | "late" | "capital";

export interface Asset {
  id: number;
  name: string;
  kind: AssetKind;
  /** User-facing class (Cash, Stocks, Retirement...). Several assets share one. */
  category: string;
  interest_basis: InterestBasis;
  /** Risk-and-liquidity band this asset counts towards. */
  profile: string;
  icon: string;
  units: string;
  created_at: string;
}

export interface Position {
  id: number;
  asset_id: number;
  amount: number;
  currency: string;
  value_in_base: number;
  price_used: number;
  base_currency: string;
  notes: string;
  /** kind="interest" only: the day the principal started accruing. */
  accrues_from: string | null;
  timestamp: string;
}

export interface Summary {
  base_currency: string;
  total_value: number;
  positions: number;
  gold_price: number;
  /** Keyed by symbol; always has BTC/SOL (backward compat) plus whatever
   *  else the wallet holds (see backend routes/helpers.held_symbols). */
  crypto_prices: Record<string, number>;
  /** Per-gram, keyed by symbol; always has XAU (backward compat) plus
   *  whatever other metals the wallet holds. */
  metals: Record<string, number>;
}

/** How the time series is split. "total" is one line; the rest are stacked. */
export type BreakdownMode = "total" | "asset" | "category" | "profile";

export interface SeriesKey {
  key: string;
  label: string;
  /** Present on the folded "__other__" series: what it absorbed. */
  members?: string[];
}

/** One day. Beyond `date` and `total`, each series key is its own field, so
 *  the row can be handed to the chart without pivoting. */
export interface ValueRow {
  date: string;
  total: number;
  [seriesKey: string]: string | number;
}

export interface ValueOverTime {
  base_currency: string;
  mode: BreakdownMode;
  keys: SeriesKey[];
  rows: ValueRow[];
}

export interface AllocationItem {
  asset_id: number;
  name: string;
  category: string;
  icon: string;
  kind: AssetKind;
  units: string;
  amount: number;
  value: number;
  percent: number;
}

export interface AllocationCategory {
  category: string;
  icon: string;
  value: number;
  percent: number;
  /** How many assets rolled up into this class. */
  assets: number;
}

export interface AllocationProfile {
  /** safe | moderate | risky | illiquid */
  profile: string;
  value: number;
  percent: number;
  /** Which asset classes rolled up into this band. */
  categories: string[];
}

export interface AllocationWrapper {
  /** ike | ikze | ppk | oipe | oki - never "", empty wrapper is left out. */
  wrapper: string;
  value: number;
  percent: number;
  assets: number;
}

export interface Allocation {
  base_currency: string;
  total: number;
  items: AllocationItem[];
  by_category: AllocationCategory[];
  by_profile: AllocationProfile[];
  /** Non-empty wrappers present, in the wrapper table's fixed order
   *  (ike, ikze, ppk, oipe, oki) - see routes/statistics.allocation. */
  by_wrapper: AllocationWrapper[];
  tax_advantaged_total: number;
  tax_advantaged_percent: number;
}

export interface Prices {
  base_currency: string;
  gold_per_gram: number;
  /** Keyed by symbol (BTC/SOL always present, plus whatever else is held). */
  crypto: Record<string, number>;
  /** Per-gram, keyed by symbol (XAU always present, plus whatever else is held). */
  metals: Record<string, number>;
  fx: Record<string, number>;
}

/** One entry of GET /api/prices/catalogue - what AssetForm offers when the
 *  user picks a precious metal or cryptocurrency to track. */
export interface CatalogueEntry {
  symbol: string;
  kind: "metal" | "crypto";
  name: { en: string; pl: string };
  icon: string;
  category: string;
  profile: string;
  unit: "g" | "coin";
}

export interface Catalogue {
  metals: CatalogueEntry[];
  crypto: CatalogueEntry[];
}

/** Advanced features, off by default for a new wallet and switchable in
 *  Settings. `fire` requires `portfolio` (see FeatureFlags on the backend) -
 *  the frontend mirrors that by turning portfolio on whenever fire is
 *  switched on, and fire off whenever portfolio is switched off. */
export interface FeatureFlags {
  portfolio: boolean;
  fire: boolean;
  tax: boolean;
  insights: boolean;
}

/** Terms-of-use acceptance state - see backend routes/settings.py. Both
 *  accepted fields are null until the wallet has accepted any version. */
export interface TermsState {
  current_version: number;
  accepted_version: number | null;
  accepted_at: string | null;
}

export interface Settings {
  base_currency: string;
  allowed_currencies: string[];
  timezone: string;
  allowed_timezones: string[];
  default_timezone: string;
  features: FeatureFlags;
  terms: TermsState;
  /** Optional, stored encrypted; only for age-based analysis. */
  birth_year: number | null;
}

/** GET /api/recovery/status - answers even when the account is locked. */
export interface RecoveryStatus {
  locked: boolean;
  configured: boolean;
  confirmed: boolean;
  created_at: string | null;
}

/** POST /api/recovery/restore. */
export interface RecoveryRestoreResult {
  restored: boolean;
  result: "recovered" | "rewrapped";
}

/** GET/POST /api/contacts[/opt-in|/opt-out]. The browser never sends an
 *  address; the server reads it from the sign-in token. */
export interface ContactState {
  opted_in: boolean;
  can_opt_in: boolean;
}

export type ExpensePeriod = "monthly" | "quarterly" | "yearly" | "once";
export type ExpenseStatus = "active" | "scheduled" | "ended";

export interface Expense {
  id: number;
  name: string;
  amount: number;
  currency: string;
  period: ExpensePeriod;
  category: string;
  starts_on: string;
  ends_on: string | null;
  notes: string;
  created_at: string;
  amount_in_base: number;
  base_currency: string;
  status: ExpenseStatus;
  is_indefinite: boolean;
  next_due: string | null;
  monthly_equivalent_in_base: number;
}

export interface ExpenseInput {
  name: string;
  amount: number;
  currency: string;
  period: ExpensePeriod;
  category: string;
  starts_on: string;
  ends_on: string | null;
  notes: string;
}

export interface CategoryTotal {
  category: string;
  total: number;
}

/** One B2B source's ZUS + health contribution this month - owed even with
 *  zero revenue, and already deducted from that source's net income (see
 *  services/business_costs.py), so it is shown separately, never folded
 *  into a typed expense. */
export interface BusinessContribution {
  source_id: number;
  name: string;
  social: number;
  health_fixed: number;
  total: number;
  currency: string;
}

export interface ExpenseSummary {
  base_currency: string;
  /** Personal typed expenses plus this month's JDG ZUS/health contributions
   *  - the runway/reserve basis. */
  monthly_total: number;
  /** Typed expenses only - what monthly_total was before contributions were
   *  added. FIRE's post-FI spend estimate reads this one. */
  monthly_total_personal: number;
  active_count: number;
  indefinite_count: number;
  upcoming: Expense[];
  ending_soon: Expense[];
  by_category: CategoryTotal[];
  business_contributions: BusinessContribution[];
  business_contributions_total: number;
}

/** One row of the "month checklist" - GET /api/monthly/{month}/commitments.
 *  `amount`/`currency` are the expense's own, not the record's. */
export interface MonthCommitment {
  expense_id: number;
  name: string;
  category: string;
  amount: number;
  currency: string;
  paid: boolean;
}

/** What PUT/PATCH send back for one checklist row - just enough to derive
 *  actual_spent server-side (see backend routes/monthly.py). */
export interface CommitmentInput {
  expense_id: number;
  amount: number;
  paid: boolean;
}

export interface MonthlyRecord {
  month: string;
  income: number;
  actual_spent: number;
  currency: string;
  notes: string;
  base_currency: string;
  /** The checklist breakdown behind actual_spent, in this record's own
   *  currency. Null/null/false on a legacy "one total" record that was
   *  never saved through the checklist - see models/monthly.py. */
  commitments_paid_total: number | null;
  other_spent: number | null;
  breakdown: boolean;
  income_in_base: number;
  /** Net income from income sources that month; income_in_base already
   *  includes it on top of the typed `income`. */
  income_from_sources_in_base: number;
  income_sources: {
    source_id: number;
    name: string;
    kind: "uop" | "b2b" | "other";
    net_in_base: number;
    overridden: boolean;
  }[];
  actual_in_base: number;
  committed: number;
  surplus: number;
  savings_rate: number | null;
  variance: number;
  /** Portfolio value at each end of the month, and what that implies was
   *  really spent. Null when there is no income or no snapshot on one end. */
  wallet_start: number | null;
  wallet_end: number | null;
  wallet_change: number | null;
  effective_spent: number | null;
  by_category: CategoryTotal[];
  saved: boolean;
  updated_at: string | null;
}

export interface MonthlyInput {
  income: number;
  actual_spent: number;
  currency: string;
  notes: string;
  commitments?: CommitmentInput[] | null;
  other_spent?: number | null;
}

/** Every field optional - PATCH /api/monthly/{month} touches only what is
 *  sent, so Expenses (the checklist/notes) and Income (income/currency) can
 *  edit the same row without overwriting each other. */
export interface MonthlyPatch {
  income?: number;
  actual_spent?: number;
  currency?: string;
  notes?: string;
  commitments?: CommitmentInput[];
  other_spent?: number;
}

export interface TimelinePoint {
  month: string;
  committed: number;
  income: number | null;
  actual: number | null;
  surplus: number | null;
  effective: number | null;
}

export interface MonthlyAnalytics {
  base_currency: string;
  timeline: TimelinePoint[];
  categories: string[];
  category_series: Record<string, number | string>[];
  avg_income: number | null;
  avg_actual: number | null;
  avg_effective: number | null;
  avg_savings_rate: number | null;
  months_recorded: number;
}

/** Wallet styles the assessment can be written against. */
export type ReportStyle = "safe" | "balanced" | "risky" | "long_term";

/** pending -> running -> translating -> done, or failed from any of them. */
export type ReportState =
  | "pending"
  | "running"
  | "translating"
  | "done"
  | "failed";

export interface Report {
  id: number;
  created_at: string;
  status: ReportState;
  style: ReportStyle;
  language: string;
  content: string;
  model: string;
  translator: string;
  error: string;
}

/** A history row: the same thing without the report text. */
export type ReportSummary = Omit<Report, "content">;

export interface ReportStatus {
  configured: boolean;
  model: string;
  translate_model: string;
  styles: ReportStyle[];
  /** True when the backend authenticates with a client certificate rather
   *  than a shared API key. */
  mtls: boolean;
  tls_verified: boolean;
}

export const REPORT_STYLES: ReportStyle[] = [
  "safe",
  "balanced",
  "risky",
  "long_term",
];

export const INPUT_CURRENCIES = ["PLN", "EUR", "USD", "CHF"] as const;
export const BASE_CURRENCIES = ["PLN", "EUR", "USD", "CHF"] as const;

/** Reporting periods the PDF report's efficiency section can be scoped to -
 *  mirrors backend/src/services/efficiency.py's PERIODS exactly (same
 *  short keys, since they round-trip through the `insights.period` column -
 *  see schemas/insight.py there). */
export type PdfReportPeriod = "1m" | "3m" | "ytd" | "12m" | "all";

export const PDF_REPORT_PERIODS: PdfReportPeriod[] = ["1m", "3m", "ytd", "12m", "all"];
