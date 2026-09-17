import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Settings } from "@/lib/types";

interface SettingsValue {
  settings: Settings | null;
  /** Falls back to the browser's zone until the backend answers. */
  timeZone: string | undefined;
  baseCurrency: string;
  refresh: () => Promise<void>;
  apply: (next: Settings) => void;
}

const SettingsContext = createContext<SettingsValue>({
  settings: null,
  timeZone: undefined,
  baseCurrency: "PLN",
  refresh: async () => {},
  apply: () => {},
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

  return (
    <SettingsContext.Provider
      value={{
        settings,
        timeZone: settings?.timezone,
        baseCurrency: settings?.base_currency ?? "PLN",
        refresh,
        apply: setSettings,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
}
