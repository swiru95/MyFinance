/** Single place for how a Polish tax-advantaged wrapper is *shown*: its
 *  colour (frame + badge), its i18n label key and its access-age note.
 *  Positions cards, the dashboard tile and anywhere else a wrapper needs a
 *  colour or a badge should read from here rather than re-deciding a hue -
 *  one wrapper, one colour, everywhere it appears.
 *
 *  Access ages mirror backend/src/tax/pl/wrappers.py (ike/ppk/oipe: 60,
 *  ikze: 65, oki: no lock at all).
 */

export type WrapperKey = "ike" | "ikze" | "ppk" | "oipe" | "oki";

export const WRAPPER_KEYS: WrapperKey[] = ["ike", "ikze", "ppk", "oipe", "oki"];

export interface WrapperStyle {
  /** Card frame around a wrapped position. */
  ring: string;
  /** Small badge naming the wrapper. */
  badge: string;
  /** Dot/swatch, e.g. for a legend. */
  dot: string;
}

// Tailwind's JIT scanner reads this file directly (see tailwind.config.js
// content globs), so every class below must appear as a literal string -
// no string-building from parts - or it gets purged from the build.
export const WRAPPER_STYLES: Record<WrapperKey, WrapperStyle> = {
  ike: {
    ring: "ring-2 ring-blue-400 dark:ring-blue-500",
    badge: "bg-blue-100 text-blue-800 dark:bg-blue-900/60 dark:text-blue-200",
    dot: "bg-blue-500",
  },
  ikze: {
    ring: "ring-2 ring-purple-400 dark:ring-purple-500",
    badge: "bg-purple-100 text-purple-800 dark:bg-purple-900/60 dark:text-purple-200",
    dot: "bg-purple-500",
  },
  ppk: {
    ring: "ring-2 ring-amber-400 dark:ring-amber-500",
    badge: "bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200",
    dot: "bg-amber-500",
  },
  oipe: {
    ring: "ring-2 ring-teal-400 dark:ring-teal-500",
    badge: "bg-teal-100 text-teal-800 dark:bg-teal-900/60 dark:text-teal-200",
    dot: "bg-teal-500",
  },
  // OKI behaves differently from the other four (no age lock), so it gets
  // its own hue rather than reusing one of theirs.
  oki: {
    ring: "ring-2 ring-emerald-400 dark:ring-emerald-500",
    badge: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200",
    dot: "bg-emerald-500",
  },
};

/** i18n key for the wrapper's display name ("IKE", "OKI", ...). */
export function wrapperLabelKey(wrapper: WrapperKey): string {
  return `fire.wrapper.${wrapper}`;
}

/** i18n key for the wrapper's access-age note ("Locked until 60", "Withdraw
 *  any time", ...). Wrappers with an access_age share the same two notes;
 *  only oki has no lock at all - see tax/pl/wrappers.py on the backend. */
export function wrapperAccessKey(wrapper: WrapperKey): string {
  if (wrapper === "oki") return "fire.wrapper.access.any";
  if (wrapper === "ikze") return "fire.wrapper.access.65";
  return "fire.wrapper.access.60";
}

/** Wrappers with no age lock - kept as a set of one for the same reason
 *  backend ACCESS_AGE leaves oki out: `wrapper in LOCKED` doubles as "is this
 *  one locked". */
export function isLocked(wrapper: WrapperKey): boolean {
  return wrapper !== "oki";
}
