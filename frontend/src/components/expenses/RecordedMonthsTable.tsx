import { fmtMoney, fmtNum } from "@/lib/api";
import type { MonthlyRecord } from "@/lib/types";
import { monthLabel } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";

interface Props {
  months: MonthlyRecord[];
  base: string;
}

/** Table view: also the accessibility relief for the light-mode palette. */
export default function RecordedMonthsTable({ months, base }: Props) {
  const { t, locale } = useI18n();
  const recorded = months.filter((m) => m.saved);

  return (
    <div className="card p-0">
      <h3 className="border-b border-slate-200 px-5 py-3 text-lg font-semibold dark:border-slate-800">
        {t("mon.recorded")}
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[34rem] text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            <tr>
              <th className="px-5 py-2">{t("mon.tblMonth")}</th>
              <th className="px-5 py-2 text-right">{t("mon.tblIncome")}</th>
              <th className="px-5 py-2 text-right">{t("mon.tblActual")}</th>
              <th className="px-5 py-2 text-right">{t("mon.tblEffective")}</th>
              <th className="px-5 py-2 text-right">{t("mon.tblCommitted")}</th>
              <th className="px-5 py-2 text-right">{t("mon.tblSurplus")}</th>
              <th className="px-5 py-2 text-right">{t("mon.tblSaved")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {recorded.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-5 py-6 text-center text-sm subtle">
                  {t("mon.tblEmpty")}
                </td>
              </tr>
            ) : (
              recorded.map((m) => (
                <tr key={m.month}>
                  <td className="px-5 py-2 font-medium">{monthLabel(m.month, locale)}</td>
                  <td className="px-5 py-2 text-right tabular-nums">
                    {fmtMoney(m.income_in_base, base, locale)}
                  </td>
                  <td className="px-5 py-2 text-right tabular-nums">
                    {fmtMoney(m.actual_in_base, base, locale)}
                  </td>
                  <td className="px-5 py-2 text-right tabular-nums">
                    {m.effective_spent != null
                      ? fmtMoney(m.effective_spent, base, locale)
                      : "—"}
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
  );
}
