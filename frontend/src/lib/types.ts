export type AssetKind = "currency" | "gold" | "crypto";

export interface Asset {
  id: number;
  name: string;
  kind: AssetKind;
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
  timestamp: string;
}

export interface Summary {
  base_currency: string;
  total_value: number;
  positions: number;
  gold_price: number;
  crypto_prices: { BTC: number; SOL: number };
}

export interface ValuePoint {
  timestamp: string;
  total: number;
}

export interface ValueOverTime {
  base_currency: string;
  points: ValuePoint[];
}

export interface AllocationItem {
  asset_id: number;
  name: string;
  icon: string;
  kind: AssetKind;
  units: string;
  amount: number;
  value: number;
  percent: number;
}

export interface Allocation {
  base_currency: string;
  total: number;
  items: AllocationItem[];
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
