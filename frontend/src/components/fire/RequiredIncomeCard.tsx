import Link from "next/link";
import { fmtMoney } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { RequiredIncome } from "@/lib/fireTypes";

interface Props {
  requiredIncome: RequiredIncome | null;
  base: string;
}

/** "How much do I need to earn?" (the required-saving question moved to the
 *  headline layer - see HeadlineStats.tsx's required-saving tile, which is
 *  the sibling this component used to sit next to as "Two questions"). Kept
 *  under fire.tsx's "Details" disclosure: a form-by-form income table is a
 *  step further than the plain top-layer answers, closer to /tax territory
 *  (it links there) than to "how much do I need and when". */
export default function RequiredIncomeCard({ requiredIncome, base }: Props) {
  const { t, locale } = useI18n();

  return (
    <div className="card">
      <h2 className="text-lg font-semibold">{t("fire.q2.title")}</h2>
      {requiredIncome ? (
        <>
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
  );
}
