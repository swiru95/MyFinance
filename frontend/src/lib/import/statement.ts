import { cleanNote, CURRENCIES, parseAmount, parseDate, type ImportRow } from "./parse";

/** A PDF statement's lines -> its outgoing payments, by code. Polish banks print money going out with a minus
 *  ("-45,99 PLN") and balances without one, so every line with a signed negative amount is one payment; its date
 *  is the nearest date on that line or just above. The note is a rough cut of the text around it. Statements that
 *  print debits unsigned (separate debit and credit columns) give no rows here, and the assistant reads them
 *  instead (lib/import/assist.ts extractStatement). */

const NEG = /(?<![\d,.])[-\u2212]\s?(\d{1,3}(?:[ \u00a0]\d{3})*,\d{2}|\d+,\d{2})\s?([A-Z]{3})\b/;
const DATE = /\b\d{2}[.\-/]\d{2}[.\-/]\d{4}\b|\b\d{4}-\d{2}-\d{2}\b/;
const ACCOUNT = /\b\d{26}\b|\b\d{2}(?: \d{4}){6}\b/g;
const TOTALS = /saldo|suma|razem|łącznie|balance|total/i;

/** Lines of text a note is cut from: the payment's line and the two above it. */
const ABOVE = 2;

export interface Debits {
  rows: ImportRow[];
  skipped: number;
}

const digits = (s: string) => s.replace(/\D/g, "");

/** Account numbers printed in a document's opening lines: the holder's own accounts. */
export function ownAccounts(head: string[]): Set<string> {
  return new Set(head.flatMap((l) => [...l.matchAll(ACCOUNT)].map((m) => digits(m[0]))));
}

function roughNote(lines: string[]): string {
  return cleanNote(
    lines
      .join(" ")
      .replace(new RegExp(DATE.source, "g"), " ")
      .replace(/[-\u2212]?\s?\d{1,3}(?:[ \u00a0]\d{3})*,\d{2}\s?[A-Z]{3}\b/g, " ")
      .replace(/\b\d{5,}\b|\d{2}(?: \d{4}){6}/g, " ")
      .replace(/\b(PLN|EUR|USD|CHF|POL)\b/g, " ")
      .replace(/\s[-:/]\s/g, " "),
  );
}

export function findDebits(lines: string[], baseCurrency: string): Debits {
  const anchors = lines.map((l, i) => (NEG.test(l) && !TOTALS.test(l) ? i : -1)).filter((i) => i >= 0);
  // The holder's accounts: numbers printed above the first payment's lines (at most the first 20 lines).
  const own = ownAccounts(lines.slice(0, Math.min(20, Math.max(0, (anchors[0] ?? 0) - ABOVE - 1))));
  const rows: ImportRow[] = [];
  let skipped = 0;
  anchors.forEach((i, n) => {
    const m = lines[i].match(NEG)!;
    const amount = parseAmount(m[1]);
    const currency = m[2] || baseCurrency;
    let date = "";
    for (let k = 0; k <= 3 && !date && i - k >= 0; k++) date = parseDate(lines[i - k].match(DATE)?.[0] ?? "");
    if (!date || !(amount > 0) || !CURRENCIES.includes(currency)) {
      skipped++;
      return;
    }
    // An own account number between this payment and the next one: a transfer between the holder's accounts.
    const next = anchors[n + 1] ?? lines.length;
    const after = lines.slice(i, Math.min(next, i + 5));
    const transfer = after.some((l) => [...l.matchAll(ACCOUNT)].some((a) => own.has(digits(a[0]))));
    const key = `pdf-${i + 1}`;
    rows.push({
      key,
      date,
      amount,
      currency,
      note: roughNote(lines.slice(Math.max(0, i - ABOVE), i + 1)),
      commitment: null,
      checked: !transfer,
      unverified: false,
      transfer,
    });
  });
  return { rows, skipped };
}
