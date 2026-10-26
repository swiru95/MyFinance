import { cleanNote, CURRENCIES, parseAmount, parseDate, type ImportRow } from "./parse";
import { ownAccounts } from "./statement";

/** Bank CSV exports. Layouts differ per bank (one signed amount or debit/credit columns, metadata lines above the
 *  header, Polish or English names), so the columns come from a mapping: the assistant's (lib/import/assist.ts) when
 *  the wallet has one, else guessHeuristic() below. Either way the mapping is checked against the rows and then
 *  applied by code to every row, so a model never invents a transaction here. */

/** One CSV line -> fields; quotes may wrap a field, "" inside quotes is a quote. */
function splitLine(line: string, sep: string): string[] {
  const out: string[] = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else if (c === '"') quoted = false;
      else cur += c;
    } else if (c === '"') quoted = true;
    else if (c === sep) {
      out.push(cur.trim());
      cur = "";
    } else cur += c;
  }
  out.push(cur.trim());
  return out;
}

/** Which column holds what (0-based; -1 = absent). From guessHeuristic() or the assistant (lib/import/assist.ts). */
export interface CsvMapping {
  date: number;
  /** One signed amount column, or separate debit (money out) / credit (money in) columns. */
  amount: number;
  debit: number;
  credit: number;
  /** In `amount`: is money going out printed negative (most banks) or positive? */
  outgoing: "negative" | "positive";
  description: number[];
  currency: number;
}

export interface CsvTable {
  header: string[];
  /** The rows that carry a date and an amount (metadata, totals and blank lines dropped). */
  data: string[][];
  /** Account numbers in the lines above the header (the export's own accounts). */
  own: Set<string>;
}

const isData = (r: string[]) => r.some((c) => parseDate(c)) && r.some((c) => !isNaN(parseAmount(c)));

export function readCsv(text: string): CsvTable | null {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  const sep = [";", ",", "\t"]
    .map((s) => [s, lines.slice(0, 50).filter((l) => splitLine(l, s).length >= 3).length] as const)
    .sort((a, b) => b[1] - a[1])[0][0];
  const table = lines.map((l) => splitLine(l, sep));
  // The header is the line right before the first row with a date and an amount.
  const first = table.findIndex(isData);
  if (first < 0) return null;
  return { header: first > 0 ? table[first - 1] : [], data: table.slice(first).filter(isData), own: ownAccounts(lines.slice(0, Math.max(0, first - 1))) };
}

const DATE_NAMES = /data (operacji|transakcji|księgowania)|^data$|date/i;
const AMOUNT_NAMES = /^kwota|amount|wartość/i;
const DEBIT_NAMES = /obciążen|wypływ|debit|wydatk/i;
const CREDIT_NAMES = /uznani|wpływ|credit/i;
const NOTE_NAMES = /kontrahent|odbiorc|tytuł|opis|counterparty|payee|merchant|title|description/i;
/** Exact names: "Kwota (waluta rachunku)" names an amount, not a currency. */
const CURRENCY_NAMES = /^(waluta|currency)$/i;

/** Column names first, then content: which column most rows have a date / an amount in. */
export function guessHeuristic({ header, data }: CsvTable): CsvMapping {
  const h = header.map((x) => x.toLocaleLowerCase());
  const named = (re: RegExp, not: number[] = []) => h.findIndex((x, i) => re.test(x) && !not.includes(i));
  const width = Math.max(...data.map((r) => r.length));
  const best = (test: (c: string) => boolean, not: number[]) => {
    let col = -1;
    let n = 0;
    for (let c = 0; c < width; c++) {
      if (not.includes(c)) continue;
      const k = data.filter((r) => test(r[c] ?? "")).length;
      if (k > n) [col, n] = [c, k];
    }
    return col;
  };
  let date = named(DATE_NAMES);
  if (date < 0) date = best((c) => !!parseDate(c), []);
  const debit = named(DEBIT_NAMES, [date]);
  const credit = named(CREDIT_NAMES, [date, debit]);
  let amount = debit >= 0 ? -1 : named(AMOUNT_NAMES, [date]);
  if (amount < 0 && debit < 0) amount = best((c) => !isNaN(parseAmount(c)) && /[.,]\d{2}/.test(c), [date]);
  const used = [date, amount, debit, credit];
  let description = h.map((x, i) => (NOTE_NAMES.test(x) && !used.includes(i) ? i : -1)).filter((i) => i >= 0).slice(0, 3);
  if (!description.length) {
    // No named description: the column with the longest text on average.
    let col = -1;
    let len = 0;
    for (let c = 0; c < width; c++) {
      if (used.includes(c)) continue;
      const l = data.reduce((a, r) => a + (r[c]?.length ?? 0), 0);
      if (l > len) [col, len] = [c, l];
    }
    description = col >= 0 ? [col] : [];
  }
  // Several currency columns (one per amount, as in ING's export): the first one after the amount used.
  const after = Math.max(amount, debit);
  const currency = h.findIndex((x, i) => i > after && CURRENCY_NAMES.test(x.trim()));
  return { date, amount, debit, credit, outgoing: "negative", description, currency: currency >= 0 ? currency : named(CURRENCY_NAMES) };
}

/** A mapping is usable when its date column parses in most rows and its amount column(s) parse as amounts. */
export function mappingFits(m: CsvMapping, { data }: CsvTable): boolean {
  const most = (test: (r: string[]) => boolean) => data.filter(test).length * 4 >= data.length * 3;
  // A debit column is empty on incoming rows, so empty cells pass; at least one must hold an amount.
  const amountOk = (col: number) =>
    col >= 0 && data.some((r) => !isNaN(parseAmount(r[col] ?? ""))) && most((r) => !r[col] || !isNaN(parseAmount(r[col])));
  return (
    m.date >= 0 &&
    most((r) => !!parseDate(r[m.date] ?? "")) &&
    (amountOk(m.amount) || amountOk(m.debit)) &&
    m.description.every((c) => c >= 0 && c !== m.date)
  );
}

export function applyMapping(m: CsvMapping, { data, own }: CsvTable, baseCurrency: string): { rows: ImportRow[]; skipped: number } {
  const ownIn = (cell: string | undefined) => own.has((cell ?? "").replace(/\D/g, ""));
  // A column holding an own account on nearly every row is the statement's account, not the payee's.
  const width = Math.max(...data.map((r) => r.length));
  const payeeCols = [...Array(width).keys()].filter((c) => data.filter((r) => ownIn(r[c])).length * 10 < data.length * 9);
  const rows: ImportRow[] = [];
  let skipped = 0;
  data.forEach((r, i) => {
    const date = parseDate(r[m.date] ?? "");
    let out = NaN;
    if (m.amount >= 0) {
      const v = parseAmount(r[m.amount] ?? "");
      out = m.outgoing === "negative" ? -v : v;
    } else if (m.debit >= 0) {
      // Debit columns print money out as a positive number (some banks with a minus): either way it is spent.
      const v = parseAmount(r[m.debit] ?? "");
      out = isNaN(v) || v === 0 ? -1 : Math.abs(v);
    }
    const currency = m.currency >= 0 && r[m.currency] ? r[m.currency].toUpperCase() : baseCurrency;
    if (!date || !(out > 0) || !CURRENCIES.includes(currency)) {
      if (date) skipped++;
      return;
    }
    const note = cleanNote(
      m.description
        .map((c) => r[c] ?? "")
        .filter(Boolean)
        .join(" · "),
    );
    const transfer = payeeCols.some((c) => ownIn(r[c]));
    rows.push({ key: `csv-${i}`, date, amount: Math.round(out * 100) / 100, currency, note, commitment: null, checked: !transfer, unverified: false, transfer });
  });
  return { rows, skipped };
}
