export type Theme = "light" | "dark" | "system";

export const THEME_KEY = "myfinance-theme";
export const THEMES: Theme[] = ["light", "dark", "system"];

/** The theme actually painted, once "system" is resolved. */
export function resolveTheme(theme: Theme): "light" | "dark" {
  if (theme !== "system") return theme;
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function readTheme(): Theme {
  if (typeof window === "undefined") return "system";
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") {
      return stored;
    }
  } catch {
    // Private mode or blocked storage - fall through to the default.
  }
  return "system";
}

export function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;
  const dark = resolveTheme(theme) === "dark";
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
}

export function storeTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Not fatal - the theme still applies for this page view.
  }
}
