/** FIRE-specific types, kept out of lib/types.ts so feature work does not
 *  collide there. Mirrors backend/src/schemas/fire.py and the payload
 *  services/fire.py assembles - see routes/fire.py for the field-by-field
 *  rationale. */
import type { Asset, Position } from "./types";

/** "" = not in any wrapper. Four of the five (ike/ikze/ppk/oipe) are
 *  penalised before a different age (see backend services/fire.ACCESS_AGE);
 *  oki carries no age lock at all (see backend/src/tax/pl/wrappers.py). */
export type Wrapper = "" | "ike" | "ikze" | "ppk" | "oipe" | "oki";

/** Every Asset the API returns already carries `wrapper` (see AssetOut) -
 *  lib/types.ts just does not declare it, so this extends rather than
 *  redeclares. */
export type AssetWithWrapper = Asset & { wrapper: Wrapper };

/** Every Position the API returns already carries `flow_in_base`. */
export type PositionWithFlow = Position & { flow_in_base: number | null };

/** Mirrors backend/src/schemas/position.py::GrowthLast. */
export interface GrowthLast {
  change: number;
  flow: number | null;
  growth: number;
  since: string;
  at: string;
}

/** Mirrors backend/src/schemas/position.py::AssetGrowth. */
export interface AssetGrowth {
  asset_id: number;
  opening_value: number;
  contributed: number;
  untracked_updates: number;
  invested: number;
  value: number;
  growth: number;
  growth_pct: number | null;
  last: GrowthLast | null;
}

/** Mirrors backend/src/schemas/position.py::PortfolioGrowthOut. */
export interface PortfolioGrowth {
  base_currency: string;
  assets: AssetGrowth[];
  total: {
    opening_value: number;
    contributed: number;
    invested: number;
    value: number;
    growth: number;
    growth_pct: number | null;
    untracked_updates: number;
  };
}

export interface FireSettings {
  birth_year: number | null;
  target_fi_age: number | null;
  retirement_age: number;
  swr: number;
  inflation: number;
  real_return_override: number | null;
  monthly_spend_override: number | null;
  barista_income_monthly: number;
  zus_pension_monthly: number;
  include_health_cost: boolean;
  gain_share: number;
  emergency_months: number;
  lean_factor: number;
  fat_factor: number;
}

export interface FireTargets {
  regular: number;
  lean: number;
  fat: number;
  barista: number;
}

export interface FireProjectionPoint {
  year_offset: number;
  age: number;
  value: number;
  target: number;
}

export interface FireSavingsRatePoint {
  rate: number;
  years: number | null;
}

export interface FireLeverOutcome {
  years: number | null;
  fi_number: number | null;
}

export interface FireResult {
  targets_age: number;
  targets: FireTargets;
  targets_now: FireTargets;
  progress: number | null;
  coast: { number: number; reached: boolean };
  simulate: { years: number | null; fi_age: number | null };
  required: {
    contribution: number;
    savings_rate: number | null;
    required_net_income: number;
  } | null;
  current_savings_rate: number | null;
  bridge_check: {
    needed: number;
    projected_accessible: number;
    ok: boolean;
  } | null;
  savings_rate_curve: FireSavingsRatePoint[];
  levers: {
    baseline_years: number | null;
    spend_cut: FireLeverOutcome;
    income_raise: FireLeverOutcome;
  };
  projection: FireProjectionPoint[];
}

export interface FireInputs {
  current_age: number;
  retirement_age: number;
  target_fi_age: number | null;
  swr: number;
  real_return: number;
  monthly_spend: number;
  monthly_net_income: number;
  monthly_contribution: number;
  fi_assets: number;
  accessible_assets: number;
  wrapped_assets: number;
  zus_pension_monthly: number;
  barista_income_monthly: number;
  health_cost_monthly: number;
  gain_share: number;
  lean_factor: number;
  fat_factor: number;
  spend_source: "override" | "recorded" | "committed";
  contribution_source: "flows" | "recorded" | "none";
  flow_coverage: number;
  reserve: number;
  excluded_illiquid: number;
  blended_nominal: number;
  inflation: number;
  params_year: number;
}

/** Output of tax/pl/reverse.py's reverse_uop / reverse_b2b - only the fields
 *  the /fire page reads are declared; `year` carries the full forward
 *  schedule but is only used here for its effective_rate. */
export interface ReverseIncomeResult {
  gross_monthly?: number;
  revenue_monthly?: number;
  achieved_net_monthly?: number;
  achieved_take_home_monthly?: number;
  year: { effective_rate: number | null };
}

export interface RequiredIncome {
  uop: ReverseIncomeResult;
  b2b_skala: ReverseIncomeResult;
  b2b_liniowy: ReverseIncomeResult;
  b2b_ryczalt: ReverseIncomeResult;
}

export interface FireNeedsSetup {
  needs: string[];
  settings: FireSettings;
  result: null;
}

export interface FireReady {
  settings: FireSettings;
  inputs: FireInputs;
  result: FireResult;
  required_income: RequiredIncome | null;
  disclaimer_key: string;
}

export type FireResponse = FireNeedsSetup | FireReady;

export function fireNeedsSetup(data: FireResponse): data is FireNeedsSetup {
  return "needs" in data;
}
