import { fmtMoney, fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { FireInputs, FireResult } from "@/lib/fireTypes";

interface Props {
  result: FireResult;
  inputs: FireInputs;
  base: string;
}

/** The top FIRE layer (round 2 spec item 8): three plain answers - how much
 *  you need, when you get there, how much to put aside each month - plus
 *  the progress bar, all in one glance with nothing collapsed. The Coast FI
 *  tile that used to sit here moved to VariantCards under "Details": it is
 *  a variant on the FI number, not one of the three headline answers, and
 *  VariantCards already prices it out with the same figure. "How much to
 *  put aside" is former TwoQuestions' q1 card, folded in here rather than
 *  left as a fourth item below the fold - see RequiredIncomeCard.tsx for
 *  its sibling q2 (how much to *earn*), which stayed under Details since it
 *  is a step further than the three headline answers. */
export default function HeadlineStats({ result, inputs, base }: Props) {
  const { t, locale } = useI18n();
  const progressPct =
    result.progress != null ? Math.max(0, Math.min(result.progress * 100, 100)) : null;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div className="card">
        <p className="text-sm muted">{t("fire.stat.fiNumber")}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">
          {fmtMoney(result.targets.regular, base, locale)}
        </p>
        <p className="mt-1 text-xs subtle">
          {t("fire.stat.fiNumberAt", { age: fmtNum(result.targets_age, 0, locale) })}
        </p>
      </div>

      <div className="card">
        <p className="text-sm muted">{t("fire.stat.progress")}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">
          {progressPct != null ? `${fmtNum(progressPct, 0, locale)}%` : "—"}
        </p>
        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
          <div
            className="h-full rounded-full bg-brand-600"
            style={{ width: `${progressPct ?? 0}%` }}
          />
        </div>
      </div>

      <div className="card">
        <p className="text-sm muted">{t("fire.stat.yearsToFi")}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">
          {result.simulate.years != null && result.simulate.fi_age != null
            ? t("fire.stat.yearsValue", {
                years: fmtNum(result.simulate.years, 1, locale),
                age: fmtNum(result.simulate.fi_age, 0, locale),
              })
            : "—"}
        </p>
        {result.simulate.years == null && (
          <p className="mt-1 text-xs subtle">{t("fire.stat.notReachable")}</p>
        )}
      </div>

      <div className="card">
        <p className="text-sm muted">{t("fire.q1.title")}</p>
        {result.required ? (
          <>
            <p className="mt-1 text-2xl font-semibold tabular-nums">
              {fmtMoney(result.required.contribution, base, locale)}
              <span className="ml-1 text-sm font-normal muted">{t("fire.perMonth")}</span>
            </p>
            <p className="mt-1 text-xs subtle">
              {t("fire.q1.rateVsCurrent", {
                required:
                  result.required.savings_rate != null
                    ? `${fmtNum(result.required.savings_rate * 100, 0, locale)}%`
                    : "—",
                current:
                  result.current_savings_rate != null
                    ? `${fmtNum(result.current_savings_rate * 100, 0, locale)}%`
                    : "—",
              })}
            </p>
            <details className="mt-1 text-xs subtle">
              <summary className="cursor-pointer">{t("fire.howComputed")}</summary>
              <p className="mt-1">{t("fire.q1.formula")}</p>
              <p className="mt-1">
                {t(`fire.contributionSource.${inputs.contribution_source}`)}
              </p>
            </details>
          </>
        ) : (
          <p className="mt-1 text-sm muted">{t("fire.q1.needTarget")}</p>
        )}
      </div>
    </div>
  );
}
