import { useCallback, useEffect, useRef, useState } from "react";
import { api, saveBlob } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useFeatures } from "@/lib/features";
import { insightsApi, isNotFound } from "@/lib/insightsApi";
import type { Insight, InsightState, InsightStatus } from "@/lib/insightsTypes";
import { PDF_REPORT_PERIODS, type PdfReportPeriod } from "@/lib/types";
import InfoTip from "@/components/InfoTip";

/** Generation runs on the same shared LLM queue as the Insights tabs and
 *  can take minutes, so this polls the same way WalletAssessmentTab does. */
const POLL_MS = 3000;
const PENDING: InsightState[] = ["pending", "running", "translating"];

type Phase = "idle" | "queued" | "running" | "translating" | "downloading";

/** Download entry point for the wallet PDF report - period picker, an
 *  optional AI-commentary checkbox (off by default), and one button that
 *  either downloads immediately (no AI) or walks generate -> poll ->
 *  download (AI on), the same job lifecycle the Insights tabs already use.
 *  Rendered on the Assets page only while `portfolio` is on (see
 *  pages/positions.tsx) - this file itself gates only the AI checkbox on
 *  `insights` being on, since the deterministic report needs nothing more
 *  than positions/allocation data. */
export default function PdfReportCard() {
  const { t, lang } = useI18n();
  const { insights } = useFeatures();
  const [period, setPeriod] = useState<PdfReportPeriod>("12m");
  const [includeAi, setIncludeAi] = useState(false);
  const [status, setStatus] = useState<InsightStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string[] | null>(null);
  const pollId = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!insights) {
      setIncludeAi(false);
      return;
    }
    insightsApi
      .status()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, [insights]);

  const stopPolling = useCallback(() => {
    if (pollId.current) {
      clearInterval(pollId.current);
      pollId.current = null;
    }
  }, []);
  useEffect(() => stopPolling, [stopPolling]);

  async function downloadNow(aiInsightId?: number) {
    setPhase("downloading");
    const blob = await api.reportPdf(period, lang, aiInsightId);
    saveBlob(blob, `myfinance-report-${period}-${lang}.pdf`);
  }

  function watch(insightId: number) {
    stopPolling();
    pollId.current = setInterval(async () => {
      let next: Insight;
      try {
        next = await insightsApi.item(insightId);
      } catch (e) {
        stopPolling();
        setBusy(false);
        setPhase("idle");
        setError(e instanceof Error ? e.message : t("common.failedLoad"));
        return;
      }
      if (PENDING.includes(next.status)) {
        setPhase(next.status === "pending" ? "queued" : (next.status as Phase));
        return;
      }
      stopPolling();
      if (next.status === "done") {
        if (next.ungrounded.length > 0) setWarning(next.ungrounded);
        try {
          await downloadNow(next.id);
        } catch (e) {
          setError(e instanceof Error ? e.message : t("pdf.downloadFailed"));
        }
      } else {
        setError(next.error || t("ins.job.failed"));
      }
      setBusy(false);
      setPhase("idle");
    }, POLL_MS);
  }

  // Resume a running/queued job for the currently selected period+language
  // on mount (and whenever either changes) - the same pattern
  // ProfileTab/NextStepsTab use via insightsApi.latest(), so switching away
  // from the Assets page and back (or just reloading) doesn't lose track
  // of a generation started earlier. Only ever picks up a job that matches
  // both `period` and `lang` exactly, so it never attaches to - or steals
  // the poll interval from - a job for a different period.
  useEffect(() => {
    if (!insights) return;
    let alive = true;
    insightsApi
      .latest("wallet_pdf", lang, period)
      .then((latest) => {
        if (!alive || !PENDING.includes(latest.status)) return;
        setIncludeAi(true);
        setError(null);
        setBusy(true);
        watch(latest.id);
      })
      .catch((e) => {
        // Nothing to resume (404) is the common case, not an error; any
        // other failure is a convenience lookup that must not block the
        // page with a banner the person did not ask for.
        if (!alive || isNotFound(e)) return;
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [insights, lang, period]);

  async function go() {
    setBusy(true);
    setError(null);
    setWarning(null);
    try {
      if (!includeAi) {
        await downloadNow();
        setBusy(false);
        setPhase("idle");
        return;
      }
      setPhase("queued");
      const created = await insightsApi.create("wallet_pdf", lang, period);
      watch(created.id);
    } catch (e) {
      setBusy(false);
      setPhase("idle");
      setError(e instanceof Error ? e.message : t("pdf.downloadFailed"));
    }
  }

  const aiConfigured = status?.configured ?? false;
  const aiCheckboxDisabled = !insights || busy || !aiConfigured;

  const buttonLabel =
    phase === "queued"
      ? t("ins.job.queued")
      : phase === "running"
        ? t("ins.job.running")
        : phase === "translating"
          ? t("ins.job.translating")
          : phase === "downloading"
            ? t("pdf.preparing")
            : t("pdf.download");

  return (
    <div className="card space-y-4">
      <div>
        <h2 className="text-lg font-semibold">{t("pdf.title")}</h2>
        <p className="text-sm muted">{t("pdf.subtitle")}</p>
      </div>

      {error && <div className="banner-error">{error}</div>}

      {warning && warning.length > 0 && (
        <div className="banner-error">
          <p>{t("pdf.groundingWarning")}</p>
          <ul className="mt-1 list-disc pl-5">
            {warning.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <span className="label">{t("pdf.period")}</span>
        <div className="mt-1 grid grid-cols-2 gap-2 sm:grid-cols-5">
          {PDF_REPORT_PERIODS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPeriod(p)}
              aria-pressed={period === p}
              disabled={busy}
              className={`rounded-lg border px-3 py-2 text-sm transition disabled:opacity-60 ${
                period === p
                  ? "border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100"
                  : "border-slate-200 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
              }`}
            >
              {t(`pdf.period.${p}`)}
            </button>
          ))}
        </div>
      </div>

      {insights ? (
        <div>
          <div className="flex items-start gap-2">
            <input
              id="pdf-ai-checkbox"
              type="checkbox"
              className="mt-1"
              checked={includeAi}
              onChange={(e) => setIncludeAi(e.target.checked)}
              disabled={aiCheckboxDisabled}
            />
            <label htmlFor="pdf-ai-checkbox" className="flex items-center gap-1 text-sm">
              {t("pdf.includeAi")}
              <InfoTip text={t("pdf.aiInfo")} label={t("pdf.includeAi")} />
            </label>
          </div>
          {status && !aiConfigured && (
            <p className="mt-1 text-xs subtle">{t("pdf.aiNotConfigured")}</p>
          )}
        </div>
      ) : (
        <p className="text-xs subtle">{t("pdf.aiUnavailable")}</p>
      )}

      <button onClick={go} className="btn-primary" disabled={busy}>
        {buttonLabel}
      </button>
    </div>
  );
}
