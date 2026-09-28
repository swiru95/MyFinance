import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmtMoney } from "@/lib/api";
import { INPUT_CURRENCIES } from "@/lib/types";
import type { MonthCommitment, MonthlyRecord } from "@/lib/types";
import { monthLabel, monthLabelLong } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";

interface Props {
  months: MonthlyRecord[];
  selected: string;
  onSelect: (month: string) => void;
  record: MonthlyRecord | null;
  base: string;
  onSaved: () => void | Promise<void>;
  hasBusinessIncome: boolean;
}

/** One checklist row, editable - amount kept as a string so the input can
 *  hold "", a partial number, etc. without fighting the user mid-edit. */
interface Row extends Omit<MonthCommitment, "amount"> {
  amount: string;
}

/** `amount` (in `from`) converted into `to`, mirroring the backend's
 *  routes.helpers.convert_currency - fx is `PriceService.rates()` (1 USD in
 *  each currency), fetched once via GET /api/prices. Falls back to no
 *  conversion before rates have loaded, which only briefly under- or
 *  over-states a mixed-currency total on first paint. */
function convertAmt(
  amount: number,
  from: string,
  to: string,
  fx: Record<string, number> | null
): number {
  if (from === to || !fx) return amount;
  const fromRate = fx[from] ?? 1;
  const toRate = fx[to] ?? 1;
  return amount * (toRate / fromRate);
}

const round2 = (n: number) => Math.round(n * 100) / 100;

/** The "month checklist": tick off which recurring commitments were paid
 *  this month (and correct the amount if one was unusual), then add
 *  everything else spent - actual_spent is derived from the two rather than
 *  typed directly. Saved with PATCH: a PUT here would carry this form's
 *  blank income default and erase whatever Income wrote for the month. */
export default function MonthEditorCard({
  months,
  selected,
  onSelect,
  record,
  base,
  onSaved,
  hasBusinessIncome,
}: Props) {
  const { t, locale } = useI18n();
  const [rows, setRows] = useState<Row[]>([]);
  const [otherSpent, setOtherSpent] = useState("");
  const [currency, setCurrency] = useState("PLN");
  const [notes, setNotes] = useState("");
  const [fx, setFx] = useState<Record<string, number> | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetched once - the rates barely move within one editing session, and
  // every conversion below is just this table's ratios.
  useEffect(() => {
    api.prices().then((p) => setFx(p.fx)).catch(() => setFx(null));
  }, []);

  // Load the selected month's checklist plus its notes/currency. Re-runs
  // when the record's updated_at changes (i.e. after a save) so "save, then
  // look again" shows exactly what was persisted, not just what was typed.
  useEffect(() => {
    let cancelled = false;
    setCurrency(record?.currency || base);
    setNotes(record?.notes ?? "");
    setMsg(null);
    setError(null);

    api
      .monthCommitments(selected)
      .then((list) => {
        if (cancelled) return;
        setRows(list.map((c) => ({ ...c, amount: String(c.amount) })));

        // Legacy record (one typed total, never saved through the
        // checklist): prefill other_spent as the remainder after the
        // default-paid commitments, rather than leaving it blank and
        // risking the user re-adding spend the old total already covered.
        const recCurrency = record?.currency || base;
        if (record?.breakdown) {
          setOtherSpent(String(record.other_spent ?? 0));
        } else if (record?.saved && (record?.actual_spent ?? 0) > 0) {
          const defaultPaidTotal = list.reduce(
            (sum, c) => sum + convertAmt(c.amount, c.currency, recCurrency, fx),
            0
          );
          setOtherSpent(String(Math.max(0, round2(record.actual_spent - defaultPaidTotal))));
        } else {
          setOtherSpent("");
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : t("common.failedLoad"));
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, record?.updated_at, fx]);

  function toggleRow(expenseId: number) {
    setRows((prev) =>
      prev.map((r) => (r.expense_id === expenseId ? { ...r, paid: !r.paid } : r))
    );
  }

  function setRowAmount(expenseId: number, amount: string) {
    setRows((prev) =>
      prev.map((r) => (r.expense_id === expenseId ? { ...r, amount } : r))
    );
  }

  const paidTotal = rows
    .filter((r) => r.paid)
    .reduce((sum, r) => sum + convertAmt(parseFloat(r.amount) || 0, r.currency, currency, fx), 0);
  const otherNum = parseFloat(otherSpent) || 0;
  const total = paidTotal + otherNum;

  // The "use what your accounts show" helper only compares like with like:
  // effective_spent is always in the base currency, so it is only offered
  // while the record itself is kept in that same currency - converting it
  // would need another FX hop on top of the per-row one above, for a figure
  // that is already an estimate.
  const showHelper =
    record?.effective_spent != null && currency === base && record.effective_spent - paidTotal > 0;
  const rest = showHelper ? round2(record!.effective_spent! - paidTotal) : 0;

  const isLegacy = !!record?.saved && !record?.breakdown && (record?.actual_spent ?? 0) > 0;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      await api.patchMonth(selected, {
        commitments: rows.map((r) => ({
          expense_id: r.expense_id,
          amount: parseFloat(r.amount) || 0,
          paid: r.paid,
        })),
        other_spent: otherNum,
        currency,
        notes,
      });
      setMsg(t("mon.saved", { month: monthLabel(selected, locale) }));
      await onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(false);
    }
  }

  const sourceRows = record?.income_sources ?? [];
  const sourcesTotal = record?.income_from_sources_in_base ?? 0;
  const incomeTotal = record?.income_in_base ?? 0;

  return (
    <form onSubmit={save} className="card max-w-xl space-y-4">
      <div>
        <label className="label" htmlFor="m-month">{t("mon.month")}</label>
        <select
          id="m-month"
          className="input"
          value={selected}
          onChange={(e) => onSelect(e.target.value)}
        >
          {months.map((m) => (
            <option key={m.month} value={m.month}>
              {monthLabel(m.month, locale)}
              {m.saved ? "" : t("mon.notFilled")}
            </option>
          ))}
        </select>
      </div>

      {sourceRows.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm dark:border-slate-800 dark:bg-slate-800/50">
          <p className="mb-1 font-medium">{t("mon.fromSources")}</p>
          <ul className="space-y-0.5">
            {sourceRows.map((s) => (
              <li key={s.source_id} className="flex justify-between gap-2">
                <span className="truncate">{s.name}</span>
                <span className="shrink-0 tabular-nums muted">
                  {fmtMoney(s.net_in_base, base, locale)}
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-1 flex justify-between border-t border-slate-200 pt-1 font-medium dark:border-slate-700">
            <span>{t("mon.fromSourcesTotal")}</span>
            <span className="tabular-nums">{fmtMoney(sourcesTotal, base, locale)}</span>
          </div>
        </div>
      )}

      {/* Income is read-only here - it is edited on /income now, both the
          typed "other income" figure and every source that feeds this total. */}
      <div>
        <p className="label">{t("exp.monthly.incomeLabel")}</p>
        <p className="text-lg font-semibold tabular-nums">
          {fmtMoney(incomeTotal, base, locale)}
        </p>
        <p className="mt-1 text-xs subtle">
          {t("exp.monthly.incomeHint")}{" "}
          <Link href="/income" className="underline hover:no-underline">
            {t("exp.monthly.incomeLink")}
          </Link>
        </p>
      </div>

      {/* 1. Commitments due this month - the checklist. */}
      <div>
        <p className="label">{t("mon.commitmentsTitle", { month: monthLabelLong(selected, locale) })}</p>
        {isLegacy && (
          <p className="mb-2 rounded-md bg-amber-50 px-2 py-1.5 text-xs text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
            {t("mon.legacyNote", { x: fmtMoney(record!.actual_spent, record!.currency, locale) })}
          </p>
        )}
        {rows.length === 0 ? (
          <p className="text-sm subtle">{t("mon.commitmentsEmpty")}</p>
        ) : (
          <ul className="space-y-2">
            {rows.map((r) => (
              <li
                key={r.expense_id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-800"
              >
                {/* min-w keeps the label from shrinking to fit next to the
                    amount field - without it flexbox shrinks the name to
                    nothing instead of wrapping the row onto its own line at
                    390px. */}
                <label className="flex min-w-[10rem] flex-1 items-center gap-2">
                  <input
                    type="checkbox"
                    className="h-4 w-4 shrink-0 rounded border-slate-300"
                    checked={r.paid}
                    onChange={() => toggleRow(r.expense_id)}
                  />
                  <span className="min-w-0 truncate text-sm">
                    {r.name}
                    {r.category && (
                      <span className="ml-1 subtle text-xs">({r.category})</span>
                    )}
                  </span>
                </label>
                <div className="flex shrink-0 items-center gap-1.5">
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    className="input w-24"
                    value={r.amount}
                    disabled={!r.paid}
                    onChange={(e) => setRowAmount(r.expense_id, e.target.value)}
                  />
                  <span className="w-10 text-xs subtle">{r.currency}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-1 text-xs subtle">{t("mon.commitmentsHint")}</p>
        {hasBusinessIncome && (
          <p className="mt-1 text-xs subtle">{t("mon.jdgNote")}</p>
        )}
      </div>

      {/* 2. Everything else spent, plus the record's currency. */}
      <div>
        <p className="label">{t("mon.otherTitle")}</p>
        <div className="grid grid-cols-2 gap-3">
          <input
            id="m-other-spent"
            className="input"
            type="number"
            step="0.01"
            min="0"
            value={otherSpent}
            onChange={(e) => setOtherSpent(e.target.value)}
            placeholder="0.00"
            aria-label={t("mon.otherTitle")}
          />
          <select
            id="m-currency"
            className="input"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            {INPUT_CURRENCIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <p className="mt-1 text-xs subtle">{t("mon.otherHint")}</p>
        {showHelper && rest > 0 && (
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs subtle">
            <span>
              {t("mon.otherHelper", {
                effective: fmtMoney(record!.effective_spent!, currency, locale),
                rest: fmtMoney(rest, currency, locale),
              })}
            </span>
            <button
              type="button"
              className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
              onClick={() => setOtherSpent(rest.toFixed(2))}
            >
              {t("mon.otherHelperButton", { rest: fmtMoney(rest, currency, locale) })}
            </button>
          </p>
        )}
      </div>

      {/* 3. Live total. */}
      <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm font-medium tabular-nums dark:bg-slate-800/50">
        {t("mon.totalLine", {
          month: monthLabelLong(selected, locale),
          paid: fmtMoney(paidTotal, currency, locale),
          other: fmtMoney(otherNum, currency, locale),
          total: fmtMoney(total, currency, locale),
        })}
      </p>

      {/* 4. Notes, save. */}
      <div>
        <label className="label" htmlFor="m-notes">{t("common.notes")}</label>
        <input
          id="m-notes"
          className="input"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {msg && <p className="banner-info">{msg}</p>}

      <button type="submit" className="btn-primary w-full" disabled={busy}>
        {busy
          ? t("common.saving")
          : t("mon.saveMonth", { month: monthLabel(selected, locale) })}
      </button>
    </form>
  );
}
