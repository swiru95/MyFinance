import { useEffect, useState } from "react";
import { fmtMoney, fmtNum } from "@/lib/api";
import { taxApi } from "@/lib/incomeApi";
import { DEFAULT_B2B_OPTIONS, DEFAULT_UOP_OPTIONS } from "@/lib/incomeTypes";
import type { ReverseResult, TaxForm } from "@/lib/incomeTypes";
import { useI18n } from "@/lib/i18n";
import TaxDisclaimer from "./Disclaimer";

const FORM_ROWS: { key: "uop" | TaxForm; labelKey: string }[] = [
  { key: "uop", labelKey: "tax.rev.formUop" },
  { key: "skala", labelKey: "tax.rev.formSkala" },
  { key: "liniowy", labelKey: "tax.rev.formLiniowy" },
  { key: "ryczalt", labelKey: "tax.rev.formRyczalt" },
];

/** Target net per month -> what UoP gross or B2B revenue (each tax form)
 *  would need to earn to hit it, plus a hint on which B2B form is most
 *  efficient at that income and the deadline to switch forms. */
export default function ReverseCalculator() {
  const { t, locale } = useI18n();
  const year = new Date().getFullYear();

  const [targetNet, setTargetNet] = useState("8000");
  const [costsMonthly, setCostsMonthly] = useState("0");
  const [result, setResult] = useState<ReverseResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function calculate(e?: React.FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await taxApi.reverse({
        year,
        target_net_monthly: parseFloat(targetNet) || 0,
        uop_options: DEFAULT_UOP_OPTIONS,
        b2b_options: DEFAULT_B2B_OPTIONS,
        costs_monthly: parseFloat(costsMonthly) || 0,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedLoad"));
    } finally {
      setBusy(false);
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { calculate(); }, []);

  const bestForm: TaxForm | null = result
    ? (["skala", "liniowy", "ryczalt"] as TaxForm[]).reduce((best, f) =>
        result.b2b[f].revenue_monthly < result.b2b[best].revenue_monthly ? f : best
      )
    : null;
  const bestFormLabelKey =
    bestForm === "skala"
      ? "inc.form.taxFormSkala"
      : bestForm === "liniowy"
        ? "inc.form.taxFormLiniowy"
        : "inc.form.taxFormRyczalt";

  return (
    <div className="card space-y-4">
      <div>
        <h2 className="text-lg font-semibold">{t("tax.rev.title")}</h2>
        <p className="text-sm muted">{t("tax.rev.subtitle")}</p>
      </div>

      <form onSubmit={calculate} className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="rev-target">{t("tax.rev.targetNet")}</label>
          <input id="rev-target" className="input" type="number" min="0" step="100" value={targetNet} onChange={(e) => setTargetNet(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="rev-costs">{t("tax.rev.costsMonthly")}</label>
          <input id="rev-costs" className="input" type="number" min="0" step="100" value={costsMonthly} onChange={(e) => setCostsMonthly(e.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? t("tax.calculating") : t("tax.calculate")}
          </button>
        </div>
      </form>

      {error && <div className="banner-error">{error}</div>}

      {result && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[32rem] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                <tr>
                  <th className="px-3 py-2">{t("tax.rev.form")}</th>
                  <th className="px-3 py-2 text-right">{t("tax.rev.grossOrRevenue")}</th>
                  <th className="px-3 py-2 text-right">{t("tax.rev.achievedNet")}</th>
                  <th className="px-3 py-2 text-right">{t("tax.rev.effectiveRate")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {FORM_ROWS.map((row) => {
                  const data = row.key === "uop" ? result.uop : result.b2b[row.key];
                  const gross = row.key === "uop" ? result.uop.gross_monthly : result.b2b[row.key].revenue_monthly;
                  const achieved = row.key === "uop" ? result.uop.achieved_net_monthly : result.b2b[row.key].achieved_take_home_monthly;
                  const effRate = data.year.effective_rate;
                  return (
                    <tr key={row.key} className={bestForm === row.key ? "bg-emerald-50/60 dark:bg-emerald-500/10" : ""}>
                      <td className="px-3 py-2 font-medium">{t(row.labelKey)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(gross, "PLN", locale)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(achieved, "PLN", locale)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {effRate != null ? `${fmtNum(effRate * 100, 1, locale)}%` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-800">
            <p className="font-medium">{t("tax.hint.title")}</p>
            {bestForm && (
              <p className="mt-1">{t("tax.hint.best", { form: t(bestFormLabelKey) })}</p>
            )}
            <p className="mt-1 text-xs subtle">{t("tax.hint.deadline")}</p>
          </div>

          <TaxDisclaimer year={year} />
        </>
      )}
    </div>
  );
}
