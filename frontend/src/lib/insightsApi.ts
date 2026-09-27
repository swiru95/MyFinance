/** LLM-insights calls, kept out of lib/api.ts so feature work does not
 *  collide there. Uses the same `request` helper api.ts exports, so auth
 *  headers and error handling stay identical to every other call in the app. */
import { request } from "./api";
import type {
  Insight,
  InsightKind,
  InsightStatus,
  InsightSummary,
  LadderResponse,
  ProfileAnswers,
  StepFeedbackState,
} from "./insightsTypes";

export const insightsApi = {
  status: () => request<InsightStatus>("/insights/status"),

  getAnswers: () => request<ProfileAnswers>("/insights/profile/answers"),
  saveAnswers: (answers: ProfileAnswers) =>
    request<ProfileAnswers>("/insights/profile/answers", {
      method: "PUT",
      body: JSON.stringify(answers),
    }),

  list: () => request<InsightSummary[]>("/insights"),
  item: (id: number) => request<Insight>(`/insights/item/${id}`),
  /** Newest done row of a kind; the backend 404s when there is none yet - see
   *  isNotFound below for how callers should treat that. */
  latest: (kind: InsightKind, language: string) =>
    request<Insight>(
      `/insights/${kind}/latest?language=${encodeURIComponent(language)}`,
    ),
  create: (kind: InsightKind, language: string, period?: string) =>
    request<Insight>(`/insights/${kind}`, {
      method: "POST",
      body: JSON.stringify(period ? { language, period } : { language }),
    }),
  remove: (id: number) =>
    request<void>(`/insights/item/${id}`, { method: "DELETE" }),

  ladder: () => request<LadderResponse>("/insights/ladder"),
  setLadderState: (key: string, state: StepFeedbackState) =>
    request<LadderResponse>(`/insights/ladder/${key}`, {
      method: "PUT",
      body: JSON.stringify({ state }),
    }),
};

/** `request` throws a bare Error("API <status>: ...") for any non-2xx, non
 *  204/401/403 response (see lib/api.ts) - this is how callers tell "nothing
 *  generated yet" (404) apart from a real failure. */
export function isNotFound(e: unknown): boolean {
  return e instanceof Error && /^API 404\b/.test(e.message);
}
