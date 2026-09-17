import { fmtDay, fmtMoney } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Expense } from "@/lib/types";

interface Props {
  expense: Expense;
  base: string;
  onEdit: () => void;
  onDelete: () => void;
}

/** Days from today until `iso`, counted in whole local days. */
function daysUntil(iso: string): number {
  const target = new Date(`${iso}T00:00:00`);
  const now = new Date();
  const todayMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target.getTime() - todayMidnight.getTime()) / 86_400_000);
}

const STATUS_KEYS: Record<Expense["status"], string> = {
  active: "exp.statusActive",
  scheduled: "exp.statusScheduled",
  ended: "exp.statusEnded",
};

const STATUS_STYLES: Record<Expense["status"], string> = {
  active: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  scheduled: "bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
  ended: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400",
};

export default function ExpenseRow({ expense, base, onEdit, onDelete }: Props) {
  const { t, td, locale } = useI18n();
  const ended = expense.status === "ended";

  function term() {
    if (expense.period === "once") {
      const days = daysUntil(expense.starts_on);
      if (days < 0) {
        return <>{t("exp.wasDue", { date: fmtDay(expense.starts_on, locale) })}</>;
      }
      return (
        <>
          {t("exp.due", { date: fmtDay(expense.starts_on, locale) })}
          {days <= 30 && (
            <span className="ml-1 text-amber-600 dark:text-amber-400">
              ·{" "}
              {days === 0 ? t("exp.dueToday") : t("exp.dueInDays", { days })}
            </span>
          )}
        </>
      );
    }
    if (!expense.ends_on) {
      return <>{t("exp.since", { date: fmtDay(expense.starts_on, locale) })}</>;
    }
    const days = daysUntil(expense.ends_on);
    return (
      <>
        {t("exp.until", { date: fmtDay(expense.ends_on, locale) })}
        {days >= 0 && days <= 90 && (
          <span className="ml-1 text-amber-600 dark:text-amber-400">
            · {t("exp.daysLeft", { days })}
          </span>
        )}
      </>
    );
  }

  return (
    <li
      className={`flex flex-wrap items-center justify-between gap-3 px-4 py-3 ${
        ended ? "opacity-60" : ""
      }`}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-slate-900 dark:text-slate-50">
            {expense.name}
          </span>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              STATUS_STYLES[expense.status]
            }`}
          >
            {t(STATUS_KEYS[expense.status])}
          </span>
          {expense.is_indefinite && (
            <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300">
              {t("exp.badgeOngoing")}
            </span>
          )}
          {expense.period === "once" && (
            <span className="rounded-full bg-violet-50 px-2 py-0.5 text-xs font-medium text-violet-700 dark:bg-violet-500/15 dark:text-violet-300">
              {t("exp.badgeOneOff")}
            </span>
          )}
          {expense.category && (
            <span className="text-xs subtle">{td(expense.category)}</span>
          )}
        </div>
        <p className="mt-0.5 text-xs muted">{term()}</p>
        {expense.notes && (
          <p className="mt-0.5 truncate text-xs subtle">{expense.notes}</p>
        )}
      </div>

      <div className="flex items-center gap-3">
        <div className="text-right">
          <p className="font-semibold tabular-nums text-slate-900 dark:text-slate-50">
            {fmtMoney(expense.amount_in_base, base, locale)}
            {expense.period === "monthly" && (
              <span className="text-xs font-normal subtle">{t("exp.perMonth")}</span>
            )}
          </p>
          {expense.currency !== base && (
            <p className="text-xs tabular-nums subtle">
              {fmtMoney(expense.amount, expense.currency, locale)}
            </p>
          )}
        </div>
        <button
          onClick={onEdit}
          className="btn-ghost text-xs"
          aria-label={`${t("common.edit")} ${expense.name}`}
        >
          {t("common.edit")}
        </button>
        <button
          onClick={onDelete}
          className="btn-ghost text-xs text-red-600"
          aria-label={`${t("common.delete")} ${expense.name}`}
        >
          ✕
        </button>
      </div>
    </li>
  );
}
