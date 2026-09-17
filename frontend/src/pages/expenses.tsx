import { useCallback, useEffect, useState } from "react";
import { api, fmtDay, fmtMoney, fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Expense, ExpenseSummary } from "@/lib/types";
import ExpenseForm from "@/components/ExpenseForm";
import ExpenseRow from "@/components/ExpenseRow";

type Filter = "active" | "all";

export default function ExpensesPage() {
  const { t, td, locale } = useI18n();
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [summary, setSummary] = useState<ExpenseSummary | null>(null);
  const [filter, setFilter] = useState<Filter>("active");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Expense | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [list, sum] = await Promise.all([api.expenses(), api.expenseSummary()]);
      setExpenses(list);
      setSummary(sum);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedLoad"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const base = summary?.base_currency ?? "PLN";
  const visible = expenses.filter((e) =>
    filter === "all" ? true : e.status !== "ended"
  );
  const monthly = visible.filter((e) => e.period === "monthly");
  const oneOffs = visible.filter((e) => e.period === "once");

  async function remove(expense: Expense) {
    if (!confirm(t("exp.confirmDelete", { name: expense.name }))) return;
    try {
      await api.deleteExpense(expense.id);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedDelete"));
    }
  }

  function openNew() {
    setEditing(null);
    setFormOpen(true);
  }

  function openEdit(expense: Expense) {
    setEditing(expense);
    setFormOpen(true);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{t("exp.title")}</h1>
          <p className="text-sm muted">
            {t("exp.subtitle")}
          </p>
        </div>
        <button onClick={openNew} className="btn-primary">
          {t("exp.add")}
        </button>
      </div>

      {error && (
        <div className="banner-error">
          {error}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="card">
          <p className="text-sm muted">{t("exp.monthlyCommitment")}</p>
          <p className="mt-1 text-3xl font-semibold tabular-nums">
            {summary ? fmtMoney(summary.monthly_total, base, locale) : "—"}
          </p>
          <p className="mt-1 text-xs subtle">
            {summary
              ? t("exp.activeOngoing", {
                  active: summary.active_count,
                  ongoing: summary.indefinite_count,
                })
              : ""}
          </p>
        </div>
        <div className="card">
          <p className="text-sm muted">{t("exp.endingSoon")}</p>
          {summary && summary.ending_soon.length > 0 ? (
            <ul className="mt-2 space-y-1 text-sm">
              {summary.ending_soon.map((e) => (
                <li key={e.id} className="flex justify-between gap-2">
                  <span className="truncate">{e.name}</span>
                  <span className="shrink-0 tabular-nums muted">
                    {e.ends_on ? fmtDay(e.ends_on, locale) : ""}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm subtle">{t("exp.nothingEnding")}</p>
          )}
        </div>
        <div className="card">
          <p className="text-sm muted">{t("exp.upcoming")}</p>
          {summary && summary.upcoming.length > 0 ? (
            <ul className="mt-2 space-y-1 text-sm">
              {summary.upcoming.slice(0, 4).map((e) => (
                <li key={e.id} className="flex justify-between gap-2">
                  <span className="truncate">{e.name}</span>
                  <span className="shrink-0 tabular-nums muted">
                    {fmtMoney(e.amount_in_base, base, locale)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm subtle">{t("exp.noneScheduled")}</p>
          )}
        </div>
      </div>

      {summary && summary.by_category.length > 0 && (
        <div className="card">
          <h2 className="mb-3 text-lg font-semibold">{t("exp.byCategory")}</h2>
          <ul className="space-y-2">
            {summary.by_category.map((c) => {
              const pct = summary.monthly_total
                ? (100 * c.total) / summary.monthly_total
                : 0;
              return (
                <li key={c.category}>
                  <div className="flex justify-between text-sm">
                    <span>{td(c.category)}</span>
                    <span className="tabular-nums muted">
                      {fmtNum(pct, 0, locale)}% · {fmtMoney(c.total, base, locale)}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 w-full rounded-full bg-slate-100 dark:bg-slate-800">
                    <div
                      className="h-1.5 rounded-full bg-brand-600"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div className="flex gap-2">
        {(["active", "all"] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              filter === f
                ? "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100"
                : "text-slate-600 hover:bg-slate-100 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            {f === "active" ? t("exp.filterActive") : t("exp.filterAll")}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-sm subtle">{t("common.loading")}</p>
      ) : visible.length === 0 ? (
        <div className="card grid h-40 place-items-center text-sm subtle">
          {t("exp.empty")}
        </div>
      ) : (
        <div className="space-y-6">
          {monthly.length > 0 && (
            <div className="card p-0">
              <h2 className="border-b border-slate-200 dark:border-slate-800 px-4 py-3 text-lg font-semibold">
                {t("exp.everyMonth")}
              </h2>
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {monthly.map((e) => (
                  <ExpenseRow
                    key={e.id}
                    expense={e}
                    base={base}
                    onEdit={() => openEdit(e)}
                    onDelete={() => remove(e)}
                  />
                ))}
              </ul>
            </div>
          )}

          {oneOffs.length > 0 && (
            <div className="card p-0">
              <h2 className="border-b border-slate-200 dark:border-slate-800 px-4 py-3 text-lg font-semibold">
                {t("exp.oneOffSection")}
              </h2>
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {oneOffs.map((e) => (
                  <ExpenseRow
                    key={e.id}
                    expense={e}
                    base={base}
                    onEdit={() => openEdit(e)}
                    onDelete={() => remove(e)}
                  />
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {formOpen && (
        <div className="fixed inset-0 z-20 grid place-items-center overflow-y-auto bg-black/40 p-4">
          <div className="card my-8 w-full max-w-sm">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                {editing ? t("exp.editTitle") : t("exp.new")}
              </h2>
              <button onClick={() => setFormOpen(false)} className="subtle">
                ✕
              </button>
            </div>
            <ExpenseForm
              base={base}
              existing={editing}
              onDone={() => {
                setFormOpen(false);
                setEditing(null);
                refresh();
              }}
              onCancel={() => {
                setFormOpen(false);
                setEditing(null);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
