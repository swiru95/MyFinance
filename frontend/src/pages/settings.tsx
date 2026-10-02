import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useFeatures } from "@/lib/features";
import { BASE_CURRENCIES } from "@/lib/types";
import type { FeatureFlags } from "@/lib/types";
import { useSettings } from "@/components/SettingsProvider";
import ThemeToggle from "@/components/ThemeToggle";
import LanguageToggle from "@/components/LanguageToggle";
import {
  BirthYearCard,
  NotificationsCard,
  RecoveryCard,
} from "@/components/RecoverySettingsCards";

const FEATURE_KEYS: (keyof FeatureFlags)[] = ["portfolio", "fire", "tax", "insights"];

/** The four advanced features, each a plain-language one-liner rather than
 *  jargon - this app is meant to stay approachable for someone who is not a
 *  finance specialist. `fire` needs `portfolio` (see FeatureFlags on the
 *  backend, which enforces this regardless of what the UI sends), so
 *  toggling either one here also updates the other locally before the round
 *  trip comes back, and the FIRE row explains why. */
function FeaturesSection() {
  const { t } = useI18n();
  const { portfolio, fire, tax, insights, setFeatures } = useFeatures();
  const [busy, setBusy] = useState<keyof FeatureFlags | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const current: FeatureFlags = { portfolio, fire, tax, insights };

  async function toggle(key: keyof FeatureFlags) {
    const next: FeatureFlags = { ...current, [key]: !current[key] };
    if (key === "fire" && next.fire) next.portfolio = true;
    if (key === "portfolio" && !next.portfolio) next.fire = false;
    setBusy(key);
    setMsg(null);
    try {
      await setFeatures(next);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="card max-w-md space-y-4">
      <div>
        <h2 className="text-lg font-semibold">{t("set.features.title")}</h2>
        <p className="text-sm muted">{t("set.features.subtitle")}</p>
      </div>
      <ul className="space-y-4">
        {FEATURE_KEYS.map((key) => (
          <li key={key} className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-medium">{t(`set.features.${key}.label`)}</p>
              <p className="mt-0.5 text-xs muted">{t(`set.features.${key}.desc`)}</p>
              {key === "fire" && (
                <p className="mt-0.5 text-xs subtle">{t("set.features.fire.dependency")}</p>
              )}
            </div>
            <input
              type="checkbox"
              className="mt-1 h-5 w-5 shrink-0"
              checked={current[key]}
              disabled={busy === key}
              onChange={() => toggle(key)}
              aria-label={t(`set.features.${key}.label`)}
            />
          </li>
        ))}
      </ul>
      {msg && <p className="banner-error">{msg}</p>}
    </div>
  );
}

export default function SettingsPage() {
  const { t, locale } = useI18n();
  const { settings, apply } = useSettings();
  const [base, setBase] = useState("PLN");
  const [zone, setZone] = useState("Europe/Warsaw");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [now, setNow] = useState<string>("");

  useEffect(() => {
    if (!settings) return;
    setBase(settings.base_currency);
    setZone(settings.timezone);
  }, [settings]);

  // Preview the selected zone so the choice is verifiable before saving.
  useEffect(() => {
    const tick = () => {
      try {
        setNow(
          new Date().toLocaleString(locale, {
            timeZone: zone,
            dateStyle: "medium",
            timeStyle: "medium",
          })
        );
      } catch {
        setNow("");
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [zone, locale]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const next = await api.setSettings(base, zone);
      apply(next);
      setMsg(t("set.savedMsg"));
    } catch (err) {
      setMsg(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(false);
    }
  }

  const zones = settings?.allowed_timezones ?? [zone];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t("set.title")}</h1>
        <p className="text-sm muted">{t("set.subtitle")}</p>
      </div>

      <div className="card max-w-md space-y-4">
        <div>
          <span className="label">{t("set.appearance")}</span>
          <ThemeToggle />
        </div>
        <div>
          <span className="label">{t("set.language")}</span>
          <LanguageToggle />
        </div>
      </div>

      <FeaturesSection />

      <form onSubmit={save} className="card max-w-md space-y-4">
        <div>
          <label className="label" htmlFor="set-currency">
            {t("set.baseCurrency")}
          </label>
          <select
            id="set-currency"
            className="input"
            value={base}
            onChange={(e) => setBase(e.target.value)}
          >
            {BASE_CURRENCIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs muted">{t("set.baseCurrencyHint")}</p>
        </div>

        <div>
          <label className="label" htmlFor="set-timezone">
            {t("set.timezone")}
          </label>
          <select
            id="set-timezone"
            className="input"
            value={zone}
            onChange={(e) => setZone(e.target.value)}
          >
            {zones.map((z) => (
              <option key={z} value={z}>
                {z.replace(/_/g, " ")}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs muted">{t("set.timezoneHint")}</p>
          {now && (
            <p className="mt-1 text-xs subtle tabular-nums">
              {t("set.timezoneNow", { time: now })}
            </p>
          )}
        </div>

        {msg && <p className="banner-info">{msg}</p>}

        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? t("common.saving") : t("set.saveSettings")}
        </button>
      </form>

      <RecoveryCard />

      <NotificationsCard />

      <BirthYearCard />
    </div>
  );
}
