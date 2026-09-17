import { useState } from "react";
import { api } from "@/lib/api";
import { INPUT_CURRENCIES } from "@/lib/types";
import { useI18n } from "@/lib/i18n";
import type { Expense, ExpenseInput, ExpensePeriod } from "@/lib/types";

interface Props {
  base: string;
  existing?: Expense | null;
  onDone: () => void;
  onCancel: () => void;
}

const today = () => new Date().toISOString().slice(0, 10);

export default function ExpenseForm({ base, existing, onDone, onCancel }: Props) {
  const { t } = useI18n();
  const [name, setName] = useState(existing?.name ?? "");
  const [amount, setAmount] = useState(existing ? String(existing.amount) : "");
  const [currency, setCurrency] = useState(existing?.currency ?? base);
  const [period, setPeriod] = useState<ExpensePeriod>(existing?.period ?? "monthly");
  const [category, setCategory] = useState(existing?.category ?? "");
  const [startsOn, setStartsOn] = useState(existing?.starts_on ?? today());
  // "Runs indefinitely" is the default for a new monthly commitment.
  const [hasEnd, setHasEnd] = useState(Boolean(existing?.ends_on));
  const [endsOn, setEndsOn] = useState(existing?.ends_on ?? "");
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isOnce = period === "once";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const value = parseFloat(amount);
    if (isNaN(value) || value <= 0) {
      setError(t("exp.amountPositive"));
      return;
    }
    if (!isOnce && hasEnd && endsOn && endsOn < startsOn) {
      setError(t("exp.endAfterStart"));
      return;
    }
    const payload: ExpenseInput = {
      name: name.trim(),
      amount: value,
      currency,
      period,
      category: category.trim(),
      starts_on: startsOn,
      ends_on: isOnce || !hasEnd ? null : endsOn || null,
      notes: notes.trim(),
    };
    setBusy(true);
    setError(null);
    try {
      if (existing) await api.updateExpense(existing.id, payload);
      else await api.createExpense(payload);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="label" htmlFor="exp-name">{t("exp.name")}</label>
        <input
          id="exp-name"
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("exp.namePlaceholder")}
          required
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label" htmlFor="exp-amount">{t("common.amount")}</label>
          <input
            id="exp-amount"
            className="input"
            type="number"
            step="0.01"
            min="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
            required
          />
        </div>
        <div>
          <label className="label" htmlFor="exp-currency">{t("common.currency")}</label>
          <select
            id="exp-currency"
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
        <label className="label">{t("exp.howOften")}</label>
        <div className="flex gap-2">
          {(["monthly", "once"] as ExpensePeriod[]).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPeriod(p)}
              className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium transition ${
                period === p
                  ? "border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100"
                  : "border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              {p === "monthly" ? t("exp.everyMonthOption") : t("exp.onceOption")}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="label" htmlFor="exp-start">
          {isOnce ? t("exp.dueDate") : t("exp.firstPayment")}
        </label>
        <input
          id="exp-start"
          className="input"
          type="date"
          value={startsOn}
          onChange={(e) => setStartsOn(e.target.value)}
          required
        />
      </div>

      {!isOnce && (
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-3">
          <div className="flex items-center gap-2">
            {/* Sibling + htmlFor rather than nesting: a checkbox inside its own
                label can receive the click twice (once direct, once forwarded
                by the label) and cancel itself out. */}
            <input
              id="exp-has-end"
              type="checkbox"
              checked={hasEnd}
              onChange={(e) => setHasEnd(e.target.checked)}
            />
            <label
              htmlFor="exp-has-end"
              className="text-sm font-medium text-slate-700 dark:text-slate-200"
            >
              {t("exp.hasEnd")}
            </label>
          </div>
          {hasEnd ? (
            <input
              className="input mt-2"
              type="date"
              value={endsOn}
              min={startsOn}
              onChange={(e) => setEndsOn(e.target.value)}
              required
            />
          ) : (
            <p className="mt-1 text-xs muted">
              {t("exp.indefiniteHint")}
            </p>
          )}
        </div>
      )}

      <div>
        <label className="label" htmlFor="exp-category">{t("exp.category")}</label>
        <input
          id="exp-category"
          className="input"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder={t("exp.categoryPlaceholder")}
        />
      </div>

      <div>
        <label className="label" htmlFor="exp-notes">{t("common.notes")}</label>
        <input
          id="exp-notes"
          className="input"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button type="button" onClick={onCancel} className="btn-ghost flex-1">
          {t("common.cancel")}
        </button>
        <button type="submit" className="btn-primary flex-1" disabled={busy}>
          {busy
            ? t("common.saving")
            : existing
              ? t("exp.saveChanges")
              : t("exp.addButton")}
        </button>
      </div>
    </form>
  );
}
