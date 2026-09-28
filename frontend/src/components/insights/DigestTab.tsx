import { useCallback, useEffect, useRef, useState } from "react";
import { insightsApi } from "@/lib/insightsApi";
import { fmtDateTime, fmtMoney, fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSettings } from "@/components/SettingsProvider";
import type { Insight, InsightSummary } from "@/lib/insightsTypes";
import Markdown from "@/components/Markdown";

const POLL_MS = 3000;
const PENDING: Insight["status"][] = ["pending", "running", "translating"];

/** Which fields of build_digest_snapshot (backend/src/services/insights.py)
 *  are worth a row in the readable table, how to format each, and the
 *  i18n key for its label. Deliberately a whitelist rather than "every key
 *  in the dict": `income_sources`, `ladder` and `anomalies` are nested
 *  structures the model's prose already covers in full sentences, not
 *  standalone figures, and `period`/`base_currency`/the two `*_enabled`
 *  flags are context the table itself doesn't need to repeat. */
const SNAPSHOT_FIELDS: {
  key: string;
  labelKey: string;
  format: "money" | "percent" | "number";
}[] = [
  { key: "income_total", labelKey: "ins.digest.snap.incomeTotal", format: "money" },
  { key: "typed_spend", labelKey: "ins.digest.snap.typedSpend", format: "money" },
  { key: "effective_spend", labelKey: "ins.digest.snap.effectiveSpend", format: "money" },
  { key: "savings_rate", labelKey: "ins.digest.snap.savingsRate", format: "percent" },
  { key: "avg_savings_rate_12m", labelKey: "ins.digest.snap.avgSavingsRate12m", format: "percent" },
  { key: "wallet_change", labelKey: "ins.digest.snap.walletChange", format: "money" },
  { key: "flows", labelKey: "ins.digest.snap.flows", format: "money" },
  { key: "market_change", labelKey: "ins.digest.snap.marketChange", format: "money" },
  { key: "fi_progress_pct", labelKey: "ins.digest.snap.fiProgress", format: "percent" },
  { key: "years_to_fi", labelKey: "ins.digest.snap.yearsToFi", format: "number" },
];

// month_out.savings_rate, hist.avg_savings_rate and fi_progress are all
// already 0-100 by the time they reach the snapshot (see routes/monthly.py
// and services/insights.py:build_digest_snapshot's `round(... * 100, 1)`),
// so "percent" here only ever adds the "%" sign, never rescales.
function formatSnapshotValue(
  raw: unknown,
  format: (typeof SNAPSHOT_FIELDS)[number]["format"],
  currency: string,
  locale: string,
): string {
  if (typeof raw !== "number") return "—";
  switch (format) {
    case "money":
      return fmtMoney(raw, currency, locale);
    case "percent":
      return `${fmtNum(raw, 1, locale)}%`;
    case "number":
      return fmtNum(raw, 1, locale);
  }
}

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
              <table className="mt-2 w-full text-left text-xs">
                <tbody>
                  {SNAPSHOT_FIELDS.map((f) => (
                    <tr key={f.key} className="border-t border-slate-200 dark:border-slate-800">
                      <td className="py-1 pr-3">{t(f.labelKey)}</td>
                      <td className="py-1 text-right tabular-nums">
                        {formatSnapshotValue(
                          insight.snapshot![f.key],
                          f.format,
                          typeof insight.snapshot!.base_currency === "string"
                            ? insight.snapshot!.base_currency
                            : "PLN",
                          locale,
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
