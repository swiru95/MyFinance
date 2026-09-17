import { useCallback, useEffect, useMemo, useState } from "react";
import { api, fmtMoney, fmtNum } from "@/lib/api";
import { INPUT_CURRENCIES } from "@/lib/types";
import type { MonthlyAnalytics, MonthlyRecord } from "@/lib/types";
import { monthLabel } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";
import BudgetTimelineChart from "@/components/BudgetTimelineChart";
import SavingsRateChart from "@/components/SavingsRateChart";
import CategoryTrendChart from "@/components/CategoryTrendChart";

const currentMonthKey = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
};

export default function MonthlyPage() {
  const { t, locale } = useI18n();
  const [months, setMonths] = useState<MonthlyRecord[]>([]);
  const [analytics, setAnalytics] = useState<MonthlyAnalytics | null>(null);
  const [selected, setSelected] = useState<string>(currentMonthKey());
  const [income, setIncome] = useState("");
  const [spent, setSpent] = useState("");
  const [currency, setCurrency] = useState("PLN");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [list, stats] = await Promise.all([
        api.months(),
        api.monthlyAnalytics(11, 12),
      ]);
      setMonths(list);
      setAnalytics(stats);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedLoad"));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const record = useMemo(
    () => months.find((m) => m.month === selected) ?? null,
    [months, selected]
  );
  const base = analytics?.base_currency ?? record?.base_currency ?? "PLN";

  // Load the selected month's figures into the editor.
  useEffect(() => {
    if (!record) return;
    setIncome(record.income ? String(record.income) : "");
    setSpent(record.actual_spent ? String(record.actual_spent) : "");
    setCurrency(record.currency || base);
    setNotes(record.notes ?? "");
    setMsg(null);
  }, [record, base]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api.saveMonth(selected, {
        income: parseFloat(income) || 0,
        actual_spent: parseFloat(spent) || 0,
        currency,
        notes,
      });
      setMsg(t("mon.saved", { month: monthLabel(selected, locale) }));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(false);
    }
  }

  const surplus = record?.surplus ?? 0;
  const surplusTone =
    surplus > 0
      ? "text-emerald-600 dark:text-emerald-400"
      : surplus < 0
        ? "text-red-600 dark:text-red-400"
        : "";
  const variance = record?.variance ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t("mon.title")}</h1>
        <p className="text-sm muted">
          {t("mon.subtitle")}
        </p>
      </div>

      {error && <div className="banner-error">{error}</div>}

      <div className="grid gap-4 lg:grid-cols-3">
        <form onSubmit={save} className="card space-y-3 lg:col-span-1">
          <div>
            <label className="label" htmlFor="m-month">{t("mon.month")}</label>
            <select
              id="m-month"
              className="input"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              {months.map((m) => (
                <option key={m.month} value={m.month}>
                  {monthLabel(m.month, locale)}
                  {m.saved ? "" : t("mon.notFilled")}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="m-income">{t("mon.income")}</label>
              <input
                id="m-income"
                className="input"
                type="number"
                step="0.01"
                min="0"
                value={income}
                onChange={(e) => setIncome(e.target.value)}
                placeholder="0.00"
              />
            </div>
            <div>
              <label className="label" htmlFor="m-spent">{t("mon.actualSpent")}</label>
              <input
                id="m-spent"
                className="input"
                type="number"
                step="0.01"
                min="0"
                value={spent}
                onChange={(e) => setSpent(e.target.value)}
                placeholder="0.00"
              />
            </div>
          </div>

          <div>
            <label className="label" htmlFor="m-currency">{t("common.currency")}</label>
            <select
              id="m-currency"
              className="input"
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
            >
              {INPUT_CURRENCIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="label" htmlFor="m-notes">{t("common.notes")}</label>
            <input
              id="m-notes"
              className="input"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          {msg && <p className="banner-info">{msg}</p>}

          <button type="submit" className="btn-primary w-full" disabled={busy}>
            {busy
              ? t("common.saving")
              : t("mon.saveMonth", { month: monthLabel(selected, locale) })}
          </button>
        </form>

        <div className="grid auto-rows-min content-start gap-4 sm:grid-cols-2 lg:col-span-2">
          <div className="card">
            <p className="text-sm muted">{t("mon.committedThis")}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">
              {record ? fmtMoney(record.committed, base, locale) : "—"}
            </p>
            <p className="mt-1 text-xs subtle">{t("mon.fromRecurring")}</p>
          </div>
          <div className="card">
            <p className="text-sm muted">{t("mon.surplus")}</p>
            <p className={`mt-1 text-2xl font-semibold tabular-nums ${surplusTone}`}>
              {record ? fmtMoney(surplus, base, locale) : "—"}
            </p>
            <p className="mt-1 text-xs subtle">
              {record?.savings_rate != null
                ? t("mon.savedPct", { rate: fmtNum(record.savings_rate, 1, locale) })
                : t("mon.addIncomeHint")}
            </p>
          </div>
          <div className="card">
            <p className="text-sm muted">{t("mon.actualVsCommitted")}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">
              {record ? fmtMoney(variance, base, locale) : "—"}
            </p>
            <p className="mt-1 text-xs subtle">
              {variance > 0
                ? t("mon.above")
                : variance < 0
                  ? t("mon.below")
                  : t("mon.matches")}
            </p>
          </div>
          <div className="card">
            <p className="text-sm muted">{t("mon.avgSavings")}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">
              {analytics?.avg_savings_rate != null
                ? `${fmtNum(analytics.avg_savings_rate, 1, locale)}%`
                : "—"}
            </p>
            <p className="mt-1 text-xs subtle">
              {t(
                analytics?.months_recorded === 1
                  ? "mon.acrossMonth"
                  : "mon.acrossMonths",
                { count: analytics?.months_recorded ?? 0 }
              )}
            </p>
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="text-lg font-semibold">{t("mon.chartTitle")}</h2>
        <p className="mb-3 text-sm muted">
          {t("mon.chartSubtitle")}
        </p>
        <BudgetTimelineChart
          points={analytics?.timeline ?? []}
          currency={base}
          currentMonth={currentMonthKey()}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card">
          <h2 className="text-lg font-semibold">{t("mon.savingsTitle")}</h2>
          <p className="mb-3 text-sm muted">
            {t("mon.savingsSubtitle")}
          </p>
          <SavingsRateChart points={analytics?.timeline ?? []} />
        </div>
        <div className="card">
          <h2 className="text-lg font-semibold">{t("mon.categoryTitle")}</h2>
          <p className="mb-3 text-sm muted">
            {t("mon.categorySubtitle")}
          </p>
          <CategoryTrendChart
            series={analytics?.category_series ?? []}
            categories={analytics?.categories ?? []}
            currency={base}
          />
        </div>
      </div>

      {/* Table view: also the accessibility relief for the light-mode palette. */}
      <div className="card p-0">
        <h2 className="border-b border-slate-200 px-5 py-3 text-lg font-semibold dark:border-slate-800">
          {t("mon.recorded")}
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              <tr>
                <th className="px-5 py-2">{t("mon.tblMonth")}</th>
                <th className="px-5 py-2 text-right">{t("mon.tblIncome")}</th>
                <th className="px-5 py-2 text-right">{t("mon.tblActual")}</th>
                <th className="px-5 py-2 text-right">{t("mon.tblCommitted")}</th>
                <th className="px-5 py-2 text-right">{t("mon.tblSurplus")}</th>
                <th className="px-5 py-2 text-right">{t("mon.tblSaved")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {months.filter((m) => m.saved).length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-6 text-center text-sm subtle">
                    {t("mon.tblEmpty")}
                  </td>
                </tr>
              ) : (
                months
                  .filter((m) => m.saved)
                  .map((m) => (
                    <tr key={m.month}>
                      <td className="px-5 py-2 font-medium">{monthLabel(m.month, locale)}</td>
                      <td className="px-5 py-2 text-right tabular-nums">
                        {fmtMoney(m.income_in_base, base, locale)}
                      </td>
                      <td className="px-5 py-2 text-right tabular-nums">
                        {fmtMoney(m.actual_in_base, base, locale)}
                      </td>
                      <td className="px-5 py-2 text-right tabular-nums">
                        {fmtMoney(m.committed, base, locale)}
                      </td>
                      <td
                        className={`px-5 py-2 text-right tabular-nums ${
                          m.surplus > 0
                            ? "text-emerald-600 dark:text-emerald-400"
                            : m.surplus < 0
                              ? "text-red-600 dark:text-red-400"
                              : ""
                        }`}
                      >
                        {fmtMoney(m.surplus, base, locale)}
                      </td>
                      <td className="px-5 py-2 text-right tabular-nums">
                        {m.savings_rate != null
                          ? `${fmtNum(m.savings_rate, 1, locale)}%`
                          : "—"}
                      </td>
                    </tr>
                  ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
