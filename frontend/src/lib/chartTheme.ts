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
