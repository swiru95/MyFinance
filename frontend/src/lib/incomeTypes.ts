/** Types for /api/income and /api/tax, mirrored field-for-field from
 *  backend/src/schemas/income.py, backend/src/schemas/tax.py and the plain
 *  dicts services/income.py and tax/pl/*.py hand back (those have no
 *  pydantic response_model, so FastAPI serialises the dataclass/dict as-is).
 */

export type IncomeKind = "uop" | "b2b" | "other";
export type Billing = "monthly" | "daily" | "hourly";
export type TaxForm = "skala" | "liniowy" | "ryczalt";
export type ZusStage = "start" | "preferential" | "maly_zus_plus" | "full";
export type VatMode = "standard" | "exempt" | "reverse_charge";
export type Kup = "standard" | "commuting";

// ---- tax/pl option shapes (schemas/tax.py) --------------------------------

export interface UopOptionsIn {
  kup: Kup;
  creative_share: number;
  pit2: boolean;
  young_relief: boolean;
  ppk_employee: number;
  ppk_employee_extra: number;
  ppk_employer: number;
  ppk_employer_extra: number;
  accident_rate: number;
}

export const DEFAULT_UOP_OPTIONS: UopOptionsIn = {
  kup: "standard",
  creative_share: 0,
  pit2: true,
  young_relief: false,
  ppk_employee: 0.02,
  ppk_employee_extra: 0,
  ppk_employer: 0.015,
  ppk_employer_extra: 0,
  accident_rate: 0.0167,
};

export interface B2bOptionsIn {
  tax_form: TaxForm;
  ryczalt_rate: number;
  zus_stage: ZusStage;
  custom_base: number | null;
  sickness: boolean;
  vat: VatMode;
  vat_rate: number;
  costs_vat_rate: number;
}

export const DEFAULT_B2B_OPTIONS: B2bOptionsIn = {
  tax_form: "liniowy",
  ryczalt_rate: 0.12,
  zus_stage: "full",
  custom_base: null,
  sickness: false,
  vat: "standard",
  vat_rate: 0.23,
  costs_vat_rate: 0.23,
};

// ---- income source params (schemas/income.py) ------------------------------

export interface UopIncomeParams extends UopOptionsIn {
  gross_monthly: number;
}

export interface B2bIncomeParams extends B2bOptionsIn {
  billing: Billing;
  invoice_monthly: number | null;
  rate: number | null;
  /** null = from the working-time calendar (daily -> working_days, hourly ->
   *  working_hours) for daily/hourly billing; a number is a fixed monthly
   *  count that always wins over the calendar. */
  units_per_month: number | null;
  costs_monthly: number;
}

export interface OtherIncomeParams {
  net_monthly: number;
}

export type IncomeParams = UopIncomeParams | B2bIncomeParams | OtherIncomeParams;

export interface IncomeSourceInput {
  name: string;
  kind: IncomeKind;
  currency: string;
  params: Record<string, unknown>;
  starts_on: string;
  ends_on: string | null;
  notes: string;
}

// ---- schedule breakdown rows (tax/pl/uop.py, tax/pl/b2b.py) ---------------

export interface UopMonthBreakdown {
  month: number;
  gross: number;
  pension: number;
  disability: number;
  sickness: number;
  employee_social: number;
  health: number;
  kup: number;
  pit_base: number;
  pit_advance: number;
  ppk_employee: number;
  ppk_employer: number;
  net: number;
  employer_pension: number;
  employer_disability: number;
  employer_accident: number;
  employer_fp: number;
  employer_fgsp: number;
  employer_cost: number;
  zus_capped: boolean;
  over_threshold: boolean;
}

export interface JdgSocialBreakdown {
  base: number;
  pension: number;
  disability: number;
  accident: number;
  sickness: number;
  fp: number;
  total: number;
}

export interface B2bMonthBreakdown {
  month: number;
  revenue: number;
  costs: number;
  invoice_gross: number;
  vat_output: number;
  vat_input: number;
  vat_due: number;
  social: JdgSocialBreakdown;
  social_total: number;
  income: number;
  health: number;
  pit_advance: number;
  take_home: number;
  set_aside: number;
  health_tier: number | null;
}

export type MonthBreakdown = UopMonthBreakdown | B2bMonthBreakdown;

export interface UopYearTotals extends Omit<UopMonthBreakdown, "month" | "zus_capped" | "over_threshold"> {}

export interface B2bYearTotals
  extends Omit<B2bMonthBreakdown, "month" | "health_tier"> {}

// ---- source_year (services/income.py) -------------------------------------

export type UnitsSource = "calendar" | "fixed" | "entry";

export interface SourceMonthRow {
  month: string; // YYYY-MM
  active: boolean;
  has_entry: boolean;
  amount: number;
  overridden: boolean;
  breakdown: MonthBreakdown | null;
  net_pln: number;
  net_in_base: number;
  employer_cost?: number; // uop only
  set_aside?: number; // b2b only
  vat_due?: number; // b2b only
  // Day/hour-billed b2b sources only; null for every other kind/billing.
  units: number | null;
  units_source: UnitsSource | null;
  working_days: number | null;
  working_hours: number | null;
}

/** The `dict` GET /api/income/sources/{id}/year/{year} returns, and the
 *  same shape (minus `months`) merged into IncomeSourceOut.year_summary. */
export interface SourceYear {
  source_id: number;
  name: string;
  kind: IncomeKind;
  currency: string;
  year: number;
  months: SourceMonthRow[];
  // uop
  params_year?: number;
  totals?: UopYearTotals | B2bYearTotals | { amount: number; net_pln: number; net_in_base: number };
  annual_pit?: number;
  settlement?: number;
  effective_rate?: number | null;
  pension_account_contributions?: number;
  // b2b
  tax_form?: TaxForm;
  warnings?: string[];
}

export interface IncomeSource {
  id: number;
  name: string;
  kind: IncomeKind;
  currency: string;
  params: Record<string, any>;
  starts_on: string;
  ends_on: string | null;
  notes: string;
  created_at: string;
  year_summary: Omit<SourceYear, "months">;
  current_month: SourceMonthRow | Record<string, never>;
}

export interface IncomeEntryInput {
  // Optional for a daily/hourly b2b source given `units` instead - the
  // server resolves rate x units into `amount` and freezes it there.
  amount?: number | null;
  units?: number | null;
  costs: number;
  override_net: number | null;
  notes: string;
}

export interface IncomeEntry {
  month: string;
  amount: number;
  units: number | null;
  costs: number;
  override_net: number | null;
  notes: string;
  updated_at: string;
}

// ---- /api/income/summary ---------------------------------------------------

export interface IncomeSummaryMonth {
  month: string;
  net: number;
  gross: number;
  social: number;
  health: number;
  pit: number;
  ppk: number;
  vat_due: number;
}

export interface EnvelopeComponent {
  amount_in_base: number;
  due_date: string;
  status: "outstanding" | "paid_window_passed";
}

export interface EnvelopeItem {
  source_id: number;
  name: string;
  month: string;
  zus: EnvelopeComponent;
  pit: EnvelopeComponent;
  vat: EnvelopeComponent;
}

export interface IncomeSummary {
  year: number;
  base_currency: string;
  months: IncomeSummaryMonth[];
  annual: Omit<IncomeSummaryMonth, "month">;
  envelope: EnvelopeItem[];
  envelope_outstanding_in_base: number;
}

// ---- /api/tax/params/{year} -------------------------------------------------

export interface JdgSocialForStage {
  with_sickness: JdgSocialBreakdown;
  without_sickness: JdgSocialBreakdown;
}

export interface TaxParams {
  year: number;
  minimum_wage: number;
  avg_wage_forecast: number;
  avg_wage_q4_prev: number;
  zus_annual_cap: number;
  jdg_full_base: number;
  jdg_preferential_base: number;
  health_min_base_share: number;
  linear_health_deduction_limit: number;
  ryczalt_health_tiers: [number, number, number];
  vat_exempt_limit: number;
  ike_limit: number;
  ikze_limit: number;
  ikze_limit_jdg: number;
  verified_on: string;
  sources: [string, string][];
  ryczalt_tier_thresholds: [number, number];
  young_relief_limit: number;
  pit_threshold: number;
  pit_rate_1: number;
  pit_rate_2: number;
  pit_reduction_annual: number;
  linear_rate: number;
  capital_gains_rate: number;
  vat_standard: number;
  kup_monthly: number;
  kup_monthly_commuting: number;
  kup_creative_rate: number;
  kup_creative_annual_limit: number;
  employee_pension_rate: number;
  employee_disability_rate: number;
  employee_sickness_rate: number;
  employee_health_rate: number;
  employer_pension_rate: number;
  employer_disability_rate: number;
  employer_fp_rate: number;
  employer_fgsp_rate: number;
  jdg_pension_rate: number;
  jdg_disability_rate: number;
  jdg_accident_rate: number;
  jdg_sickness_rate: number;
  jdg_fp_rate: number;
  jdg_health_skala_rate: number;
  jdg_health_liniowy_rate: number;
  params_year: number;
  health_min_monthly: number;
  voluntary_nfz_monthly: number;
  jdg_social: Record<"start" | "preferential" | "full", JdgSocialForStage>;
  disclaimer_key: string;
}

// ---- /api/tax/uop, /api/tax/b2b --------------------------------------------

export interface UopPreviewInput {
  year: number;
  gross_monthly?: number | null;
  gross_by_month?: number[] | null;
  options: UopOptionsIn;
}

export interface UopPreviewResult {
  params_year: number;
  months: UopMonthBreakdown[];
  totals: UopYearTotals;
  annual_pit: number;
  settlement: number;
  effective_rate: number | null;
  pension_account_contributions: number;
  disclaimer_key: string;
}

export interface B2bPreviewInput {
  year: number;
  revenue_monthly?: number | null;
  revenue_by_month?: number[] | null;
  costs_monthly?: number | null;
  costs_by_month?: number[] | null;
  options: B2bOptionsIn;
}

export interface B2bPreviewResult {
  params_year: number;
  tax_form: TaxForm;
  months: B2bMonthBreakdown[];
  totals: B2bYearTotals;
  effective_rate: number | null;
  pension_account_contributions: number;
  warnings: string[];
  disclaimer_key: string;
}

// ---- /api/tax/compare -------------------------------------------------------

export interface ComparePreviewInput {
  year: number;
  uop_gross_monthly: number;
  uop_options: UopOptionsIn;
  b2b_revenue_monthly: number;
  b2b_costs_monthly: number;
  b2b_options: B2bOptionsIn;
  paid_leave_days: number;
  // Omit or null -> the working-time calendar's total for `year`.
  working_days?: number | null;
  b2b_billed_per_day: boolean;
}

export interface CompareResult {
  year: number;
  uop_gross_monthly: number;
  b2b_revenue_monthly: number;
  b2b_costs_monthly: number;
  paid_leave_days: number;
  working_days: number;
  b2b_billed_per_day: boolean;
  uop_annual_net: number;
  uop_employer_cost_annual: number;
  uop_pension_account_contributions: number;
  b2b_annual_revenue: number;
  b2b_annual_take_home: number;
  b2b_pension_account_contributions: number;
  b2b_equivalent_revenue_monthly: number;
  pension_gap_annual: number;
  difference_net_annual: number;
  disclaimer_key: string;
}

// ---- /api/tax/calendar/{year} (tax/pl/calendar.py's year_calendar) ---------

export interface CalendarHoliday {
  date: string; // YYYY-MM-DD
  name: string;
}

export interface CalendarMonth {
  month: number; // 1-12
  working_days: number;
  working_hours: number;
  holidays: CalendarHoliday[];
}

export type YearCalendar = CalendarMonth[];

// ---- /api/tax/reverse --------------------------------------------------------

export interface ReverseInput {
  year: number;
  target_net_monthly: number;
  uop_options: UopOptionsIn;
  b2b_options: B2bOptionsIn;
  costs_monthly: number;
}

export interface ReverseUopResult {
  gross_monthly: number;
  achieved_net_monthly: number;
  year: Omit<UopPreviewResult, "months" | "disclaimer_key">;
}

export interface ReverseB2bResult {
  revenue_monthly: number;
  achieved_take_home_monthly: number;
  year: Omit<B2bPreviewResult, "months" | "disclaimer_key">;
}

export interface ReverseResult {
  uop: ReverseUopResult;
  b2b: Record<TaxForm, ReverseB2bResult>;
  disclaimer_key: string;
}

// ---- /api/monthly's income-source fields ------------------------------------
//
// schemas/monthly.py's MonthlyOut carries `income_from_sources_in_base` and
// `income_sources` (services/income.py's income_by_month, one row per
// contributing source), but frontend/src/lib/types.ts's MonthlyRecord
// predates them and this WP does not own that file. monthly.tsx reads these
// two fields through a cast to this extension instead of widening the
// shared type - see the WP-F1 handback note for why.

export interface MonthlyIncomeSourceRow {
  source_id: number;
  name: string;
  kind: IncomeKind;
  net_in_base: number;
  overridden: boolean;
}

