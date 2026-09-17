import { useCallback, useEffect, useRef, useState } from "react";
import { api, fmtDateTime } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSettings } from "@/components/SettingsProvider";
import { REPORT_STYLES } from "@/lib/types";
import type {
  Report,
  ReportStatus,
  ReportStyle,
  ReportSummary,
} from "@/lib/types";
import Markdown from "@/components/Markdown";

/** Translation keys per style, so the picker stays in the active language. */
const STYLE_KEYS: Record<ReportStyle, { label: string; hint: string }> = {
  safe: { label: "rep.style.safe", hint: "rep.style.safeHint" },
  balanced: { label: "rep.style.balanced", hint: "rep.style.balancedHint" },
  risky: { label: "rep.style.risky", hint: "rep.style.riskyHint" },
  long_term: { label: "rep.style.longTerm", hint: "rep.style.longTermHint" },
};

/** Generation runs on the server and takes minutes, so the page polls. */
const POLL_MS = 3000;
const PENDING: Report["status"][] = ["pending", "running", "translating"];

export default function ReportPage() {
  const { t, lang, locale } = useI18n();
  const { timeZone } = useSettings();
  const [status, setStatus] = useState<ReportStatus | null>(null);
  const [style, setStyle] = useState<ReportStyle>("balanced");
  const [report, setReport] = useState<Report | null>(null);
  const [history, setHistory] = useState<ReportSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Held in a ref as well so the poll can stop itself without being restarted
  // by its own setState.
  const pollId = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      setHistory(await api.reports());
    } catch {
      // The history list is a convenience; a failure here must not replace the
      // report the user is reading with an error.
    }
  }, []);

  useEffect(() => {
    api
      .reportStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
    loadHistory();
  }, [loadHistory]);

  // Load the newest finished report so the page is not empty on arrival.
  useEffect(() => {
    if (report || history.length === 0) return;
    const newest = history.find((h) => h.status === "done");
    if (newest) api.report(newest.id).then(setReport).catch(() => {});
  }, [history, report]);

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
          const next = await api.report(id);
          setReport(next);
          if (!PENDING.includes(next.status)) {
            stopPolling();
            setBusy(false);
            loadHistory();
          }
        } catch (e) {
          stopPolling();
          setBusy(false);
          setError(e instanceof Error ? e.message : t("common.failedLoad"));
        }
      }, POLL_MS);
    },
    [loadHistory, stopPolling, t],
  );

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      // The report is written in whichever language the app is currently in.
      const queued = await api.createReport(style, lang);
      setReport(queued);
      watch(queued.id);
    } catch (e) {
      setBusy(false);
      setError(e instanceof Error ? e.message : t("common.failedSave"));
    }
  }

  async function open(id: number) {
    try {
      const picked = await api.report(id);
      setReport(picked);
      if (PENDING.includes(picked.status)) {
        setBusy(true);
        watch(id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedLoad"));
    }
  }

  async function remove(id: number) {
    if (!confirm(t("rep.confirmDelete"))) return;
    try {
      await api.deleteReport(id);
      if (report?.id === id) {
        stopPolling();
        setReport(null);
        setBusy(false);
      }
      loadHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedDelete"));
    }
  }

  const pending = report != null && PENDING.includes(report.status);
  const progressKey =
    report?.status === "translating"
      ? "rep.translating"
      : report?.status === "running"
        ? "rep.running"
        : "rep.queued";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t("rep.title")}</h1>
        <p className="text-sm muted">{t("rep.subtitle")}</p>
      </div>

      {error && <div className="banner-error">{error}</div>}
      {status && !status.configured && (
        <div className="banner-error">{t("rep.unavailable")}</div>
      )}

      <div className="card space-y-4">
        <div>
          <span className="label">{t("rep.style")}</span>
          <div className="mt-1 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {REPORT_STYLES.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setStyle(option)}
                aria-pressed={style === option}
                disabled={busy}
                className={`rounded-lg border p-3 text-left transition disabled:opacity-60 ${
                  style === option
                    ? "border-brand-600 bg-brand-50 dark:bg-brand-500/15"
                    : "border-slate-200 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
                }`}
              >
                <span
                  className={`block text-sm font-medium ${
                    style === option
                      ? "text-brand-700 dark:text-brand-100"
                      : "text-slate-700 dark:text-slate-200"
                  }`}
                >
                  {t(STYLE_KEYS[option].label)}
                </span>
                <span className="mt-1 block text-xs subtle">
                  {t(STYLE_KEYS[option].hint)}
                </span>
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs muted">{t("rep.styleHint")}</p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={generate}
            className="btn-primary"
            disabled={busy || pending || (status != null && !status.configured)}
          >
            {busy || pending ? t("rep.generating") : t("rep.generate")}
          </button>
          {lang === "pl" && <p className="text-xs subtle">{t("rep.langNote")}</p>}
        </div>

        {status?.configured && (
          <p className="text-xs subtle">
            {status.mtls
              ? `🔐 ${t("rep.mtls", { model: status.model })}`
              : !status.tls_verified
                ? `⚠️ ${t("rep.tlsPlain", { model: status.model })}`
                : ""}
          </p>
        )}
      </div>

      {pending && (
        <div className="card flex items-center gap-3">
          <span
            className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600 dark:border-slate-600 dark:border-t-brand-400"
            aria-hidden
          />
          <p className="text-sm muted">{t(progressKey)}</p>
        </div>
      )}

      {report?.status === "failed" && (
        <div className="card space-y-2">
          <p className="text-sm font-medium text-red-600">{t("rep.failed")}</p>
          <p className="text-xs muted">{report.error}</p>
          <button onClick={generate} className="btn-ghost text-sm" disabled={busy}>
            {t("rep.retry")}
          </button>
        </div>
      )}

      {report && report.status === "done" && report.content ? (
        <article className="card">
          <header className="mb-4 border-b border-slate-200 pb-3 dark:border-slate-800">
            <p className="text-sm font-medium">
              {t(STYLE_KEYS[report.style].label)}
            </p>
            <p className="text-xs subtle">
              {t("rep.generatedAt", {
                when: fmtDateTime(report.created_at, locale, timeZone),
              })}
              {" · "}
              {report.translator
                ? t("rep.translatedLine", {
                    model: report.model,
                    translator: report.translator,
                  })
                : t("rep.modelLine", { model: report.model })}
            </p>
          </header>
          <Markdown text={report.content} />
          <p className="mt-6 border-t border-slate-200 pt-3 text-xs subtle dark:border-slate-800">
            {t("rep.disclaimer")}
          </p>
        </article>
      ) : (
        !pending &&
        report?.status !== "failed" && (
          <div className="card grid h-40 place-items-center text-sm subtle">
            {t("rep.empty")}
          </div>
        )
      )}

      <div className="card p-0">
        <h2 className="border-b border-slate-200 px-5 py-3 text-lg font-semibold dark:border-slate-800">
          {t("rep.history")}
        </h2>
        {history.length === 0 ? (
          <p className="px-5 py-6 text-center text-sm subtle">
            {t("rep.noHistory")}
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {history.map((h) => (
              <li
                key={h.id}
                className="flex flex-wrap items-center justify-between gap-3 px-5 py-3"
              >
                <button
                  onClick={() => open(h.id)}
                  className="min-w-0 text-left"
                  disabled={h.status === "failed"}
                >
                  <span className="block text-sm font-medium">
                    {t(STYLE_KEYS[h.style].label)}
                    <span className="ml-2 text-xs font-normal uppercase tracking-wide subtle">
                      {h.language}
                    </span>
                  </span>
                  <span className="block text-xs subtle">
                    {fmtDateTime(h.created_at, locale, timeZone)}
                    {h.status !== "done" && ` · ${h.status}`}
                  </span>
                </button>
                <button
                  onClick={() => remove(h.id)}
                  className="btn-ghost text-xs text-red-600"
                  aria-label={t("common.delete")}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
