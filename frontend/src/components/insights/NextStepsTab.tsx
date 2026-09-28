import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { insightsApi, isNotFound } from "@/lib/insightsApi";
import type {
  Insight,
  LadderResponse,
  NextStepsData,
  StepFeedbackState,
} from "@/lib/insightsTypes";
import LadderChecklist, { type AiStep } from "./LadderChecklist";

const POLL_MS = 3000;
const PENDING: Insight["status"][] = ["pending", "running", "translating"];

interface Props {
  status: { configured: boolean } | null;
}

/** One merged checklist (round 2 spec item 9): the deterministic ladder and
 *  the AI ranking used to be two separate lists answering the same "what
 *  should I do next" question. Now every rung is one row; a rung the latest
 *  AI ranking also picked out shows that model's title/explanation inline,
 *  and AI-ranked rows sort first, in the AI's own order - see
 *  LadderChecklist for the row rendering. */
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
      ? ((insight.language === "pl"
          ? (insight.data_localized ?? insight.data)
          : insight.data) as unknown as NextStepsData)
      : null;
  // data_localized is only ever set for a "pl" job (see
  // services/insights.py:localize_data); null there means the translation
  // call failed, so the list below is silently showing English prose.
  const translationUnavailable =
    insight?.status === "done" &&
    insight.language === "pl" &&
    insight.data != null &&
    insight.data_localized == null;
  const unavailable = status != null && !status.configured;

  // AI steps keyed by rung key (see LadderChecklist's AiStep doc), and the
  // merged row order: AI-ranked rungs first in the AI's own order, then
  // every other rung in the ladder's own order - so a fresh AI ranking
  // reorders the top of the list without reshuffling rungs it left alone.
  const aiByKey = useMemo(() => {
    const map = new Map<string, AiStep>();
    if (data) {
      for (const step of data.steps) {
        map.set(step.key, { title: step.title, why_md: step.why_md });
      }
    }
    return map;
  }, [data]);
  const rungs = useMemo(() => {
    const all = [...(ladder?.rungs ?? [])].sort((a, b) => a.order - b.order);
    const aiOrder = new Map((data?.steps ?? []).map((s, i) => [s.key, i]));
    return all.sort((a, b) => {
      const aRank = aiOrder.get(a.key);
      const bRank = aiOrder.get(b.key);
      if (aRank != null && bRank != null) return aRank - bRank;
      if (aRank != null) return -1;
      if (bRank != null) return 1;
      return a.order - b.order;
    });
  }, [ladder, data]);

  return (
    <div className="card space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t("ins.next.checklistTitle")}</h2>
          <p className="text-sm muted">{t("ins.next.checklistSubtitle")}</p>
        </div>
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

      {translationUnavailable && (
        <p className="text-xs subtle">{t("ins.data.translationUnavailable")}</p>
      )}

      <LadderChecklist
        rungs={rungs}
        aiByKey={aiByKey}
        feedback={ladder?.feedback ?? {}}
        onFeedback={giveFeedback}
      />
    </div>
  );
}
