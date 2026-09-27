import { fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { FireResult } from "@/lib/fireTypes";

interface Props {
  levers: FireResult["levers"];
}

export default function LeversCard({ levers }: Props) {
  const { t, locale } = useI18n();

  return (
    <div className="card">
      <h2 className="text-lg font-semibold">{t("fire.levers.title")}</h2>
      {levers.baseline_years != null && (
        <p className="mt-1 text-xs subtle">
          {t("fire.levers.baseline", { years: fmtNum(levers.baseline_years, 1, locale) })}
        </p>
      )}
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <div>
          <p className="text-sm muted">{t("fire.levers.spendCut")}</p>
          <p className="mt-1 text-xl font-semibold tabular-nums">
            {levers.spend_cut.years != null
              ? t("fire.levers.yearsValue", { years: fmtNum(levers.spend_cut.years, 1, locale) })
              : "—"}
          </p>
        </div>
        <div>
          <p className="text-sm muted">{t("fire.levers.incomeRaise")}</p>
          <p className="mt-1 text-xl font-semibold tabular-nums">
            {levers.income_raise.years != null
              ? t("fire.levers.yearsValue", { years: fmtNum(levers.income_raise.years, 1, locale) })
              : "—"}
          </p>
        </div>
      </div>
      <p className="mt-3 text-sm muted">{t("fire.levers.explanation")}</p>
    </div>
  );
}
