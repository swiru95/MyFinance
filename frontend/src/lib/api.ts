import type {
  BreakdownMode,
  Allocation,
  Asset,
  Expense,
  ExpenseInput,
  ExpenseSummary,
  FeatureFlags,
  MonthCommitment,
  MonthlyAnalytics,
  MonthlyInput,
  MonthlyPatch,
  MonthlyRecord,
  PdfReportPeriod,
  Prices,
  Position,
  Report,
  ReportStatus,
  ReportStyle,
  RecoveryRestoreResult,
  RecoveryStatus,
  ReportSummary,
  ContactState,
  Settings,
  Summary,
  ValueOverTime,
} from "./types";

const BASE = "/api";

/** Supplies an Entra access token, or null when authentication is disabled.
 *
 *  Injected by AuthProvider rather than imported, so this module keeps no
 *  dependency on MSAL and stays usable when there is no tenant configured. */
type TokenProvider = (forceRefresh?: boolean) => Promise<string | null>;

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

/** Raised on 423 + `X-MyFinance-Locked: recovery`: the account exists but
 *  this sign-in cannot unlock its data. Deliberately NOT an AuthError - the
 *  token is fine, so it must not send the user back to sign-in, and callers
 *  must not show it as a generic "failed to load". LockedGate shows the
 *  recovery screen instead. */
export class LockedError extends Error {
  readonly status = 423;
  constructor(message: string) {
    super(message);
    this.name = "LockedError";
  }
}

/** Notified on any 423, so LockedGate can switch to the recovery screen even
 *  when the lock only becomes visible after its initial status check. */
let onLocked: (() => void) | null = null;

export function setLockedHandler(handler: (() => void) | null): void {
  onLocked = handler;
}

/** A non-2xx answer that is not an auth/lock error. Carries the same
 *  "API <status>: <body>" message the plain Error used to, so callers that
 *  show err.message are unaffected; recovery callers branch on `status`. */
export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** 429 with the server's Retry-After (seconds; null if absent/unparseable). */
export class RateLimitError extends ApiError {
  readonly retryAfter: number | null;
  constructor(message: string, retryAfter: number | null) {
    super(429, message);
    this.name = "RateLimitError";
    this.retryAfter = retryAfter;
  }
}

/** Shared by request() and requestBlob(): attaches the bearer token (with a
 *  one-shot silent-refresh retry on a 401), and turns a non-2xx response
 *  into the same AuthError/Error split every caller already handles. Kept
 *  as one function so a PDF download (which needs the raw bytes, not
 *  res.json()) never has to reimplement the auth dance. */
async function fetchWithAuth(path: string, options?: RequestInit): Promise<Response> {
  const headers: Record<string, string> = {
    ...((options?.headers as Record<string, string>) ?? {}),
  };
  if (getToken) {
    // MSAL serves this from cache until the token is close to expiring, so
    // this is not a network round trip on every call.
    const token = await getToken();
    if (!token) {
      // setTokenProvider is only ever wired up once auth is enabled (see
      // AuthProvider), so a null token here does not mean "no auth
      // required" - acquireTokenSilent could not produce one, which means
      // either the account has not loaded yet or Entra genuinely needs
      // interaction and getAccessToken() has already kicked off a redirect.
      // Sending the request anyway would just hand the backend a bearer-less
      // call it is guaranteed to 401 and race the in-flight redirect with a
      // real round trip. Fail the same way locally, without the network hop.
      onAuthError?.(401);
      throw new AuthError(401, "No access token available");
    }
    headers.Authorization = `Bearer ${token}`;
  }
  let res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (res.status === 401 && getToken) {
    // A token that expired between MSAL's cache check and the backend's check
    // should not cost the user their session.
    const newToken = await getToken(true);
    if (newToken) {
      headers.Authorization = `Bearer ${newToken}`;
      res = await fetch(`${BASE}${path}`, { ...options, headers });
    }
  }
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    if (res.status === 401 || res.status === 403) {
      onAuthError?.(res.status);
      throw new AuthError(res.status, body || res.statusText);
    }
    if (res.status === 423) {
      onLocked?.();
      throw new LockedError(body || res.statusText);
    }
    const message = `API ${res.status}: ${body || res.statusText}`;
    if (res.status === 429) {
      const raw = Number.parseInt(res.headers.get("Retry-After") ?? "", 10);
      throw new RateLimitError(message, Number.isFinite(raw) && raw > 0 ? raw : null);
    }
    throw new ApiError(res.status, message);
  }
  return res;
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetchWithAuth(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...((options?.headers as Record<string, string>) ?? {}) },
  });
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json();
}

/** Same auth handling as request(), but returns the raw body - for the PDF
 *  report download (application/pdf), which res.json() cannot parse. */
export async function requestBlob(path: string): Promise<Blob> {
  const res = await fetchWithAuth(path);
  return res.blob();
}

/** Triggers a browser "Save As" for `blob` named `filename`, the same way a
 *  plain `<a href download>` would for a same-origin URL - needed here
 *  because the PDF has to be fetched with an Authorization header first
 *  (see requestBlob), so a plain anchor pointing at the API path directly
 *  cannot be used. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
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
  getMonth: (month: string) => request<MonthlyRecord>(`/monthly/${month}`),
  // The month checklist's rows - see backend routes/monthly.month_commitments.
  monthCommitments: (month: string) =>
    request<MonthCommitment[]>(`/monthly/${month}/commitments`),
  monthlyAnalytics: (back = 11, ahead = 12) =>
    request<MonthlyAnalytics>(
      `/monthly/analytics?months_back=${back}&months_ahead=${ahead}`
    ),
  saveMonth: (month: string, data: MonthlyInput) =>
    request<MonthlyRecord>(`/monthly/${month}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  // Expenses and Income each own one half of this row (spend vs. other
  // income); PATCH sends only the fields that page edits so the other half
  // is left untouched - see backend/src/routes/monthly.py::patch_month.
  patchMonth: (month: string, data: MonthlyPatch) =>
    request<MonthlyRecord>(`/monthly/${month}`, {
      method: "PATCH",
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
  /** The wallet PDF report - see backend/src/routes/report_pdf.py. Returns
   *  the raw bytes; callers hand them to saveBlob() to trigger the
   *  download. `aiInsightId` embeds a finished "wallet_pdf" insight's
   *  commentary (see insightsApi.create("wallet_pdf", ...)) when given. */
  reportPdf: (period: PdfReportPeriod, language: string, aiInsightId?: number) =>
    requestBlob(
      `/reports/pdf?period=${period}&language=${encodeURIComponent(language)}` +
        (aiInsightId ? `&ai_insight_id=${aiInsightId}` : "")
    ),
  getSettings: () => request<Settings>("/settings"),
  setSettings: (base_currency: string, timezone?: string, features?: FeatureFlags) =>
    request<Settings>("/settings", {
      method: "PUT",
      body: JSON.stringify({ base_currency, timezone, features }),
    }),
  setBirthYear: (birth_year: number | null) =>
    request<Settings>("/settings/birth-year", {
      method: "PUT",
      body: JSON.stringify({ birth_year }),
    }),
  recoveryStatus: () => request<RecoveryStatus>("/recovery/status"),
  /** The only call that ever returns the code; it cannot be fetched again. */
  createRecoveryCode: (replace = false) =>
    request<{ code: string }>("/recovery", {
      method: "POST",
      body: JSON.stringify({ replace }),
    }),
  confirmRecoveryCode: (code: string) =>
    request<RecoveryStatus>("/recovery/confirm", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  /** 400 invalid code, 409 account already holds data, 429 locked out
   *  (RateLimitError.retryAfter). */
  restoreRecoveryCode: (code: string) =>
    request<RecoveryRestoreResult>("/recovery/restore", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  getContact: () => request<ContactState>("/contacts"),
  optInContact: () => request<ContactState>("/contacts/opt-in", { method: "POST" }),
  optOutContact: () => request<ContactState>("/contacts/opt-out", { method: "POST" }),
  acceptTerms: (version: number) =>
    request<Settings>("/settings/terms/accept", {
      method: "POST",
      body: JSON.stringify({ version }),
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

/** Same as fmtMoney but always carries an explicit +/− sign (e.g. "+100.00
 *  zł" / "−20.00 zł") - used wherever a figure can be a gain or a loss and
 *  the sign itself is the point (growth, deposits/withdrawals). */
export function fmtSigned(value: number, currency: string, locale = "en-US"): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
    signDisplay: "exceptZero",
  }).format(value);
}

/** A fraction (0.018 -> "+1.8%") with an explicit sign, for growth_pct. */
export function fmtSignedPct(value: number, locale = "en-US"): string {
  return new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 1,
    signDisplay: "exceptZero",
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
