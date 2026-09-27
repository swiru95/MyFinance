import type { RungKey, RungStatus } from "@/lib/insightsTypes";

/** Display order and copy for each ladder rung, keyed by rung key and then
 *  by status. The backend computes `why_key` per rung (see
 *  lib/insightsTypes.ts), but this UI does not depend on guessing that
 *  string's exact spelling against a backend written concurrently by a
 *  different agent - it owns its own (key, status) -> i18n-key mapping
 *  instead, matching the STYLE_KEYS pattern already used on this page for
 *  ReportStyle. The backend's `figures` dict still drives every number shown
 *  (see FiguresLine), so nothing here invents data - only the surrounding
 *  sentence is client-side copy. */
export const RUNG_ORDER: RungKey[] = [
  "starter_buffer",
  "envelope_covered",
  "emergency_fund",
  "ppk_on",
  "ikze_used",
  "ike_used",
  "fire_configured",
  "savings_rate_on_track",
  "data_fresh",
];

export const RUNG_TITLE_KEY: Record<RungKey, string> = {
  starter_buffer: "ins.ladder.starter_buffer.title",
  envelope_covered: "ins.ladder.envelope_covered.title",
  emergency_fund: "ins.ladder.emergency_fund.title",
  ppk_on: "ins.ladder.ppk_on.title",
  ikze_used: "ins.ladder.ikze_used.title",
  ike_used: "ins.ladder.ike_used.title",
  fire_configured: "ins.ladder.fire_configured.title",
  savings_rate_on_track: "ins.ladder.savings_rate_on_track.title",
  data_fresh: "ins.ladder.data_fresh.title",
};

export function rungWhyKey(key: RungKey, status: RungStatus): string {
  return `ins.ladder.${key}.${status}`;
}

export const STATUS_ICON: Record<RungStatus, string> = {
  done: "✓", // check
  in_progress: "◐", // half circle
  todo: "○", // open circle
  not_applicable: "–", // en dash
  unknown: "?",
};

export const STATUS_CLASS: Record<RungStatus, string> = {
  done: "text-emerald-600 dark:text-emerald-400",
  in_progress: "text-amber-600 dark:text-amber-400",
  todo: "text-slate-400 dark:text-slate-500",
  not_applicable: "subtle",
  unknown: "subtle",
};
