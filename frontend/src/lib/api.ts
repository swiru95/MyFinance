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
  Report,
  ReportStatus,
  ReportStyle,
  ReportSummary,
  Settings,
  Summary,
  ValueOverTime,
} from "./types";

const BASE = "/api";

/** Supplies an Entra access token, or null when authentication is disabled.
 *
 *  Injected by AuthProvider rather than imported, so this module keeps no
 *  dependency on MSAL and stays usable when there is no tenant configured. */
type TokenProvider = () => Promise<string | null>;

let getToken: TokenProvider | null = null;

export function setTokenProvider(provider: TokenProvider | null): void {
  getToken = provider;
}

/** Notified when the backend rejects a token, so the app can send the user
 *  back to sign-in instead of every page rendering its own "failed to load".
 *  MSAL renews silently on its own, so reaching here means the token was
 *  refused outright - revoked, role unassigned, or the tenant reconfigured. */
let onAuthError: ((status: number) => void) | null = null;

export function setAuthErrorHandler(
  handler: ((status: number) => void) | null
): void {
  onAuthError = handler;
}

/** Raised on 401/403 so callers can tell "you are not allowed" apart from
 *  "the request failed", which read identically as a bare Error. */
export class AuthError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "AuthError";
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options?.headers as Record<string, string>) ?? {}),
  };
  if (getToken) {
    // MSAL serves this from cache until the token is close to expiring, so
    // this is not a network round trip on every call.
    const token = await getToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    if (res.status === 401 || res.status === 403) {
      onAuthError?.(res.status);
      throw new AuthError(res.status, body || res.statusText);
    }
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
  reportStatus: () => request<ReportStatus>("/reports/status"),
  reports: () => request<ReportSummary[]>("/reports"),
  report: (id: number) => request<Report>(`/reports/${id}`),
  createReport: (style: ReportStyle, language: string) =>
    request<Report>("/reports", {
      method: "POST",
      body: JSON.stringify({ style, language }),
    }),
  deleteReport: (id: number) =>
    request<void>(`/reports/${id}`, { method: "DELETE" }),
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
