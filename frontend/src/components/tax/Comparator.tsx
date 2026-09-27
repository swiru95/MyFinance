import { useEffect, useState } from "react";
import { fmtMoney } from "@/lib/api";
import { taxApi } from "@/lib/incomeApi";
import { DEFAULT_B2B_OPTIONS, DEFAULT_UOP_OPTIONS } from "@/lib/incomeTypes";
import type { CompareResult, TaxForm, ZusStage } from "@/lib/incomeTypes";
import { useI18n } from "@/lib/i18n";
import TaxDisclaimer from "./Disclaimer";

const RYCZALT_RATES = [0.02, 0.03, 0.055, 0.085, 0.1, 0.12, 0.14, 0.15, 0.17];

/** UoP <-> B2B side by side: what a given gross and a given revenue actually
 *  leave you, plus the equivalent revenue B2B would need to match UoP's net
 *  and what that trade costs the ZUS pension account. */
export default function Comparator() {
  const { t, locale } = useI18n();
  const year = new Date().getFullYear();

  const [uopGross, setUopGross] = useState("15000");
  const [b2bRevenue, setB2bRevenue] = useState("20000");
  const [b2bCosts, setB2bCosts] = useState("0");
  const [taxForm, setTaxForm] = useState<TaxForm>("liniowy");
  const [ryczaltRate, setRyczaltRate] = useState(0.12);
  const [zusStage, setZusStage] = useState<ZusStage>("full");
  const [customBase, setCustomBase] = useState("");
  const [sickness, setSickness] = useState(false);
  const [paidLeaveDays, setPaidLeaveDays] = useState("26");
  const [workingDays, setWorkingDays] = useState("250");
  const [billedPerDay, setBilledPerDay] = useState(true);

  const [result, setResult] = useState<CompareResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function calculate(e?: React.FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await taxApi.compare({
        year,
        uop_gross_monthly: parseFloat(uopGross) || 0,
        uop_options: DEFAULT_UOP_OPTIONS,
        b2b_revenue_monthly: parseFloat(b2bRevenue) || 0,
        b2b_costs_monthly: parseFloat(b2bCosts) || 0,
        b2b_options: {
          ...DEFAULT_B2B_OPTIONS,
          tax_form: taxForm,
          ryczalt_rate: ryczaltRate,
          zus_stage: zusStage,
          custom_base: zusStage === "maly_zus_plus" ? parseFloat(customBase) || 0 : null,
          sickness,
        },
        paid_leave_days: parseInt(paidLeaveDays, 10) || 0,
        working_days: parseInt(workingDays, 10) || 1,
        b2b_billed_per_day: billedPerDay,
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

  return (
    <div className="card space-y-4">
      <div>
        <h2 className="text-lg font-semibold">{t("tax.cmp.title")}</h2>
        <p className="text-sm muted">{t("tax.cmp.subtitle")}</p>
      </div>

      <form onSubmit={calculate} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <label className="label" htmlFor="cmp-uop">{t("tax.cmp.uopGross")}</label>
          <input id="cmp-uop" className="input" type="number" min="0" step="100" value={uopGross} onChange={(e) => setUopGross(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="cmp-rev">{t("tax.cmp.b2bRevenue")}</label>
          <input id="cmp-rev" className="input" type="number" min="0" step="100" value={b2bRevenue} onChange={(e) => setB2bRevenue(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="cmp-costs">{t("tax.cmp.b2bCosts")}</label>
          <input id="cmp-costs" className="input" type="number" min="0" step="100" value={b2bCosts} onChange={(e) => setB2bCosts(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="cmp-form">{t("inc.form.taxForm")}</label>
          <select id="cmp-form" className="input" value={taxForm} onChange={(e) => setTaxForm(e.target.value as TaxForm)}>
            <option value="skala">{t("inc.form.taxFormSkala")}</option>
            <option value="liniowy">{t("inc.form.taxFormLiniowy")}</option>
            <option value="ryczalt">{t("inc.form.taxFormRyczalt")}</option>
          </select>
        </div>
        {taxForm === "ryczalt" && (
          <div>
            <label className="label" htmlFor="cmp-ryczalt">{t("inc.form.ryczaltRate")}</label>
            <select id="cmp-ryczalt" className="input" value={ryczaltRate} onChange={(e) => setRyczaltRate(parseFloat(e.target.value))}>
              {RYCZALT_RATES.map((r) => (
                <option key={r} value={r}>{(r * 100).toFixed(1)}%</option>
              ))}
            </select>
          </div>
        )}
        <div>
          <label className="label" htmlFor="cmp-zus">{t("inc.form.zusStage")}</label>
          <select id="cmp-zus" className="input" value={zusStage} onChange={(e) => setZusStage(e.target.value as ZusStage)}>
            <option value="start">{t("inc.form.zusStart")}</option>
            <option value="preferential">{t("inc.form.zusPreferential")}</option>
            <option value="maly_zus_plus">{t("inc.form.zusMzp")}</option>
            <option value="full">{t("inc.form.zusFull")}</option>
          </select>
        </div>
        {zusStage === "maly_zus_plus" && (
          <div>
            <label className="label" htmlFor="cmp-custom-base">{t("inc.form.customBase")}</label>
            <input id="cmp-custom-base" className="input" type="number" min="0" step="0.01" value={customBase} onChange={(e) => setCustomBase(e.target.value)} />
          </div>
        )}
        <div>
          <label className="label" htmlFor="cmp-leave">{t("tax.cmp.paidLeave")}</label>
          <input id="cmp-leave" className="input" type="number" min="0" step="1" value={paidLeaveDays} onChange={(e) => setPaidLeaveDays(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="cmp-workdays">{t("tax.cmp.workingDays")}</label>
          <input id="cmp-workdays" className="input" type="number" min="1" step="1" value={workingDays} onChange={(e) => setWorkingDays(e.target.value)} />
        </div>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input type="checkbox" checked={sickness} onChange={(e) => setSickness(e.target.checked)} />
          {t("inc.form.sickness")}
        </label>
        <label className="flex items-center gap-2 self-end pb-2 text-sm sm:col-span-2 lg:col-span-1">
          <input type="checkbox" checked={billedPerDay} onChange={(e) => setBilledPerDay(e.target.checked)} />
          {t("tax.cmp.billedPerDay")}
        </label>
        <div className="sm:col-span-2 lg:col-span-3">
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? t("tax.calculating") : t("tax.calculate")}
          </button>
        </div>
      </form>

      {error && <div className="banner-error">{error}</div>}

      {result && (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-xs muted">{t("tax.cmp.uopAnnualNet")}</p>
              <p className="font-semibold tabular-nums">{fmtMoney(result.uop_annual_net, "PLN", locale)}</p>
            </div>
            <div>
              <p className="text-xs muted">{t("tax.cmp.uopEmployerCost")}</p>
              <p className="font-semibold tabular-nums">{fmtMoney(result.uop_employer_cost_annual, "PLN", locale)}</p>
            </div>
            <div>
              <p className="text-xs muted">{t("tax.cmp.b2bAnnualTakeHome")}</p>
              <p className="font-semibold tabular-nums">{fmtMoney(result.b2b_annual_take_home, "PLN", locale)}</p>
            </div>
            <div>
              <p className="text-xs muted">{t("tax.cmp.difference")}</p>
              <p className={`font-semibold tabular-nums ${result.difference_net_annual >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                {fmtMoney(result.difference_net_annual, "PLN", locale)}
              </p>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
              <p className="text-xs muted">{t("tax.cmp.equivalentRevenue")}</p>
              <p className="text-lg font-semibold tabular-nums">{fmtMoney(result.b2b_equivalent_revenue_monthly, "PLN", locale)}</p>
              <p className="mt-1 text-xs subtle">{t("tax.cmp.equivalentHint")}</p>
            </div>
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-900/50 dark:bg-amber-500/10">
              <p className="text-xs muted">{t("tax.cmp.pensionGap")}</p>
              <p className="text-lg font-semibold tabular-nums">{fmtMoney(result.pension_gap_annual, "PLN", locale)}</p>
              <p className="mt-1 text-xs subtle">{t("tax.cmp.pensionGapNote")}</p>
            </div>
          </div>
          <TaxDisclaimer year={year} />
        </div>
      )}
    </div>
  );
}
