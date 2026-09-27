import { fmtMoney, fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { FireResult } from "@/lib/fireTypes";

interface Props {
  result: FireResult;
  base: string;
}

export default function HeadlineStats({ result, base }: Props) {
  const { t, locale } = useI18n();
  const progressPct =
    result.progress != null ? Math.max(0, Math.min(result.progress * 100, 100)) : null;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div className="card">
        <p className="text-sm muted">{t("fire.stat.fiNumber")}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">
          {fmtMoney(result.targets.regular, base, locale)}
        </p>
        <p className="mt-1 text-xs subtle">
          {t("fire.stat.fiNumberAt", { age: fmtNum(result.targets_age, 0, locale) })}
        </p>
      </div>

      <div className="card">
        <p className="text-sm muted">{t("fire.stat.progress")}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">
          {progressPct != null ? `${fmtNum(progressPct, 0, locale)}%` : "—"}
        </p>
        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
          <div
            className="h-full rounded-full bg-brand-600"
            style={{ width: `${progressPct ?? 0}%` }}
          />
        </div>
      </div>

      <div className="card">
        <p className="text-sm muted">{t("fire.stat.yearsToFi")}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">
          {result.simulate.years != null && result.simulate.fi_age != null
            ? t("fire.stat.yearsValue", {
                years: fmtNum(result.simulate.years, 1, locale),
                age: fmtNum(result.simulate.fi_age, 0, locale),
              })
            : "—"}
        </p>
        {result.simulate.years == null && (
          <p className="mt-1 text-xs subtle">{t("fire.stat.notReachable")}</p>
        )}
      </div>

      <div className="card">
        <p className="text-sm muted">{t("fire.stat.coast")}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">
          {fmtMoney(result.coast.number, base, locale)}
        </p>
        <p
          className={`mt-1 text-xs ${
            result.coast.reached ? "text-emerald-600 dark:text-emerald-400" : "subtle"
          }`}
        >
          {result.coast.reached ? t("fire.stat.coastReached") : t("fire.stat.coastNotYet")}
        </p>
      </div>
    </div>
  );
}
