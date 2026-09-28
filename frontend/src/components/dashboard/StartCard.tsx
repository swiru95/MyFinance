import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { api } from "@/lib/api";
import { incomeApi } from "@/lib/incomeApi";
import { useI18n } from "@/lib/i18n";
import { useSettings } from "@/components/SettingsProvider";
import { useStoredBool } from "@/lib/useStoredBool";
import {
  DEFAULT_B2B_OPTIONS,
  DEFAULT_UOP_OPTIONS,
} from "@/lib/incomeTypes";
import type { TaxForm, ZusStage } from "@/lib/incomeTypes";
import InfoTip from "@/components/InfoTip";

type Step = "choose" | "uop" | "b2b" | "done";

const today = () => new Date().toISOString().slice(0, 10);

/** First-run start card (round 2 spec item 6): shown in place of a wall of
 *  empty tiles when the wallet has no income sources, no expenses and no
 *  positions yet. Fetches those three lists itself, the same self-contained
 *  pattern BaseSummary and NextStepTile already use on this page, so
 *  pages/index.tsx only needs one extra line to render it - it owns the
 *  price tiles below and round 2 is asked to touch that file as little as
 *  possible while another agent works on it concurrently.
 *
 *  Dismissal is a plain localStorage flag (see useStoredBool), not a
 *  Settings field: it is a one-time "I've seen this, stop asking" nudge for
 *  this browser, not data - it doesn't need to sync across devices or
 *  survive a server backup/restore the way a real setting would. */
export default function StartCard() {
  const { t } = useI18n();
  const router = useRouter();
  const { baseCurrency } = useSettings();
  const [dismissed, setDismissed] = useStoredBool("myfinance-start-card-dismissed", false);
  const [empty, setEmpty] = useState(false);
  const [checked, setChecked] = useState(false);
  const [step, setStep] = useState<Step>("choose");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // uop
  const [grossMonthly, setGrossMonthly] = useState("");
  const [uopStartsOn, setUopStartsOn] = useState(today());

  // b2b
  const [invoiceMonthly, setInvoiceMonthly] = useState("");
  const [taxForm, setTaxForm] = useState<TaxForm>(DEFAULT_B2B_OPTIONS.tax_form);
  const [zusStage, setZusStage] = useState<ZusStage>(DEFAULT_B2B_OPTIONS.zus_stage);
  const [b2bStartsOn, setB2bStartsOn] = useState(today());

  useEffect(() => {
    let alive = true;
    async function check() {
      try {
        const [sources, expenses, positions] = await Promise.all([
          incomeApi.sources(),
          api.expenses(),
          api.positions(),
        ]);
        if (alive) {
          setEmpty(sources.length === 0 && expenses.length === 0 && positions.length === 0);
        }
      } catch {
        // If the check itself fails, say nothing rather than risk nagging
        // someone who already has data - the rest of the dashboard already
        // surfaces the real error.
      } finally {
        if (alive) setChecked(true);
      }
    }
    check();
    return () => {
      alive = false;
    };
  }, []);

  if (dismissed || !checked || !empty) return null;

  async function createUop(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await incomeApi.createSource({
        name: t("start.uop.defaultName"),
        kind: "uop",
        currency: baseCurrency,
        params: {
          ...DEFAULT_UOP_OPTIONS,
          gross_monthly: parseFloat(grossMonthly) || 0,
        },
        starts_on: uopStartsOn,
        ends_on: null,
        notes: "",
      });
      setStep("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(false);
    }
  }

  async function createB2b(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await incomeApi.createSource({
        name: t("start.b2b.defaultName"),
        kind: "b2b",
        currency: baseCurrency,
        params: {
          ...DEFAULT_B2B_OPTIONS,
          tax_form: taxForm,
          zus_stage: zusStage,
          billing: "monthly",
          invoice_monthly: parseFloat(invoiceMonthly) || 0,
          rate: null,
          units_per_month: null,
          costs_monthly: 0,
        },
        starts_on: b2bStartsOn,
        ends_on: null,
        notes: "",
      });
      setStep("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(false);
    }
  }

  function spendingOnly() {
    router.push("/expenses?add=1");
  }

  return (
    <div className="card border-brand-200 bg-brand-50/40 dark:border-brand-900/50 dark:bg-brand-500/5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t("start.title")}</h2>
          {step === "choose" && <p className="mt-1 text-sm muted">{t("start.subtitle")}</p>}
        </div>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="subtle shrink-0 text-sm"
          aria-label={t("start.dismiss")}
        >
          {t("start.dismiss")}
        </button>
      </div>

      {step === "choose" && (
        <div className="grid gap-3 sm:grid-cols-3">
          <button
            type="button"
            onClick={() => setStep("uop")}
            className="rounded-lg border border-slate-200 bg-white p-4 text-left transition hover:border-brand-300 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-brand-700"
          >
            <p className="font-semibold">{t("start.uop.title")}</p>
            <p className="mt-1 text-xs muted">{t("start.uop.desc")}</p>
          </button>
          <button
            type="button"
            onClick={() => setStep("b2b")}
            className="rounded-lg border border-slate-200 bg-white p-4 text-left transition hover:border-brand-300 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-brand-700"
          >
            <p className="font-semibold">{t("start.b2b.title")}</p>
            <p className="mt-1 text-xs muted">{t("start.b2b.desc")}</p>
          </button>
          <button
            type="button"
            onClick={spendingOnly}
            className="rounded-lg border border-slate-200 bg-white p-4 text-left transition hover:border-brand-300 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-brand-700"
          >
            <p className="font-semibold">{t("start.spending.title")}</p>
            <p className="mt-1 text-xs muted">{t("start.spending.desc")}</p>
          </button>
        </div>
      )}

      {step === "uop" && (
        <form onSubmit={createUop} className="space-y-3">
          <div>
            <label className="label" htmlFor="start-uop-gross">{t("start.uop.grossLabel")}</label>
            <input
              id="start-uop-gross"
              className="input"
              type="number"
              step="0.01"
              min="0"
              value={grossMonthly}
              onChange={(e) => setGrossMonthly(e.target.value)}
              placeholder="0.00"
              autoFocus
              required
            />
          </div>
          <div>
            <label className="label" htmlFor="start-uop-starts">{t("inc.form.startsOn")}</label>
            <input
              id="start-uop-starts"
              className="input"
              type="date"
              value={uopStartsOn}
              onChange={(e) => setUopStartsOn(e.target.value)}
              required
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-2">
            <button type="button" onClick={() => setStep("choose")} className="btn-ghost flex-1">
              {t("common.cancel")}
            </button>
            <button type="submit" className="btn-primary flex-1" disabled={busy}>
              {busy ? t("common.saving") : t("start.create")}
            </button>
          </div>
        </form>
      )}

      {step === "b2b" && (
        <form onSubmit={createB2b} className="space-y-3">
          <div>
            <label className="label" htmlFor="start-b2b-invoice">{t("start.b2b.invoiceLabel")}</label>
            <input
              id="start-b2b-invoice"
              className="input"
              type="number"
              step="0.01"
              min="0"
              value={invoiceMonthly}
              onChange={(e) => setInvoiceMonthly(e.target.value)}
              placeholder="0.00"
              autoFocus
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="start-b2b-taxform">
                {t("inc.form.taxForm")}
                <InfoTip text={t("gloss.taxForm")} label={t("inc.form.taxForm")} />
              </label>
              <select
                id="start-b2b-taxform"
                className="input"
                value={taxForm}
                onChange={(e) => setTaxForm(e.target.value as TaxForm)}
              >
                <option value="skala">{t("inc.form.taxFormSkala")}</option>
                <option value="liniowy">{t("inc.form.taxFormLiniowy")}</option>
                <option value="ryczalt">{t("inc.form.taxFormRyczalt")}</option>
              </select>
            </div>
            <div>
              <label className="label" htmlFor="start-b2b-zus">
                {t("inc.form.zusStage")}
                <InfoTip text={t("gloss.zusStage")} label={t("inc.form.zusStage")} />
              </label>
              <select
                id="start-b2b-zus"
                className="input"
                value={zusStage}
                onChange={(e) => setZusStage(e.target.value as ZusStage)}
              >
                <option value="start">{t("inc.form.zusStart")}</option>
                <option value="preferential">{t("inc.form.zusPreferential")}</option>
                <option value="maly_zus_plus">{t("inc.form.zusMzp")}</option>
                <option value="full">{t("inc.form.zusFull")}</option>
              </select>
            </div>
          </div>
          <div>
            <label className="label" htmlFor="start-b2b-starts">{t("inc.form.startsOn")}</label>
            <input
              id="start-b2b-starts"
              className="input"
              type="date"
              value={b2bStartsOn}
              onChange={(e) => setB2bStartsOn(e.target.value)}
              required
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-2">
            <button type="button" onClick={() => setStep("choose")} className="btn-ghost flex-1">
              {t("common.cancel")}
            </button>
            <button type="submit" className="btn-primary flex-1" disabled={busy}>
              {busy ? t("common.saving") : t("start.create")}
            </button>
          </div>
        </form>
      )}

      {step === "done" && (
        <div className="space-y-3">
          <p className="text-sm">{t("start.done")}</p>
          <button
            type="button"
            onClick={spendingOnly}
            className="btn-primary"
          >
            {t("start.addFirstExpense")}
          </button>
        </div>
      )}
    </div>
  );
}
