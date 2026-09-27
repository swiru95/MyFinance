import { useCallback, useEffect, useRef, useState } from "react";
import { insightsApi } from "@/lib/insightsApi";
import { fmtDateTime } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSettings } from "@/components/SettingsProvider";
import type { Insight, InsightSummary } from "@/lib/insightsTypes";
import Markdown from "@/components/Markdown";

const POLL_MS = 3000;
const PENDING: Insight["status"][] = ["pending", "running", "translating"];

/** The last fully completed calendar month - matches the "default the last
 *  completed one" digest period from the spec. */
function lastCompletedMonthKey(): string {
  const now = new Date();
  const d = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

interface Props {
  status: { configured: boolean } | null;
}

export default function DigestTab({ status }: Props) {
  const { t, lang, locale } = useI18n();
  const { timeZone } = useSettings();
  const [month, setMonth] = useState(lastCompletedMonthKey());
  const [insight, setInsight] = useState<Insight | null>(null);
  const [history, setHistory] = useState<InsightSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollId = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      const rows = await insightsApi.list();
      setHistory(rows.filter((r) => r.kind === "digest"));
    } catch {
      // History is a convenience; a failure here must not replace whatever
      // digest is currently on screen with an error banner.
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

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
      const queued = await insightsApi.create("digest", lang, month);
      setInsight(queued);
      watch(queued.id);
    } catch (e) {
      setBusy(false);
      setError(e instanceof Error ? e.message : t("common.failedSave"));
    }
  }

  async function open(id: number) {
    try {
      const picked = await insightsApi.item(id);
      setInsight(picked);
      setMonth(picked.period || month);
      if (PENDING.includes(picked.status)) {
        setBusy(true);
        watch(id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedLoad"));
    }
  }

  async function remove(id: number) {
    if (!confirm(t("ins.digest.confirmDelete"))) return;
    try {
      await insightsApi.remove(id);
      if (insight?.id === id) {
        stopPolling();
        setInsight(null);
        setBusy(false);
      }
      loadHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedDelete"));
    }
  }

  const pending = insight != null && PENDING.includes(insight.status);
  const unavailable = status != null && !status.configured;
  const ungrounded = insight?.status === "done" ? insight.ungrounded ?? [] : [];

  return (
    <div className="space-y-6">
      <div className="card space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="label" htmlFor="ins-digest-month">
              {t("ins.digest.month")}
            </label>
            <input
              id="ins-digest-month"
              type="month"
              className="input"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              disabled={busy || pending}
            />
          </div>
          <button
            onClick={generate}
            className="btn-primary"
            disabled={busy || pending || !month || unavailable}
          >
            {busy || pending ? t("ins.digest.generating") : t("ins.digest.generate")}
          </button>
        </div>
        {status?.configured === false && (
          <p className="text-sm banner-error">{t("rep.unavailable")}</p>
        )}
      </div>

      {error && <div className="banner-error">{error}</div>}

      {pending && (
        <div className="card flex items-center gap-3">
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
        <div className="card space-y-2">
          <p className="text-sm font-medium text-red-600">{t("ins.job.failed")}</p>
          <p className="text-xs muted">{insight.error}</p>
          <button onClick={generate} className="btn-ghost text-sm" disabled={busy}>
            {t("ins.job.retry")}
          </button>
        </div>
      )}

      {insight && insight.status === "done" && insight.content ? (
        <article className="card">
          <header className="mb-4 border-b border-slate-200 pb-3 dark:border-slate-800">
            <p className="text-sm font-medium">{insight.period}</p>
            <p className="text-xs subtle">
              {t("rep.generatedAt", {
                when: fmtDateTime(insight.created_at, locale, timeZone),
              })}
            </p>
          </header>

          {ungrounded.length > 0 && (
            <div className="mb-4 banner-error">
              <p>{t("ins.digest.groundingWarning")}</p>
              <ul className="mt-1 list-disc pl-5">
                {ungrounded.map((u, i) => (
                  <li key={i}>{u}</li>
                ))}
              </ul>
            </div>
          )}

          <Markdown text={insight.content} />

          {insight.snapshot && (
            <details className="mt-4 text-xs subtle">
              <summary className="cursor-pointer">{t("ins.digest.snapshot")}</summary>
              <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-slate-100 p-3 dark:bg-slate-800">
                {JSON.stringify(insight.snapshot, null, 2)}
              </pre>
            </details>
          )}

          <p className="mt-6 border-t border-slate-200 pt-3 text-xs subtle dark:border-slate-800">
            {t("rep.disclaimer")}
          </p>
        </article>
      ) : (
        !pending &&
        insight?.status !== "failed" && (
          <div className="card grid h-32 place-items-center text-sm subtle">
            {t("ins.digest.empty")}
          </div>
        )
      )}

      <div className="card p-0">
        <h2 className="border-b border-slate-200 px-5 py-3 text-lg font-semibold dark:border-slate-800">
          {t("ins.digest.history")}
        </h2>
        {history.length === 0 ? (
          <p className="px-5 py-6 text-center text-sm subtle">
            {t("ins.digest.noHistory")}
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
                    {h.period}
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
