import { useEffect, useState } from "react";
import { fmtDay, fmtMoney, fmtNum } from "@/lib/api";
import { taxApi } from "@/lib/incomeApi";
import type { TaxParams, YearCalendar } from "@/lib/incomeTypes";
import { useI18n } from "@/lib/i18n";

interface Row {
  labelKey: string;
  value: string;
}

/** The education view: every rate/threshold the engine uses for `year`,
 *  read straight off GET /api/tax/params/{year} (tax/pl/params.py), with the
 *  URL each figure was checked against. */
export default function ParamsTable({ year }: { year: number }) {
  const { t, locale } = useI18n();
  const [params, setParams] = useState<TaxParams | null>(null);
  const [calendar, setCalendar] = useState<YearCalendar | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    taxApi
      .params(year)
      .then(setParams)
      .catch((e) => setError(e instanceof Error ? e.message : t("common.failedLoad")));
    taxApi
      .calendar(year)
      .then(setCalendar)
      .catch(() => setCalendar(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  if (error) return <div className="banner-error">{error}</div>;
  if (!params) return <p className="text-sm subtle">{t("common.loading")}</p>;

  const totalWorkingDays = calendar?.reduce((sum, m) => sum + m.working_days, 0) ?? null;
  const totalWorkingHours = calendar?.reduce((sum, m) => sum + m.working_hours, 0) ?? null;
  const allHolidays = calendar
    ? calendar.flatMap((m) => m.holidays).sort((a, b) => a.date.localeCompare(b.date))
    : [];

  const pln = (v: number) => fmtMoney(v, "PLN", locale);

  const rows: Row[] = [
    { labelKey: "tax.params.minWage", value: pln(params.minimum_wage) },
    { labelKey: "tax.params.avgWageForecast", value: pln(params.avg_wage_forecast) },
    { labelKey: "tax.params.avgWageQ4", value: pln(params.avg_wage_q4_prev) },
    { labelKey: "tax.params.zusCap", value: pln(params.zus_annual_cap) },
    { labelKey: "tax.params.jdgFullBase", value: pln(params.jdg_full_base) },
    { labelKey: "tax.params.jdgPrefBase", value: pln(params.jdg_preferential_base) },
    { labelKey: "tax.params.healthMinMonthly", value: pln(params.health_min_monthly) },
    { labelKey: "tax.params.linearHealthLimit", value: pln(params.linear_health_deduction_limit) },
    {
      labelKey: "tax.params.ryczaltTiers",
      value: params.ryczalt_health_tiers.map(pln).join(" / "),
    },
    { labelKey: "tax.params.vatExemptLimit", value: pln(params.vat_exempt_limit) },
    { labelKey: "tax.params.ikeLimit", value: pln(params.ike_limit) },
    { labelKey: "tax.params.ikzeLimit", value: pln(params.ikze_limit) },
    { labelKey: "tax.params.ikzeLimitJdg", value: pln(params.ikze_limit_jdg) },
    { labelKey: "tax.params.pitThreshold", value: pln(params.pit_threshold) },
    {
      labelKey: "tax.params.pitRates",
      value: `${fmtNum(params.pit_rate_1 * 100, 0, locale)}% / ${fmtNum(params.pit_rate_2 * 100, 0, locale)}%`,
    },
    { labelKey: "tax.params.linearRate", value: `${fmtNum(params.linear_rate * 100, 0, locale)}%` },
    ...(totalWorkingDays != null && totalWorkingHours != null
      ? [
          {
            labelKey: "tax.params.workingTime",
            value: `${fmtNum(totalWorkingDays, 0, locale)} / ${fmtNum(totalWorkingHours, 0, locale)} h`,
          },
        ]
      : []),
  ];

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[24rem] text-left text-sm">
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows.map((r) => (
              <tr key={r.labelKey}>
                <td className="py-1.5 pr-3 muted">{t(r.labelKey)}</td>
                <td className="py-1.5 text-right font-medium tabular-nums">{r.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {allHolidays.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer select-none font-medium muted">
            {t("tax.params.holidays")}
          </summary>
          <ul className="mt-1 space-y-0.5">
            {allHolidays.map((h) => (
              <li key={h.date} className="flex justify-between gap-3">
                <span className="subtle">{fmtDay(h.date, locale)}</span>
                <span>{h.name}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="text-xs subtle">{t("tax.params.verifiedOn", { date: fmtDay(params.verified_on, locale) })}</p>
      <div>
        <p className="text-xs font-medium muted">{t("tax.params.sources")}</p>
        <ul className="mt-1 space-y-0.5 text-xs">
          {params.sources.map(([label, url]) => (
            <li key={url}>
              <a href={url} target="_blank" rel="noreferrer" className="text-brand-600 hover:underline dark:text-brand-300">
                {label}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
