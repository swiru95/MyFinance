import Link from "next/link";
import { fmtMoney, fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { FireInputs, FireResult, RequiredIncome } from "@/lib/fireTypes";

interface Props {
  result: FireResult;
  inputs: FireInputs;
  requiredIncome: RequiredIncome | null;
  base: string;
}

/** "How much should I save?" and "How much do I need to earn?" - both are
 *  null together (see services/fire.compute): required_income is only ever
 *  built when `required` itself is, so one guard covers both cards. */
export default function TwoQuestions({ result, inputs, requiredIncome, base }: Props) {
  const { t, locale } = useI18n();

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="card">
        <h2 className="text-lg font-semibold">{t("fire.q1.title")}</h2>
        {result.required ? (
          <>
            <p className="mt-2 text-2xl font-semibold tabular-nums">
              {fmtMoney(result.required.contribution, base, locale)}
              <span className="ml-1 text-sm font-normal muted">{t("fire.perMonth")}</span>
            </p>
            <p className="mt-1 text-sm muted">
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
            <details className="mt-2 text-xs subtle">
              <summary className="cursor-pointer">{t("fire.howComputed")}</summary>
              <p className="mt-1">{t("fire.q1.formula")}</p>
              <p className="mt-1">
                {t(`fire.contributionSource.${inputs.contribution_source}`)}
              </p>
            </details>
          </>
        ) : (
          <p className="mt-2 text-sm muted">{t("fire.q1.needTarget")}</p>
        )}
      </div>

      <div className="card">
        <h2 className="text-lg font-semibold">{t("fire.q2.title")}</h2>
        {result.required ? (
          <>
            <p className="mt-2 text-2xl font-semibold tabular-nums">
              {fmtMoney(result.required.required_net_income, base, locale)}
              <span className="ml-1 text-sm font-normal muted">{t("fire.perMonth")}</span>
            </p>
            {requiredIncome && (
              <table className="mt-3 w-full text-left text-sm">
                <thead className="text-xs uppercase subtle">
                  <tr>
                    <th className="py-1 font-medium">{t("fire.q2.form")}</th>
                    <th className="py-1 text-right font-medium">{t("fire.q2.monthly")}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1">{t("fire.q2.uop")}</td>
                    <td className="py-1 text-right tabular-nums">
                      {fmtMoney(requiredIncome.uop.gross_monthly ?? 0, base, locale)}
                    </td>
                  </tr>
                  <tr className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1">{t("fire.q2.b2bSkala")}</td>
                    <td className="py-1 text-right tabular-nums">
                      {fmtMoney(requiredIncome.b2b_skala.revenue_monthly ?? 0, base, locale)}
                    </td>
                  </tr>
                  <tr className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1">{t("fire.q2.b2bLiniowy")}</td>
                    <td className="py-1 text-right tabular-nums">
                      {fmtMoney(requiredIncome.b2b_liniowy.revenue_monthly ?? 0, base, locale)}
                    </td>
                  </tr>
                  <tr className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1">{t("fire.q2.b2bRyczalt")}</td>
                    <td className="py-1 text-right tabular-nums">
                      {fmtMoney(requiredIncome.b2b_ryczalt.revenue_monthly ?? 0, base, locale)}
                    </td>
                  </tr>
                </tbody>
              </table>
            )}
            <Link
              href="/tax"
              className="mt-3 inline-block text-xs font-medium text-brand-600 hover:underline"
            >
              {t("fire.q2.linkTax")}
            </Link>
          </>
        ) : (
          <p className="mt-2 text-sm muted">{t("fire.q1.needTarget")}</p>
        )}
      </div>
    </div>
  );
}
