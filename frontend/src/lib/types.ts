/** How a holding is valued. "interest" accrues Polish statutory interest on a
 *  principal; everything else is a spot amount or a live-priced quantity. */
export type AssetKind = "currency" | "gold" | "crypto" | "interest";

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
  crypto_prices: { BTC: number; SOL: number };
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

export interface Allocation {
  base_currency: string;
  total: number;
  items: AllocationItem[];
  by_category: AllocationCategory[];
  by_profile: AllocationProfile[];
}

export interface Prices {
  base_currency: string;
  gold_per_gram: number;
  crypto: { BTC: number; SOL: number };
  fx: Record<string, number>;
}

export interface Settings {
  base_currency: string;
  allowed_currencies: string[];
  timezone: string;
  allowed_timezones: string[];
  default_timezone: string;
}

export type ExpensePeriod = "monthly" | "once";
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

export interface ExpenseSummary {
  base_currency: string;
  monthly_total: number;
  active_count: number;
  indefinite_count: number;
  upcoming: Expense[];
  ending_soon: Expense[];
  by_category: CategoryTotal[];
}

export interface MonthlyRecord {
  month: string;
  income: number;
  actual_spent: number;
  currency: string;
  notes: string;
  base_currency: string;
  income_in_base: number;
  actual_in_base: number;
  committed: number;
  surplus: number;
  savings_rate: number | null;
  variance: number;
  by_category: CategoryTotal[];
  saved: boolean;
  updated_at: string | null;
}

export interface MonthlyInput {
  income: number;
  actual_spent: number;
  currency: string;
  notes: string;
}

export interface TimelinePoint {
  month: string;
  committed: number;
  income: number | null;
  actual: number | null;
  surplus: number | null;
}

export interface MonthlyAnalytics {
  base_currency: string;
  timeline: TimelinePoint[];
  categories: string[];
  category_series: Record<string, number | string>[];
  avg_income: number | null;
  avg_actual: number | null;
  avg_savings_rate: number | null;
  months_recorded: number;
}

export const INPUT_CURRENCIES = ["PLN", "EUR", "USD", "CHF"] as const;
export const BASE_CURRENCIES = ["PLN", "EUR", "USD", "CHF"] as const;
