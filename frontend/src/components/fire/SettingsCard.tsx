import { useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n";
import type { FireSettings } from "@/lib/fireTypes";
import InfoTip from "@/components/InfoTip";
import Disclosure from "@/components/Disclosure";

interface Props {
  settings: FireSettings;
  open: boolean;
  needsSetup: boolean;
  onToggle: () => void;
  onSave: (next: FireSettings) => Promise<void>;
}

/** Optional-number fields render as "" when null rather than 0, since 0 is a
 *  real value for several of these (target age, real return) and would be
 *  indistinguishable from "not set" if it doubled as the blank state. */
function numOrEmpty(v: number | null): string {
  return v === null ? "" : String(v);
}

/** Fraction -> percent for display, rounded to kill the float artifacts a
 *  plain `* 100` leaves behind (0.035 * 100 === 3.500000000000004). */
function toPct(v: number): number {
  return Math.round(v * 1000) / 10;
}

export default function SettingsCard({
  settings,
  open,
  needsSetup,
  onToggle,
  onSave,
}: Props) {
  const { t } = useI18n();
  const [form, setForm] = useState<FireSettings>(settings);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A fresh save flows back in as new `settings` - pick it up, but never
  // stomp on edits the person has not saved yet.
  useEffect(() => {
    if (!dirty) setForm(settings);
  }, [settings, dirty]);

  function set<K extends keyof FireSettings>(key: K, value: FireSettings[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  }

  function setOptionalNumber(key: keyof FireSettings, raw: string) {
    set(key, (raw.trim() === "" ? null : Number(raw)) as never);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSave(form);
      setDirty(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <button
        type="button"
        onClick={onToggle}
        disabled={needsSetup}
        className="flex w-full items-center justify-between text-left"
      >
        <h2 className="text-lg font-semibold">{t("fire.settings.title")}</h2>
        {!needsSetup && <span className="subtle">{open ? "▲" : "▼"}</span>}
      </button>

      {needsSetup && (
        <p className="mt-1 text-sm muted">{t("fire.needBirthYear")}</p>
      )}

      {open && (
        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="fs-birth-year">
                {t("fire.settings.birthYear")}
              </label>
              <input
                id="fs-birth-year"
                className="input"
                type="number"
                step="1"
                value={numOrEmpty(form.birth_year)}
                onChange={(e) => setOptionalNumber("birth_year", e.target.value)}
                required
              />
            </div>
            <div>
              <label className="label" htmlFor="fs-target-age">
                {t("fire.settings.targetFiAge")}
              </label>
              <input
                id="fs-target-age"
                className="input"
                type="number"
                step="0.5"
                value={numOrEmpty(form.target_fi_age)}
                onChange={(e) => setOptionalNumber("target_fi_age", e.target.value)}
              />
              <p className="mt-1 text-xs muted">
                {t("fire.settings.targetFiAgeHint")}
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="fs-retirement-age">
                {t("fire.settings.retirementAge")}
              </label>
              <input
                id="fs-retirement-age"
                className="input"
                type="number"
                step="0.5"
                value={form.retirement_age}
                onChange={(e) => set("retirement_age", Number(e.target.value))}
                required
              />
              <p className="mt-1 text-xs muted">
                {t("fire.settings.retirementAgeHint")}
              </p>
            </div>
            <div>
              <label className="label" htmlFor="fs-zus">
                {t("fire.settings.zusPension")}
              </label>
              <input
                id="fs-zus"
                className="input"
                type="number"
                step="0.01"
                min="0"
                value={form.zus_pension_monthly}
                onChange={(e) =>
                  set("zus_pension_monthly", Number(e.target.value))
                }
              />
              <p className="mt-1 text-xs muted">
                {t("fire.settings.zusPensionHint")}
              </p>
            </div>
          </div>

          <Disclosure
            title={t("fire.settings.advanced")}
            storageKey="myfinance-fire-settings-advanced"
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="label" htmlFor="fs-swr">
                  {t("fire.settings.swr")} (%)
                  <InfoTip text={t("gloss.swr")} label={t("fire.settings.swr")} />
                </label>
                <input
                  id="fs-swr"
                  className="input"
                  type="number"
                  step="0.1"
                  min="2"
                  max="6"
                  value={toPct(form.swr)}
                  onChange={(e) => set("swr", Number(e.target.value) / 100)}
                  required
                />
                <p className="mt-1 text-xs muted">{t("fire.settings.swrHint")}</p>
              </div>
              <div>
                <label className="label" htmlFor="fs-inflation">
                  {t("fire.settings.inflation")} (%)
                </label>
                <input
                  id="fs-inflation"
                  className="input"
                  type="number"
                  step="0.1"
                  min="0"
                  value={toPct(form.inflation)}
                  onChange={(e) => set("inflation", Number(e.target.value) / 100)}
                  required
                />
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="label" htmlFor="fs-real-return">
                  {t("fire.settings.realReturnOverride")} (%)
                  <InfoTip text={t("gloss.realReturn")} label={t("fire.settings.realReturnOverride")} />
                </label>
                <input
                  id="fs-real-return"
                  className="input"
                  type="number"
                  step="0.1"
                  value={
                    form.real_return_override === null
                      ? ""
                      : toPct(form.real_return_override)
                  }
                  onChange={(e) =>
                    set(
                      "real_return_override",
                      (e.target.value.trim() === ""
                        ? null
                        : Number(e.target.value) / 100) as never
                    )
                  }
                />
                <p className="mt-1 text-xs muted">
                  {t("fire.settings.realReturnOverrideHint")}
                </p>
              </div>
              <div>
                <label className="label" htmlFor="fs-spend-override">
                  {t("fire.settings.monthlySpendOverride")}
                </label>
                <input
                  id="fs-spend-override"
                  className="input"
                  type="number"
                  step="0.01"
                  min="0"
                  value={numOrEmpty(form.monthly_spend_override)}
                  onChange={(e) =>
                    setOptionalNumber("monthly_spend_override", e.target.value)
                  }
                />
                <p className="mt-1 text-xs muted">
                  {t("fire.settings.monthlySpendOverrideHint")}
                </p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="label" htmlFor="fs-barista">
                  {t("fire.settings.baristaIncome")}
                </label>
                <input
                  id="fs-barista"
                  className="input"
                  type="number"
                  step="0.01"
                  min="0"
                  value={form.barista_income_monthly}
                  onChange={(e) =>
                    set("barista_income_monthly", Number(e.target.value))
                  }
                />
              </div>
              <div>
                <label className="label" htmlFor="fs-gain-share">
                  {t("fire.settings.gainShare")} (%)
                  <InfoTip text={t("gloss.belka")} label={t("fire.settings.gainShare")} />
                </label>
                <input
                  id="fs-gain-share"
                  className="input"
                  type="number"
                  step="1"
                  min="0"
                  max="100"
                  value={toPct(form.gain_share)}
                  onChange={(e) => set("gain_share", Number(e.target.value) / 100)}
                />
                <p className="mt-1 text-xs muted">
                  {t("fire.settings.gainShareHint")}
                </p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="label" htmlFor="fs-emergency">
                  {t("fire.settings.emergencyMonths")}
                </label>
                <input
                  id="fs-emergency"
                  className="input"
                  type="number"
                  step="0.5"
                  min="0"
                  value={form.emergency_months}
                  onChange={(e) => set("emergency_months", Number(e.target.value))}
                />
              </div>
              <div className="flex items-end pb-2">
                <div className="flex items-center gap-2">
                  <input
                    id="fs-health"
                    type="checkbox"
                    checked={form.include_health_cost}
                    onChange={(e) => set("include_health_cost", e.target.checked)}
                  />
                  <label
                    htmlFor="fs-health"
                    className="text-sm font-medium text-slate-700 dark:text-slate-200"
                  >
                    {t("fire.settings.includeHealthCost")}
                  </label>
                </div>
              </div>
            </div>
          </Disclosure>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? t("common.saving") : t("fire.settings.save")}
          </button>
        </form>
      )}
    </div>
  );
}
