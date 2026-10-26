/** Shared pieces of the statement import (components/expenses/StatementImport.tsx): the row shape and the parsers
 *  for the amounts and dates Polish banks print. Everything here runs in the browser; the document never leaves it. */

export interface ImportRow {
  /** Stable key within one import (the source line for a PDF, the CSV row number). */
  key: string;
  date: string;
  /** Always positive: what was spent. */
  amount: number;
  currency: string;
  note: string;
  /** The recurring expense (Expense id) this payment pays in its month, or null = other spending. */
  commitment: number | null;
  /** Unticked rows are not saved. */
  checked: boolean;
  /** The date or amount could not be found in the source text (a model mistake): shown, never pre-ticked. */
  unverified: boolean;
  /** Paid to one of the holder's own accounts (named in the document's opening lines): not spending, unticked. */
  transfer: boolean;
}

/** What the API accepts (SpendIn.currency); rows in any other currency are skipped, not converted. */
export const CURRENCIES = ["PLN", "EUR", "USD", "CHF"];

export const MAX_PDF_BYTES = 10 * 1024 * 1024;
export const MAX_CSV_BYTES = 2 * 1024 * 1024;

const AMOUNT_RE = /[-\u2212\u2013+]?\s?\d{1,3}(?:[ \u00a0.]\d{3})*(?:[.,]\d{2})(?!\d)|[-\u2212\u2013+]?\d+[.,]\d{2}(?!\d)/g;
const DATE_RE = /\b(\d{4})[-./](\d{2})[-./](\d{2})\b|\b(\d{2})[-./](\d{2})[-./](\d{4})\b/g;

/** "-1 234,56" / "1.234,56 PLN" / "45,00-" / a typographic minus -> signed number; NaN when it is not an amount. */
export function parseAmount(raw: string): number {
  let s = raw.replace(/[\s\u00a0]/g, "").replace(/[A-Za-z]{3}$/, "").replace(/[\u2212\u2013]/g, "-");
  let sign = 1;
  if (s.startsWith("-")) {
    sign = -1;
    s = s.slice(1);
  } else if (s.startsWith("+")) s = s.slice(1);
  if (s.endsWith("-")) {
    sign = -1;
    s = s.slice(0, -1);
  }
  const lastComma = s.lastIndexOf(",");
  const lastDot = s.lastIndexOf(".");
  const dec = Math.max(lastComma, lastDot);
  // A separator followed by exactly two digits is the decimal one; any other separators group thousands.
  if (dec >= 0 && s.length - dec - 1 === 2) s = s.slice(0, dec).replace(/[.,]/g, "") + "." + s.slice(dec + 1);
  else s = s.replace(/[.,]/g, "");
  return /^\d+(\.\d{1,2})?$/.test(s) ? sign * Number(s) : NaN;
}

/** "26.10.2026" / "2026-10-26" / "26/10/2026" -> "2026-10-26"; "" when it is not a valid date. */
export function parseDate(raw: string): string {
  const m = raw.trim().match(/^(\d{4})[-./](\d{2})[-./](\d{2})$|^(\d{2})[-./](\d{2})[-./](\d{4})$/);
  if (!m) return "";
  const [y, mo, d] = m[1] ? [m[1], m[2], m[3]] : [m[6], m[5], m[4]];
  const iso = `${y}-${mo}-${d}`;
  const t = new Date(`${iso}T00:00:00Z`);
  return !isNaN(t.getTime()) && t.toISOString().slice(0, 10) === iso ? iso : "";
}

/** Every amount (in grosze, unsigned) and every date printed in `text`: what a model's row is checked against. */
export function groundTruth(text: string): { amounts: Set<number>; dates: Set<string> } {
  const amounts = new Set<number>();
  const dates = new Set<string>();
  for (const m of text.matchAll(AMOUNT_RE)) {
    const v = parseAmount(m[0]);
    if (!isNaN(v)) amounts.add(Math.round(Math.abs(v) * 100));
  }
  for (const m of text.matchAll(DATE_RE)) {
    const iso = parseDate(m[0]);
    if (iso) dates.add(iso);
  }
  return { amounts, dates };
}

/** One line of plain text for a note: no control characters, single spaces, at most 120 characters. */
export function cleanNote(raw: string): string {
  return raw.replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, 120);
}

/** UTF-8 when the bytes are valid UTF-8, otherwise Windows-1250 (what several Polish banks still export). */
export function decodeText(bytes: ArrayBuffer): string {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes).replace(/^\ufeff/, "");
  } catch {
    return new TextDecoder("windows-1250").decode(bytes);
  }
}
