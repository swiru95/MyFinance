import { fmtDay, fmtMoney } from "@/lib/api";
import { monthLabel } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";
import type { IncomeSummary } from "@/lib/incomeTypes";
import InfoTip from "@/components/InfoTip";

interface Props {
  summary: IncomeSummary;
}

const COMPONENTS: { key: "zus" | "pit" | "vat"; labelKey: string }[] = [
  { key: "zus", labelKey: "inc.envelope.zus" },
  { key: "pit", labelKey: "inc.envelope.pit" },
  { key: "vat", labelKey: "inc.envelope.vat" },
];

/** "Money on your account that is not yours": the previous and current
 *  month's ZUS/health, PIT and VAT for every b2b source, from
 *  GET /api/income/summary's `envelope` - shown only when a b2b source
 *  exists (gated by the caller). */
export default function TaxEnvelope({ summary }: Props) {
  const { t, locale } = useI18n();
  const base = summary.base_currency;

  return (
    <div className="card space-y-3">
      <div>
        <h2 className="flex items-center text-lg font-semibold">
          {t("inc.envelope.title")}
          <InfoTip text={t("gloss.taxEnvelope")} label={t("inc.envelope.title")} />
        </h2>
        <p className="text-sm muted">{t("inc.envelope.explain")}</p>
      </div>
      {summary.envelope.length === 0 ? (
        <p className="text-sm subtle">{t("inc.envelope.empty")}</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[28rem] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="py-1 pr-3">{t("inc.schedule.source")}</th>
                  <th className="py-1 pr-3">{t("inc.schedule.month")}</th>
                  {COMPONENTS.map((c) => (
                    <th key={c.key} className="py-1 pr-3 text-right">{t(c.labelKey)}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {summary.envelope.map((item, idx) => (
                  <tr key={`${item.source_id}-${item.month}-${idx}`}>
                    <td className="py-1.5 pr-3 font-medium">{item.name}</td>
                    <td className="py-1.5 pr-3">{monthLabel(item.month, locale)}</td>
                    {COMPONENTS.map((c) => {
                      const comp = item[c.key];
                      const passed = comp.status === "paid_window_passed";
                      return (
                        <td key={c.key} className="py-1.5 pr-3 text-right tabular-nums">
                          <span className={passed ? "subtle" : ""}>
                            {fmtMoney(comp.amount_in_base, base, locale)}
                          </span>
                          <span className="block text-[10px] subtle">
                            {passed
                              ? t("inc.envelope.windowPassed")
                              : t("inc.envelope.due", { date: fmtDay(comp.due_date, locale) })}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex justify-between border-t border-slate-200 pt-2 text-sm font-semibold dark:border-slate-800">
            <span>{t("inc.envelope.total")}</span>
            <span className="tabular-nums">
              {fmtMoney(summary.envelope_outstanding_in_base, base, locale)}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
