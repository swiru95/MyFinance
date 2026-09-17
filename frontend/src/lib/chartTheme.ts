import { useEffect, useState } from "react";

/**
 * Categorical slots, assigned in fixed order and never cycled. Both columns are
 * selected for their own surface - the dark column is the same eight hues
 * re-stepped for a dark background, not an automatic inversion.
 *
 * Validated (adjacent pairlist) on both surfaces: worst adjacent CVD dE 9.1
 * light / 8.4 dark, worst normal-vision dE 19.6 light / 19.3 dark. Three light
 * slots fall below 3:1 against white, so every chart using them ships the
 * months table as relief.
 */
export const SERIES_LIGHT = [
  "#2a78d6", // 1 blue
  "#eb6834", // 2 orange
  "#1baf7a", // 3 aqua
  "#eda100", // 4 yellow
  "#e87ba4", // 5 magenta
  "#008300", // 6 green
  "#4a3aa7", // 7 violet
  "#e34948", // 8 red
] as const;

export const SERIES_DARK = [
  "#3987e5",
  "#d95926",
  "#199e70",
  "#c98500",
  "#d55181",
  "#008300",
  "#9085e9",
  "#e66767",
] as const;

export const MAX_SERIES = SERIES_LIGHT.length;

/** Risk profile colours: the band name itself encodes risk semantics, so the
 *  colour should too. These break from the positional palette
 *  (SERIES_LIGHT/DARK), which assigns colours by slot index - a band must keep
 *  its meaning-bearing hue no matter where it sorts.
 *
 *  Still drawn from the eight validated slots rather than picked by eye, so the
 *  CVD work behind that palette carries over. Measured for this set of four:
 *  worst normal-vision dE 60.9, worst protanopia dE 23.0.
 *
 *  Two known trade-offs, both deliberate:
 *
 *  - Yellow is the weakest slot against a white card (2.17:1, under the 3:1
 *    guidance for graphical objects). Accepted because the legend prints every
 *    band's name, share and amount as text, so the swatch is never the only way
 *    to read the chart - the same relief the palette comment already relies on.
 *    Darkening it to pass contrast is worse, not better: at #bf8200 it collapses
 *    against the illiquid green under protanopia (dE 6.9 vs 23.0 here).
 *  - Red and green sit together by construction, since risky and illiquid want
 *    exactly those meanings. Worst deuteranopia dE is 13.5 between them. The
 *    icons (📈 / 🔒) and the text legend carry the distinction. */
export const PROFILE_LIGHT: Record<string, string> = {
  safe: "#2a78d6",       // slot 0, blue
  moderate: "#eda100",   // slot 3, yellow
  risky: "#e34948",      // slot 7, red
  illiquid: "#008300",   // slot 5, green
};

export const PROFILE_DARK: Record<string, string> = {
  safe: "#3987e5",       // slot 0, blue
  moderate: "#c98500",   // slot 3, yellow
  risky: "#e66767",      // slot 7, red
  illiquid: "#008300",   // slot 5, green
};

export function profileColor(profile: string, dark: boolean): string | undefined {
  const map = dark ? PROFILE_DARK : PROFILE_LIGHT;
  return map[profile];
}

export interface ChartTheme {
  dark: boolean;
  series: readonly string[];
  grid: string;
  axis: string;
  surface: string;
  tooltip: {
    background: string;
    border: string;
    borderRadius: number;
    color: string;
  };
}

/** Tracks the `dark` class that the theme toggle and the no-flash script set. */
export function useChartTheme(): ChartTheme {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const read = () => setDark(document.documentElement.classList.contains("dark"));
    read();
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  const surface = dark ? "#0f172a" : "#ffffff";
  return {
    dark,
    series: dark ? SERIES_DARK : SERIES_LIGHT,
    grid: dark ? "#334155" : "#e2e8f0",
    axis: dark ? "#64748b" : "#94a3b8",
    surface,
    tooltip: {
      background: dark ? "#1e293b" : "#ffffff",
      border: `1px solid ${dark ? "#334155" : "#e2e8f0"}`,
      borderRadius: 8,
      color: dark ? "#e2e8f0" : "#0f172a",
    },
  };
}

/** "2026-09" -> "Sep 26" / "wrz 26", following the active language. */
export function monthLabel(month: string, locale = "en-US"): string {
  const [year, mon] = month.split("-");
  const name = new Date(Number(year), Number(mon) - 1, 1).toLocaleDateString(
    locale,
    { month: "short" }
  );
  return `${name} ${year.slice(2)}`;
}
