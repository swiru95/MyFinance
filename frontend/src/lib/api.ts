import type {
  BreakdownMode,
  Allocation,
  Asset,
  Expense,
  ExpenseInput,
  ExpenseSummary,
  MonthlyAnalytics,
  MonthlyInput,
  MonthlyRecord,
  Prices,
  Position,
  Settings,
  Summary,
  ValueOverTime,
} from "./types";

const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json();
}

export const api = {
  summary: () => request<Summary>("/summary"),
  assets: () => request<Asset[]>("/assets"),
  positions: () => request<Position[]>("/positions"),
  createPosition: (data: {
    asset_id: number;
    amount: number;
    currency: string;
    notes: string;
    accrues_from?: string | null;
  }) =>
    request<Position>("/positions", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updatePosition: (id: number, data: { amount: number; currency: string; notes: string }) =>
    request<Position>(`/positions/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deletePosition: (id: number) =>
    request<void>(`/positions/${id}`, { method: "DELETE" }),
  expenses: () => request<Expense[]>("/expenses"),
  expenseSummary: () => request<ExpenseSummary>("/expenses/summary"),
  createExpense: (data: ExpenseInput) =>
    request<Expense>("/expenses", { method: "POST", body: JSON.stringify(data) }),
  updateExpense: (id: number, data: ExpenseInput) =>
    request<Expense>(`/expenses/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteExpense: (id: number) =>
    request<void>(`/expenses/${id}`, { method: "DELETE" }),
  months: () => request<MonthlyRecord[]>("/monthly"),
  monthlyAnalytics: (back = 11, ahead = 12) =>
    request<MonthlyAnalytics>(
      `/monthly/analytics?months_back=${back}&months_ahead=${ahead}`
    ),
  saveMonth: (month: string, data: MonthlyInput) =>
    request<MonthlyRecord>(`/monthly/${month}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteMonth: (month: string) =>
    request<void>(`/monthly/${month}`, { method: "DELETE" }),
  valueOverTime: (by: BreakdownMode = "total") =>
    request<ValueOverTime>(`/statistics/value-over-time?by=${by}`),
  allocation: () => request<Allocation>("/statistics/allocation"),
  prices: () => request<Prices>("/prices"),
  getSettings: () => request<Settings>("/settings"),
  setSettings: (base_currency: string, timezone?: string) =>
    request<Settings>("/settings", {
      method: "PUT",
      body: JSON.stringify({ base_currency, timezone }),
    }),
};

export function fmtMoney(
  value: number,
  currency: string,
  locale = "en-US"
): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value);
}

export function fmtNum(value: number, digits = 2, locale = "en-US"): string {
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: digits,
  }).format(value);
}

/** A timestamp rendered in the configured zone, not the browser's. */
export function fmtDateTime(
  iso: string,
  locale: string,
  timeZone?: string
): string {
  return new Date(iso).toLocaleString(locale, {
    timeZone,
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/** A plain calendar date (YYYY-MM-DD), rendered without any zone shift. */
export function fmtDay(iso: string, locale: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
