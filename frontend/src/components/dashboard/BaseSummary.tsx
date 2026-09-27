import { useEffect, useState } from "react";
import { api, fmtMoney, fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { ExpenseSummary, MonthlyRecord } from "@/lib/types";
import InfoTip from "@/components/InfoTip";

const currentMonthKey = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
};

/** Always-on dashboard summary, built entirely from income and expenses -
 *  nothing here needs an asset to be tracked, so it is what a new user with
 *  Portfolio off still sees at the top: this month's income, commitments
 *  (including the JDG ZUS/health line), what was actually spent and the
 *  savings rate if recorded, and the next payments due. Portfolio tiles and
 *  charts render below this in pages/index.tsx, gated on that feature. */
export default function BaseSummary() {
  const { t, locale } = useI18n();
  const [month, setMonth] = useState<MonthlyRecord | null>(null);
  const [expenses, setExpenses] = useState<ExpenseSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [m, e] = await Promise.all([
          api.getMonth(currentMonthKey()),
          api.expenseSummary(),
        ]);
        if (!alive) return;
        setMonth(m);
        setExpenses(e);
        setError(null);
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : t("common.failedLoad"));
      }
    }
    load();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const currency = expenses?.base_currency ?? month?.base_currency ?? "PLN";
  const upcoming = expenses?.upcoming.slice(0, 3) ?? [];

  return (
    <div className="space-y-4">
      {error && <div className="banner-error">{error}</div>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="card">
          <p className="text-sm muted">{t("dash.base.income")}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">
            {month ? fmtMoney(month.income_in_base, currency, locale) : "—"}
          </p>
          <p className="mt-1 text-xs subtle">{t("dash.base.incomeHint")}</p>
        </div>
        <div className="card">
          <p className="flex items-center text-sm muted">
            {t("dash.monthlyCommitted")}
            <InfoTip text={t("gloss.fixedMonthlyCosts")} label={t("dash.monthlyCommitted")} />
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">
            {expenses ? fmtMoney(expenses.monthly_total, currency, locale) : "—"}
          </p>
          {expenses && expenses.business_contributions_total > 0 ? (
            <p className="mt-1 text-xs subtle">
              {t("dash.monthlyCommittedInclBusiness", {
                amount: fmtMoney(expenses.business_contributions_total, currency, locale),
              })}
            </p>
          ) : (
            <p className="mt-1 text-xs subtle">{t("dash.fromExpenses")}</p>
          )}
        </div>
        <div className="card">
          <p className="text-sm muted">{t("dash.base.spent")}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">
            {month ? fmtMoney(month.actual_in_base, currency, locale) : "—"}
          </p>
          <p className="mt-1 text-xs subtle">
            {month?.savings_rate != null
              ? t("mon.savedPct", { rate: fmtNum(month.savings_rate, 1, locale) })
              : t("mon.addIncomeHint")}
          </p>
        </div>
        <div className="card">
          <p className="text-sm muted">{t("dash.base.upcoming")}</p>
          {upcoming.length > 0 ? (
            <ul className="mt-2 space-y-1 text-sm">
              {upcoming.map((e) => (
                <li key={e.id} className="flex justify-between gap-2">
                  <span className="truncate">{e.name}</span>
                  <span className="shrink-0 tabular-nums muted">
                    {fmtMoney(e.amount_in_base, currency, locale)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm subtle">{t("exp.noneScheduled")}</p>
          )}
        </div>
      </div>
    </div>
  );
}
