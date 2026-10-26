import type { MonthCommitment } from "@/lib/types";
import type { Assistant } from "./types";
import type { ImportRow } from "./parse";

/** Which statement payment pays which recurring expense, month by month (the month checklist,
 *  GET /api/monthly/{month}/commitments). A payment matched to an expense marks it paid at the statement's amount
 *  and stays out of "other spending", so nothing is counted twice. */

export type CommitmentsByMonth = Record<string, MonthCommitment[]>;

const words = (s: string) => new Set(s.toLocaleLowerCase().match(/[\p{L}\d]{4,}/gu) ?? []);
const shareWord = (a: string, b: string) => {
  const w = words(b);
  return [...words(a)].some((x) => w.has(x));
};

/** Exact amounts: each expense takes an unassigned ticked payment of its month with the same amount and currency;
 *  when several fit, the one whose note shares a word with the expense's name. */
export function matchByAmount(rows: ImportRow[], byMonth: CommitmentsByMonth): ImportRow[] {
  const out = rows.map((r) => ({ ...r }));
  for (const [month, commitments] of Object.entries(byMonth)) {
    // An expense is paid once per month: taken means taken in this month only.
    const taken = new Set(out.filter((r) => r.commitment !== null && r.date.startsWith(month)).map((r) => r.commitment));
    for (const c of commitments) {
      if (taken.has(c.expense_id)) continue;
      const fits = out.filter(
        (r) => r.checked && r.commitment === null && r.date.startsWith(month) && r.currency === c.currency && Math.abs(r.amount - c.amount) < 0.005,
      );
      const pick = fits.find((r) => shareWord(r.note, c.name)) ?? fits[0];
      if (pick) {
        pick.commitment = c.expense_id;
        taken.add(c.expense_id);
      }
    }
  }
  return out;
}

/** Expenses still without a payment (a bill whose amount varies): the assistant picks among that month's
 *  unassigned payments between half and double the usual amount, the 40 nearest. */
export async function matchWithAssistant(
  assistant: Assistant,
  rows: ImportRow[],
  byMonth: CommitmentsByMonth,
  onMonth: (done: number, total: number) => void,
): Promise<ImportRow[]> {
  const out = rows.map((r) => ({ ...r }));
  const months = Object.keys(byMonth).sort();
  for (let i = 0; i < months.length; i++) {
    onMonth(i, months.length);
    const month = months[i];
    const assigned = new Set(out.filter((r) => r.date.startsWith(month)).map((r) => r.commitment).filter((c) => c !== null));
    const open = byMonth[month].filter((c) => !assigned.has(c.expense_id) && c.amount > 0);
    if (!open.length) continue;
    const candidates = out
      .map((r, idx) => ({ r, idx }))
      .filter(
        ({ r }) =>
          r.checked &&
          r.commitment === null &&
          r.date.startsWith(month) &&
          open.some((c) => c.currency === r.currency && r.amount >= c.amount / 2 && r.amount <= c.amount * 2),
      )
      .sort((a, b) => nearest(a.r, open) - nearest(b.r, open))
      .slice(0, 40);
    if (!candidates.length) continue;
    let found: { commitment: number; payment: number }[];
    try {
      found = await assistant.match(
        open.map((c) => ({ id: c.expense_id, name: c.name, category: c.category, amount: c.amount, currency: c.currency })),
        candidates.map(({ r, idx }) => ({ id: idx, date: r.date, amount: r.amount, note: r.note })),
      );
    } catch {
      continue; // that month keeps the code's matches only
    }
    const offered = new Set(candidates.map((c) => c.idx));
    const openIds = new Set(open.map((c) => c.expense_id));
    for (const m of found) {
      if (!offered.has(m.payment) || !openIds.has(m.commitment) || out[m.payment].commitment !== null) continue;
      out[m.payment].commitment = m.commitment;
      openIds.delete(m.commitment);
    }
  }
  onMonth(months.length, months.length);
  return out;
}

function nearest(r: ImportRow, open: MonthCommitment[]): number {
  return Math.min(...open.filter((c) => c.currency === r.currency).map((c) => Math.abs(r.amount - c.amount) / c.amount));
}

export interface MonthPlan {
  month: string;
  /** The statement covers only part of this month: not written unless ticked. */
  partial: boolean;
  /** Expense id -> the statement's amount for it. */
  paid: Map<number, number>;
  other: number;
  rows: number;
}

/** Per month: what the checklist and "other spending" become. `currency` is the month records' currency; rows in
 *  any other currency are left out (`foreign`). */
export function planMonths(rows: ImportRow[], currency: string): { months: MonthPlan[]; foreign: number } {
  const ticked = rows.filter((r) => r.checked);
  const foreign = ticked.filter((r) => r.currency !== currency).length;
  const use = ticked.filter((r) => r.currency === currency);
  const all = rows.map((r) => r.date).sort();
  const [first, last] = [all[0] ?? "", all[all.length - 1] ?? ""];
  const byMonth = new Map<string, MonthPlan>();
  for (const r of use) {
    const month = r.date.slice(0, 7);
    let p = byMonth.get(month);
    if (!p) {
      const end = new Date(Date.UTC(+month.slice(0, 4), +month.slice(5, 7), 0)).toISOString().slice(0, 10);
      p = { month, partial: first > `${month}-01` || last < end, paid: new Map(), other: 0, rows: 0 };
      byMonth.set(month, p);
    }
    p.rows++;
    if (r.commitment !== null) p.paid.set(r.commitment, round2((p.paid.get(r.commitment) ?? 0) + r.amount));
    else p.other = round2(p.other + r.amount);
  }
  return { months: [...byMonth.values()].sort((a, b) => a.month.localeCompare(b.month)), foreign };
}

const round2 = (v: number) => Math.round(v * 100) / 100;
