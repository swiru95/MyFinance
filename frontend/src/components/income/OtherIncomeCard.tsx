import { useCallback, useEffect, useState } from "react";
import { api, fmtMoney } from "@/lib/api";
import { INPUT_CURRENCIES } from "@/lib/types";
import type { MonthlyRecord } from "@/lib/types";
import { monthLabel } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";

const currentMonthKey = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
};

interface Props {
  base: string;
}

/** Edits MonthlyRecord.income - the typed "other income" figure, for
 *  anything not covered by a recurring source. Expenses edits actual_spent
 *  on the same row; both save with PATCH so neither page's write clobbers
 *  the other's field (see backend/src/routes/monthly.py::patch_month). */
export default function OtherIncomeCard({ base }: Props) {
  const { t, locale } = useI18n();
  const [months, setMonths] = useState<MonthlyRecord[]>([]);
  const [selected, setSelected] = useState(currentMonthKey());
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState(base);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setMonths(await api.months());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedLoad"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Load the selected month's typed income into the editor.
  useEffect(() => {
    const record = months.find((m) => m.month === selected);
    setAmount(record?.income ? String(record.income) : "");
    setCurrency(record?.currency || base);
    setMsg(null);
  }, [months, selected, base]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      await api.patchMonth(selected, {
        income: parseFloat(amount) || 0,
        currency,
      });
      setMsg(t("mon.saved", { month: monthLabel(selected, locale) }));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(false);
    }
  }

  const withIncome = months
    .filter((m) => m.income > 0)
    .sort((a, b) => (a.month < b.month ? 1 : -1));

  return (
    <div className="card space-y-3">
      <div>
        <h2 className="text-lg font-semibold">{t("oi.title")}</h2>
        <p className="mt-1 text-sm muted">{t("oi.subtitle")}</p>
      </div>

      <form onSubmit={save} className="grid gap-3 sm:grid-cols-4 sm:items-end">
        <div>
          <label className="label" htmlFor="oi-month">{t("mon.month")}</label>
          <select
            id="oi-month"
            className="input"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            {months.map((m) => (
              <option key={m.month} value={m.month}>{monthLabel(m.month, locale)}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="oi-amount">{t("common.amount")}</label>
          <input
            id="oi-amount"
            className="input"
            type="number"
            step="0.01"
            min="0"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
          />
        </div>
        <div>
          <label className="label" htmlFor="oi-currency">{t("common.currency")}</label>
          <select
            id="oi-currency"
            className="input"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            {INPUT_CURRENCIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy
            ? t("common.saving")
            : t("mon.saveMonth", { month: monthLabel(selected, locale) })}
        </button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {msg && <p className="banner-info">{msg}</p>}

      <div>
        <p className="text-xs font-medium muted">{t("oi.recordedTitle")}</p>
        {withIncome.length === 0 ? (
          <p className="mt-1 text-xs subtle">{t("oi.recordedEmpty")}</p>
        ) : (
          <ul className="mt-1 space-y-0.5 text-sm">
            {withIncome.slice(0, 6).map((m) => (
              <li key={m.month} className="flex justify-between gap-2">
                <span>{monthLabel(m.month, locale)}</span>
                <span className="tabular-nums muted">
                  {fmtMoney(m.income, m.currency, locale)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
