import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fmtMoney } from "@/lib/api";
import { INPUT_CURRENCIES } from "@/lib/types";
import type { MonthlyRecord } from "@/lib/types";
import { monthLabel } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";

interface Props {
  months: MonthlyRecord[];
  selected: string;
  onSelect: (month: string) => void;
  record: MonthlyRecord | null;
  base: string;
  onSaved: () => void | Promise<void>;
}

/** Actual spend, notes and the record's currency - not income, which the
 *  Income page now owns. Saved with PATCH: a PUT here would carry this
 *  form's blank income default and erase whatever Income wrote for the
 *  month. */
export default function MonthEditorCard({
  months,
  selected,
  onSelect,
  record,
  base,
  onSaved,
}: Props) {
  const { t, locale } = useI18n();
  const [spent, setSpent] = useState("");
  const [currency, setCurrency] = useState("PLN");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load the selected month's figures into the editor.
  useEffect(() => {
    setSpent(record?.actual_spent ? String(record.actual_spent) : "");
    setCurrency(record?.currency || base);
    setNotes(record?.notes ?? "");
    setMsg(null);
  }, [record, base]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      await api.patchMonth(selected, {
        actual_spent: parseFloat(spent) || 0,
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
    <form onSubmit={save} className="card max-w-xl space-y-3">
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

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label" htmlFor="m-spent">{t("mon.actualSpent")}</label>
          <input
            id="m-spent"
            className="input"
            type="number"
            step="0.01"
            min="0"
            value={spent}
            onChange={(e) => setSpent(e.target.value)}
            placeholder="0.00"
          />
          <p className="mt-1 text-xs subtle">{t("mon.actualSpentHint")}</p>
        </div>
        <div>
          <label className="label" htmlFor="m-currency">{t("common.currency")}</label>
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
      </div>

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
