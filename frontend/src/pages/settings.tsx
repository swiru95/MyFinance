import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { BASE_CURRENCIES } from "@/lib/types";
import { useSettings } from "@/components/SettingsProvider";
import ThemeToggle from "@/components/ThemeToggle";
import LanguageToggle from "@/components/LanguageToggle";

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
    </div>
  );
}
