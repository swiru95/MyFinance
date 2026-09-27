import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { insightsApi, isNotFound } from "@/lib/insightsApi";
import type {
  Insight,
  LadderResponse,
  NextStepsData,
  StepFeedbackState,
} from "@/lib/insightsTypes";
import LadderChecklist from "./LadderChecklist";
import Markdown from "@/components/Markdown";

const POLL_MS = 3000;
const PENDING: Insight["status"][] = ["pending", "running", "translating"];
const FEEDBACK_STATES: StepFeedbackState[] = ["done", "dismissed", "later"];

interface Props {
  status: { configured: boolean } | null;
}

export default function NextStepsTab({ status }: Props) {
  const { t, lang } = useI18n();
  const [ladder, setLadder] = useState<LadderResponse | null>(null);
  const [insight, setInsight] = useState<Insight | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollId = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadLadder = useCallback(async () => {
    try {
      setLadder(await insightsApi.ladder());
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedLoad"));
    }
  }, [t]);

  const loadLatest = useCallback(async () => {
    try {
      setInsight(await insightsApi.latest("next_steps", lang));
    } catch (e) {
      if (!isNotFound(e)) {
        setError(e instanceof Error ? e.message : t("common.failedLoad"));
      }
    }
  }, [lang, t]);

  useEffect(() => {
    loadLadder();
    loadLatest();
  }, [loadLadder, loadLatest]);

  const stopPolling = useCallback(() => {
    if (pollId.current) {
      clearInterval(pollId.current);
      pollId.current = null;
    }
  }, []);
  useEffect(() => stopPolling, [stopPolling]);

  const watch = useCallback(
    (id: number) => {
      stopPolling();
      pollId.current = setInterval(async () => {
        try {
          const next = await insightsApi.item(id);
          setInsight(next);
          if (!PENDING.includes(next.status)) {
            stopPolling();
            setBusy(false);
          }
        } catch (e) {
          stopPolling();
          setBusy(false);
          setError(e instanceof Error ? e.message : t("common.failedLoad"));
        }
      }, POLL_MS);
    },
    [stopPolling, t],
  );

  async function refresh() {
    setBusy(true);
    setError(null);
    try {
      const queued = await insightsApi.create("next_steps", lang);
      setInsight(queued);
      watch(queued.id);
    } catch (e) {
      setBusy(false);
      setError(e instanceof Error ? e.message : t("common.failedSave"));
    }
  }

  async function giveFeedback(key: string, state: StepFeedbackState) {
    try {
      await insightsApi.setLadderState(key, state);
      await loadLadder();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedSave"));
    }
  }

  const pending = insight != null && PENDING.includes(insight.status);
  const data =
    insight?.status === "done" && insight.data
      ? (insight.data as unknown as NextStepsData)
      : null;
  const rungs = [...(ladder?.rungs ?? [])].sort((a, b) => a.order - b.order);
  const unavailable = status != null && !status.configured;

  return (
    <div className="space-y-6">
      <div className="card">
        <h2 className="text-lg font-semibold">{t("ins.next.checklistTitle")}</h2>
        <p className="mb-3 text-sm muted">{t("ins.next.checklistSubtitle")}</p>
        <LadderChecklist rungs={rungs} />
      </div>

      <div className="card space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">{t("ins.next.rankedTitle")}</h2>
          <button
            onClick={refresh}
            className="btn-primary"
            disabled={busy || pending || unavailable}
          >
            {busy || pending ? t("ins.job.running") : t("ins.next.refresh")}
          </button>
        </div>

        {error && <div className="banner-error">{error}</div>}

        {pending && (
          <div className="flex items-center gap-3">
            <span
              className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600 dark:border-slate-600 dark:border-t-brand-400"
              aria-hidden
            />
            <p className="text-sm muted">
              {insight?.status === "translating"
                ? t("ins.job.translating")
                : insight?.status === "running"
                  ? t("ins.job.running")
                  : t("ins.job.queued")}
            </p>
          </div>
        )}

        {insight?.status === "failed" && (
          <div className="space-y-2">
            <p className="text-sm font-medium text-red-600">{t("ins.job.failed")}</p>
            <p className="text-xs muted">{insight.error}</p>
          </div>
        )}

        {!pending && data && data.steps.length > 0 && (
          <ul className="space-y-3">
            {data.steps.map((step) => {
              const feedback = ladder?.feedback[step.key];
              return (
                <li
                  key={step.key}
                  className="rounded-lg border border-slate-200 p-3 dark:border-slate-800"
                >
                  <p className="text-sm font-medium">{step.title}</p>
                  <div className="mt-1">
                    <Markdown text={step.why_md} />
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {FEEDBACK_STATES.map((state) => (
                      <button
                        key={state}
                        onClick={() => giveFeedback(step.key, state)}
                        aria-pressed={feedback?.state === state}
                        className={`btn-ghost text-xs ${feedback?.state === state ? "border-brand-500 text-brand-700 dark:text-brand-100" : ""}`}
                      >
                        {t(`ins.next.feedback.${state}`)}
                      </button>
                    ))}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {!pending && !data && insight?.status !== "failed" && (
          <p className="text-sm subtle">{t("ins.next.rankedEmpty")}</p>
        )}
      </div>
    </div>
  );
}
