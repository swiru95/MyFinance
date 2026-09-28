import { useEffect, useState } from "react";

/** A boolean bit of UI state (a panel's open/closed) remembered per browser
 *  via localStorage - not settings, so it is not synced through the backend
 *  or across devices. Used for the progressive-disclosure panels added in
 *  round 2 (Expenses' "Show analysis", FIRE's "Details" and "Advanced
 *  settings"): each viewer's choice should stick between visits without
 *  needing a server round trip or a new Settings field for something this
 *  disposable. Starts at `initial` on the server and on first paint, then
 *  syncs from storage in an effect - avoids a hydration mismatch, at the
 *  cost of one render before a returning visitor's saved state applies.
 *  Wrapped in try/catch like lib/i18n.ts's language persistence: private
 *  browsing or blocked storage should degrade to "always `initial`", not
 *  break the panel. */
export function useStoredBool(
  key: string,
  initial: boolean,
): [boolean, (next: boolean) => void] {
  const [value, setValue] = useState(initial);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(key);
      if (stored !== null) setValue(stored === "1");
    } catch {
      // Blocked storage - stay at `initial`.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  function update(next: boolean) {
    setValue(next);
    try {
      window.localStorage.setItem(key, next ? "1" : "0");
    } catch {
      // Not fatal - the choice just does not survive a reload.
    }
  }

  return [value, update];
}
