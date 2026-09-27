import { fmtMoney } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { BusinessContribution } from "@/lib/types";

interface Props {
  rows: BusinessContribution[];
  base: string;
}

/** Read-only rows for each active B2B source's ZUS + health contribution.
 *
 * These are never typed expenses - they are computed from the source's own
 * ZUS stage / tax form (services/business_costs.py) and are already
 * subtracted from that source's net income (services/income.py's
 * source_year). Shown here, right under the recurring list, purely so the
 * user can see what is driving the gap between monthly_total and
 * monthly_total_personal. */
export default function BusinessContributions({ rows, base }: Props) {
  const { t, locale } = useI18n();
  if (rows.length === 0) return null;

  return (
    <div className="card p-0">
      <h2 className="border-b border-slate-200 dark:border-slate-800 px-4 py-3 text-lg font-semibold">
        {t("exp.business.title")}
      </h2>
      <ul className="divide-y divide-slate-100 dark:divide-slate-800">
        {rows.map((r) => (
          <li key={r.source_id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-slate-900 dark:text-slate-50">
                  {t("exp.business.rowName", { name: r.name })}
                </span>
                <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300">
                  {t("exp.business.badge")}
                </span>
              </div>
              <p className="mt-0.5 text-xs muted">
                {t("exp.business.social")} {fmtMoney(r.social, base, locale)} ·{" "}
                {t("exp.business.health")} {fmtMoney(r.health_fixed, base, locale)}
              </p>
            </div>
            <p className="font-semibold tabular-nums text-slate-900 dark:text-slate-50">
              {fmtMoney(r.total, base, locale)}
            </p>
          </li>
        ))}
      </ul>
      <p className="border-t border-slate-100 px-4 py-2 text-xs subtle dark:border-slate-800">
        {t("exp.business.note")}
      </p>
    </div>
  );
}
