import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { FeatureFlags, Settings } from "@/lib/types";

/** A new wallet's advanced features all start off - matches the backend's
 *  own fallback (schema.py's seed_features on an empty database, and
 *  GET /api/settings if the row is somehow missing), so a still-loading page
 *  reads the same as a genuinely brand-new one rather than flashing
 *  everything on for a moment. */
export const DEFAULT_FEATURES: FeatureFlags = {
  portfolio: false,
  fire: false,
  tax: false,
  insights: false,
};

interface SettingsValue {
  settings: Settings | null;
  /** Falls back to the browser's zone until the backend answers. */
  timeZone: string | undefined;
  baseCurrency: string;
  features: FeatureFlags;
  refresh: () => Promise<void>;
  apply: (next: Settings) => void;
  /** Saves just the feature switches, keeping the current currency/timezone -
   *  used by both the Settings page and lib/features.ts's useFeatures(). */
  setFeatures: (next: FeatureFlags) => Promise<void>;
}

const SettingsContext = createContext<SettingsValue>({
  settings: null,
  timeZone: undefined,
  baseCurrency: "PLN",
  features: DEFAULT_FEATURES,
  refresh: async () => {},
  apply: () => {},
  setFeatures: async () => {},
});

export function useSettings(): SettingsValue {
  return useContext(SettingsContext);
}

export default function SettingsProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [settings, setSettings] = useState<Settings | null>(null);

  const refresh = useCallback(async () => {
    try {
      setSettings(await api.getSettings());
    } catch {
      // Leave the defaults in place; pages surface their own load errors.
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setFeatures = useCallback(
    async (next: Settings["features"]) => {
      if (!settings) return;
      const updated = await api.setSettings(settings.base_currency, settings.timezone, next);
      setSettings(updated);
    },
    [settings],
  );

  return (
    <SettingsContext.Provider
      value={{
        settings,
        timeZone: settings?.timezone,
        baseCurrency: settings?.base_currency ?? "PLN",
        features: settings?.features ?? DEFAULT_FEATURES,
        refresh,
        apply: setSettings,
        setFeatures,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
}
