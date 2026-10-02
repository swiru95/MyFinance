/** Helpers shared by the recovery-code components. Nothing here stores or
 *  logs a code - the code lives only in React component state. */

/** Tolerant comparison/submission form of a code: upper-case, with any run of
 *  whitespace (a code copied from a printout often has spaces or line breaks
 *  where the hyphens were) turned back into a hyphen. Crockford base32 is
 *  case-insensitive, so this never changes which code was meant. */
export function normalizeRecoveryCode(raw: string): string {
  return raw.trim().replace(/\s+/g, "-").toUpperCase();
}

/** "1:05" / "0:42" - for the lock-out countdown. */
export function fmtCountdown(totalSeconds: number): string {
  const s = Math.max(0, Math.ceil(totalSeconds));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

/** True when a fetch failed before any HTTP answer (offline, DNS, reset). */
export function isNetworkError(err: unknown): boolean {
  return err instanceof TypeError;
}
