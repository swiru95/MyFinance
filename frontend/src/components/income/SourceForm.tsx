import { useEffect, useState } from "react";
import { fmtMoney } from "@/lib/api";
import { incomeApi, taxApi } from "@/lib/incomeApi";
import { INPUT_CURRENCIES } from "@/lib/types";
import { useI18n } from "@/lib/i18n";
import InfoTip from "@/components/InfoTip";
import type {
  B2bIncomeParams,
  Billing,
  IncomeSource,
  Kup,
  OtherIncomeParams,
  TaxForm,
  UopIncomeParams,
  VatMode,
  ZusStage,
} from "@/lib/incomeTypes";

interface Props {
  base: string;
  existing?: IncomeSource | null;
  onDone: () => void;
  onCancel: () => void;
}

const today = () => new Date().toISOString().slice(0, 10);
const RYCZALT_RATES = [0.02, 0.03, 0.055, 0.085, 0.1, 0.12, 0.14, 0.15, 0.17];

export default function SourceForm({ base, existing, onDone, onCancel }: Props) {
  const { t, locale } = useI18n();

  const [name, setName] = useState(existing?.name ?? "");
  const [kind, setKind] = useState(existing?.kind ?? "uop");
  const [currency, setCurrency] = useState(existing?.currency ?? base);
  const [startsOn, setStartsOn] = useState(existing?.starts_on ?? today());
  const [hasEnd, setHasEnd] = useState(Boolean(existing?.ends_on));
  const [endsOn, setEndsOn] = useState(existing?.ends_on ?? "");
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const up = existing?.kind === "uop" ? (existing.params as UopIncomeParams) : null;
  const bp = existing?.kind === "b2b" ? (existing.params as B2bIncomeParams) : null;
  const op = existing?.kind === "other" ? (existing.params as OtherIncomeParams) : null;

  // uop
  const [grossMonthly, setGrossMonthly] = useState(up ? String(up.gross_monthly) : "");
  const [kup, setKup] = useState<Kup>(up?.kup ?? "standard");
  const [creativeSharePct, setCreativeSharePct] = useState(
    up ? String(up.creative_share * 100) : "0"
  );
  const [pit2, setPit2] = useState(up?.pit2 ?? true);
  const [youngRelief, setYoungRelief] = useState(up?.young_relief ?? false);
  const [ppkEmployeePct, setPpkEmployeePct] = useState(
    up ? String(up.ppk_employee * 100) : "2"
  );
  const [ppkEmployerPct, setPpkEmployerPct] = useState(
    up ? String(up.ppk_employer * 100) : "1.5"
  );

  // b2b
  const [billing, setBilling] = useState<Billing>(bp?.billing ?? "monthly");
  const [invoiceMonthly, setInvoiceMonthly] = useState(
    bp?.invoice_monthly != null ? String(bp.invoice_monthly) : ""
  );
  const [rate, setRate] = useState(bp?.rate != null ? String(bp.rate) : "");
  // Existing source with a fixed units_per_month keeps its own number by
  // default; every new source, and any existing one already left at "from
  // the calendar" (units_per_month null), starts with the calendar on.
  const [useCalendarUnits, setUseCalendarUnits] = useState(
    !bp || bp.units_per_month == null
  );
  const [unitsPerMonth, setUnitsPerMonth] = useState(
    bp?.units_per_month != null ? String(bp.units_per_month) : ""
  );
  const [calendarHint, setCalendarHint] = useState<string | null>(null);
  const [costsMonthly, setCostsMonthly] = useState(bp ? String(bp.costs_monthly) : "0");
  const [taxForm, setTaxForm] = useState<TaxForm>(bp?.tax_form ?? "liniowy");
  const [ryczaltRate, setRyczaltRate] = useState<number>(bp?.ryczalt_rate ?? 0.12);
  const [ryczaltHealthTier, setRyczaltHealthTier] = useState<number | null>(
    bp?.ryczalt_health_tier ?? null
  );
  const [zusStage, setZusStage] = useState<ZusStage>(bp?.zus_stage ?? "full");
  const [customBase, setCustomBase] = useState(
    bp?.custom_base != null ? String(bp.custom_base) : ""
  );
  const [sickness, setSickness] = useState(bp?.sickness ?? false);
  const [vat, setVat] = useState<VatMode>(bp?.vat ?? "standard");
  const [vatRatePct, setVatRatePct] = useState(bp ? String(bp.vat_rate * 100) : "23");

  // other
  const [netMonthly, setNetMonthly] = useState(op ? String(op.net_monthly) : "");

  // Mały ZUS Plus's base has to fall between the preferential and full ZUS
  // bases (tax/pl/b2b.py raises otherwise) - fetched on demand so a range
  // hint can be shown instead of a 500 the first time a schedule runs.
  const [mzpRange, setMzpRange] = useState<{ min: number; max: number } | null>(null);
  useEffect(() => {
    if (kind !== "b2b" || zusStage !== "maly_zus_plus") return;
    const year = Number(startsOn.slice(0, 4)) || new Date().getFullYear();
    taxApi
      .params(year)
      .then((p) => setMzpRange({ min: p.jdg_preferential_base, max: p.jdg_full_base }))
      .catch(() => setMzpRange(null));
  }, [kind, zusStage, startsOn]);

  // Tier amounts/thresholds for the health-tier select's option labels -
  // same on-demand fetch pattern as mzpRange above.
  const [ryczaltTierInfo, setRyczaltTierInfo] = useState<{
    tiers: [number, number, number];
    thresholds: [number, number];
  } | null>(null);
  useEffect(() => {
    if (kind !== "b2b" || taxForm !== "ryczalt") return;
    const year = Number(startsOn.slice(0, 4)) || new Date().getFullYear();
    taxApi
      .params(year)
      .then((p) =>
        setRyczaltTierInfo({ tiers: p.ryczalt_health_tiers, thresholds: p.ryczalt_tier_thresholds })
      )
      .catch(() => setRyczaltTierInfo(null));
  }, [kind, taxForm, startsOn]);

  // Hint for the "from the calendar" checkbox: this month's statutory
  // working days/hours, so switching it on isn't a leap into the unknown.
  useEffect(() => {
    if (kind !== "b2b" || billing === "monthly" || !useCalendarUnits) {
      setCalendarHint(null);
      return;
    }
    const now = new Date();
    taxApi
      .calendar(now.getFullYear())
      .then((cal) => {
        const month = cal[now.getMonth()];
        if (!month) return;
        const label = now.toLocaleDateString(locale, { month: "long", year: "numeric" });
        setCalendarHint(
          t("inc.form.calendarHint", {
            days: String(month.working_days),
            hours: String(month.working_hours),
            month: label,
          })
        );
      })
      .catch(() => setCalendarHint(null));
  }, [kind, billing, useCalendarUnits, locale, t]);

  const isOther = kind === "other";

  function buildParams(): Record<string, unknown> {
    if (kind === "uop") {
      return {
        gross_monthly: parseFloat(grossMonthly) || 0,
        kup,
        creative_share: (parseFloat(creativeSharePct) || 0) / 100,
        pit2,
        young_relief: youngRelief,
        ppk_employee: (parseFloat(ppkEmployeePct) || 0) / 100,
        ppk_employer: (parseFloat(ppkEmployerPct) || 0) / 100,
      };
    }
    if (kind === "b2b") {
      const params: Record<string, unknown> = {
        billing,
        costs_monthly: parseFloat(costsMonthly) || 0,
        tax_form: taxForm,
        ryczalt_rate: ryczaltRate,
        ryczalt_health_tier: taxForm === "ryczalt" ? ryczaltHealthTier : null,
        zus_stage: zusStage,
        custom_base: zusStage === "maly_zus_plus" ? parseFloat(customBase) || 0 : null,
        sickness,
        vat,
        vat_rate: (parseFloat(vatRatePct) || 0) / 100,
      };
      if (billing === "monthly") {
        params.invoice_monthly = parseFloat(invoiceMonthly) || 0;
      } else {
        params.rate = parseFloat(rate) || 0;
        params.units_per_month = useCalendarUnits ? null : parseFloat(unitsPerMonth) || 0;
      }
      return params;
    }
    return { net_monthly: parseFloat(netMonthly) || 0 };
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!isOther && hasEnd && endsOn && endsOn < startsOn) {
      setError(t("inc.form.endAfterStart"));
      return;
    }
    if (kind === "b2b") {
      if (billing === "monthly" && !(parseFloat(invoiceMonthly) >= 0)) {
        setError(t("inc.form.amountPositive"));
        return;
      }
      if (
        billing !== "monthly" &&
        (!(parseFloat(rate) >= 0) || (!useCalendarUnits && !(parseFloat(unitsPerMonth) >= 0)))
      ) {
        setError(t("inc.form.amountPositive"));
        return;
      }
      if (zusStage === "maly_zus_plus" && !(parseFloat(customBase) >= 0)) {
        setError(t("inc.form.amountPositive"));
        return;
      }
    }

    const payload = {
      name: name.trim(),
      kind,
      currency,
      params: buildParams(),
      starts_on: startsOn,
      ends_on: hasEnd ? endsOn || null : null,
      notes: notes.trim(),
    };

    setBusy(true);
    try {
      if (existing) await incomeApi.updateSource(existing.id, payload);
      else await incomeApi.createSource(payload);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="label" htmlFor="inc-name">{t("inc.form.name")}</label>
        <input
          id="inc-name"
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("inc.form.namePlaceholder")}
          required
        />
      </div>

      <div>
        <label className="label">{t("inc.form.kind")}</label>
        <div className="flex gap-2">
          {(["uop", "b2b", "other"] as const).map((k) => (
            <button
              key={k}
              type="button"
              disabled={Boolean(existing)}
              onClick={() => setKind(k)}
              className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-60 ${
                kind === k
                  ? "border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100"
                  : "border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              {k === "uop" ? t("inc.kindUop") : k === "b2b" ? t("inc.kindB2b") : t("inc.kindOther")}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label" htmlFor="inc-currency">{t("common.currency")}</label>
          <select
            id="inc-currency"
            className="input"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            {INPUT_CURRENCIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="inc-starts">{t("inc.form.startsOn")}</label>
          <input
            id="inc-starts"
            className="input"
            type="date"
            value={startsOn}
            onChange={(e) => setStartsOn(e.target.value)}
            required
          />
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-3">
        <div className="flex items-center gap-2">
          <input
            id="inc-has-end"
            type="checkbox"
            checked={hasEnd}
            onChange={(e) => setHasEnd(e.target.checked)}
          />
          <label htmlFor="inc-has-end" className="text-sm font-medium text-slate-700 dark:text-slate-200">
            {t("inc.form.hasEnd")}
          </label>
        </div>
        {hasEnd ? (
          <input
            className="input mt-2"
            type="date"
            value={endsOn}
            min={startsOn}
            onChange={(e) => setEndsOn(e.target.value)}
            required
          />
        ) : (
          <p className="mt-1 text-xs muted">{t("inc.form.indefiniteHint")}</p>
        )}
      </div>

      {kind === "uop" && (
        <div className="space-y-3 rounded-lg border border-sky-100 bg-sky-50/50 p-3 dark:border-sky-900/50 dark:bg-sky-500/5">
          <div>
            <label className="label" htmlFor="inc-gross">{t("inc.form.grossMonthly")}</label>
            <input
              id="inc-gross"
              className="input"
              type="number"
              step="0.01"
              min="0"
              value={grossMonthly}
              onChange={(e) => setGrossMonthly(e.target.value)}
              placeholder="0.00"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="inc-kup">
                {t("inc.form.kup")}
                <InfoTip text={t("gloss.kup")} label={t("inc.form.kup")} />
              </label>
              <select id="inc-kup" className="input" value={kup} onChange={(e) => setKup(e.target.value as Kup)}>
                <option value="standard">{t("inc.form.kupStandard")}</option>
                <option value="commuting">{t("inc.form.kupCommuting")}</option>
              </select>
            </div>
            <div>
              <label className="label" htmlFor="inc-creative">{t("inc.form.creativeShare")}</label>
              <input
                id="inc-creative"
                className="input"
                type="number"
                step="1"
                min="0"
                max="100"
                value={creativeSharePct}
                onChange={(e) => setCreativeSharePct(e.target.value)}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={pit2} onChange={(e) => setPit2(e.target.checked)} />
              {t("inc.form.pit2")}
              <InfoTip text={t("gloss.pit2")} label={t("inc.form.pit2")} />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={youngRelief}
                onChange={(e) => setYoungRelief(e.target.checked)}
              />
              {t("inc.form.youngRelief")}
            </label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="inc-ppk-emp">
                {t("inc.form.ppkEmployee")}
                <InfoTip text={t("gloss.ppk")} label={t("inc.form.ppkEmployee")} />
              </label>
              <input
                id="inc-ppk-emp"
                className="input"
                type="number"
                step="0.1"
                min="0"
                max="2"
                value={ppkEmployeePct}
                onChange={(e) => setPpkEmployeePct(e.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="inc-ppk-empr">{t("inc.form.ppkEmployer")}</label>
              <input
                id="inc-ppk-empr"
                className="input"
                type="number"
                step="0.1"
                min="0"
                max="1.5"
                value={ppkEmployerPct}
                onChange={(e) => setPpkEmployerPct(e.target.value)}
              />
            </div>
          </div>
          {parseFloat(ppkEmployeePct) === 0 && (
            <p className="text-xs muted">{t("inc.form.ppkOptOutHint")}</p>
          )}
        </div>
      )}

      {kind === "b2b" && (
        <div className="space-y-3 rounded-lg border border-violet-100 bg-violet-50/50 p-3 dark:border-violet-900/50 dark:bg-violet-500/5">
          <div>
            <label className="label">{t("inc.form.billing")}</label>
            <div className="flex gap-2">
              {(["monthly", "daily", "hourly"] as Billing[]).map((b) => (
                <button
                  key={b}
                  type="button"
                  onClick={() => setBilling(b)}
                  className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium transition ${
                    billing === b
                      ? "border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100"
                      : "border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                  }`}
                >
                  {b === "monthly"
                    ? t("inc.form.billingMonthly")
                    : b === "daily"
                      ? t("inc.form.billingDaily")
                      : t("inc.form.billingHourly")}
                </button>
              ))}
            </div>
          </div>

          {billing === "monthly" ? (
            <div>
              <label className="label" htmlFor="inc-invoice">{t("inc.form.invoiceMonthly")}</label>
              <input
                id="inc-invoice"
                className="input"
                type="number"
                step="0.01"
                min="0"
                value={invoiceMonthly}
                onChange={(e) => setInvoiceMonthly(e.target.value)}
                placeholder="0.00"
                required
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label" htmlFor="inc-rate">{t("inc.form.rate")}</label>
                <input
                  id="inc-rate"
                  className="input"
                  type="number"
                  step="0.01"
                  min="0"
                  value={rate}
                  onChange={(e) => setRate(e.target.value)}
                  placeholder="0.00"
                  required
                />
              </div>
              <div>
                <label className="label" htmlFor="inc-units">{t("inc.form.unitsPerMonth")}</label>
                <input
                  id="inc-units"
                  className="input"
                  type="number"
                  step="0.5"
                  min="0"
                  value={unitsPerMonth}
                  onChange={(e) => setUnitsPerMonth(e.target.value)}
                  disabled={useCalendarUnits}
                  required={!useCalendarUnits}
                />
                <label className="mt-1 flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={useCalendarUnits}
                    onChange={(e) => setUseCalendarUnits(e.target.checked)}
                  />
                  {t("inc.form.useCalendar")}
                </label>
                {useCalendarUnits && calendarHint && (
                  <p className="mt-1 text-xs subtle">{calendarHint}</p>
                )}
              </div>
            </div>
          )}

          <div>
            <label className="label" htmlFor="inc-costs">{t("inc.form.costsMonthly")}</label>
            <input
              id="inc-costs"
              className="input"
              type="number"
              step="0.01"
              min="0"
              value={costsMonthly}
              onChange={(e) => setCostsMonthly(e.target.value)}
              placeholder="0.00"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="inc-taxform">
                {t("inc.form.taxForm")}
                <InfoTip text={t("gloss.taxForm")} label={t("inc.form.taxForm")} />
              </label>
              <select
                id="inc-taxform"
                className="input"
                value={taxForm}
                onChange={(e) => setTaxForm(e.target.value as TaxForm)}
              >
                <option value="skala">{t("inc.form.taxFormSkala")}</option>
                <option value="liniowy">{t("inc.form.taxFormLiniowy")}</option>
                <option value="ryczalt">{t("inc.form.taxFormRyczalt")}</option>
              </select>
            </div>
            {taxForm === "ryczalt" && (
              <div>
                <label className="label" htmlFor="inc-ryczalt-rate">{t("inc.form.ryczaltRate")}</label>
                <select
                  id="inc-ryczalt-rate"
                  className="input"
                  value={ryczaltRate}
                  onChange={(e) => setRyczaltRate(parseFloat(e.target.value))}
                >
                  {RYCZALT_RATES.map((r) => (
                    <option key={r} value={r}>{(r * 100).toFixed(1)}%</option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {taxForm === "ryczalt" && (
            <div>
              <label className="label" htmlFor="inc-ryczalt-health-tier">
                {t("inc.form.ryczaltHealthTier")}
              </label>
              <select
                id="inc-ryczalt-health-tier"
                className="input"
                value={ryczaltHealthTier ?? "auto"}
                onChange={(e) =>
                  setRyczaltHealthTier(e.target.value === "auto" ? null : Number(e.target.value))
                }
              >
                <option value="auto">{t("inc.form.ryczaltHealthTierAuto")}</option>
                {ryczaltTierInfo &&
                  ([1, 2, 3] as const).map((tier) => (
                    <option key={tier} value={tier}>
                      {t("inc.form.ryczaltHealthTierOption", {
                        tier: String(tier),
                        amount: fmtMoney(ryczaltTierInfo.tiers[tier - 1], "PLN", locale),
                        range:
                          tier === 1
                            ? t("inc.form.ryczaltHealthTierRangeTier1", {
                                max: fmtMoney(ryczaltTierInfo.thresholds[0], "PLN", locale),
                              })
                            : tier === 2
                              ? t("inc.form.ryczaltHealthTierRangeTier2", {
                                  min: fmtMoney(ryczaltTierInfo.thresholds[0], "PLN", locale),
                                  max: fmtMoney(ryczaltTierInfo.thresholds[1], "PLN", locale),
                                })
                              : t("inc.form.ryczaltHealthTierRangeTier3", {
                                  min: fmtMoney(ryczaltTierInfo.thresholds[1], "PLN", locale),
                                }),
                      })}
                    </option>
                  ))}
              </select>
              <p className="mt-1 text-xs muted">{t("inc.form.ryczaltHealthTierHint")}</p>
            </div>
          )}

          <div>
            <label className="label" htmlFor="inc-zus-stage">
              {t("inc.form.zusStage")}
              <InfoTip text={t("gloss.zusStage")} label={t("inc.form.zusStage")} />
            </label>
            <select
              id="inc-zus-stage"
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
          {zusStage === "maly_zus_plus" && (
            <div>
              <label className="label" htmlFor="inc-custom-base">{t("inc.form.customBase")}</label>
              <input
                id="inc-custom-base"
                className="input"
                type="number"
                step="0.01"
                min="0"
                value={customBase}
                onChange={(e) => setCustomBase(e.target.value)}
                required
              />
              {mzpRange && (
                <p className="mt-1 text-xs muted">
                  {t("inc.form.customBaseHint", {
                    min: fmtMoney(mzpRange.min, "PLN", locale),
                    max: fmtMoney(mzpRange.max, "PLN", locale),
                    year: startsOn.slice(0, 4),
                  })}
                </p>
              )}
            </div>
          )}

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={sickness} onChange={(e) => setSickness(e.target.checked)} />
            {t("inc.form.sickness")}
          </label>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="inc-vat">{t("inc.form.vat")}</label>
              <select id="inc-vat" className="input" value={vat} onChange={(e) => setVat(e.target.value as VatMode)}>
                <option value="standard">{t("inc.form.vatStandard")}</option>
                <option value="exempt">{t("inc.form.vatExempt")}</option>
                <option value="reverse_charge">{t("inc.form.vatReverseCharge")}</option>
              </select>
            </div>
            {vat === "standard" && (
              <div>
                <label className="label" htmlFor="inc-vat-rate">{t("inc.form.vatRate")}</label>
                <input
                  id="inc-vat-rate"
                  className="input"
                  type="number"
                  step="1"
                  min="0"
                  max="100"
                  value={vatRatePct}
                  onChange={(e) => setVatRatePct(e.target.value)}
                />
              </div>
            )}
          </div>
        </div>
      )}

      {isOther && (
        <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-800/40">
          <div>
            <label className="label" htmlFor="inc-net">{t("inc.form.netMonthly")}</label>
            <input
              id="inc-net"
              className="input"
              type="number"
              step="0.01"
              min="0"
              value={netMonthly}
              onChange={(e) => setNetMonthly(e.target.value)}
              placeholder="0.00"
              required
            />
          </div>
          <p className="text-xs muted">{t("inc.form.otherHint")}</p>
        </div>
      )}

      <div>
        <label className="label" htmlFor="inc-notes">{t("common.notes")}</label>
        <input
          id="inc-notes"
          className="input"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button type="button" onClick={onCancel} className="btn-ghost flex-1">
          {t("common.cancel")}
        </button>
        <button type="submit" className="btn-primary flex-1" disabled={busy}>
          {busy
            ? t("common.saving")
            : existing
              ? t("inc.form.saveChanges")
              : t("inc.form.addButton")}
        </button>
      </div>
    </form>
  );
}
