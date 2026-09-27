import { fmtMoney, fmtNum } from "@/lib/api";
import type { MonthlyAnalytics, MonthlyRecord } from "@/lib/types";
import { useI18n } from "@/lib/i18n";
import InfoTip from "@/components/InfoTip";

interface Props {
  record: MonthlyRecord | null;
  analytics: MonthlyAnalytics | null;
  base: string;
  /** Effective spend is derived from portfolio history (income minus the
   *  change in what is held) - without portfolio there is nothing to derive
   *  it from, so its tile is skipped rather than shown stuck on "—". */
  showEffective: boolean;
}

export default function MonthStatTiles({ record, analytics, base, showEffective }: Props) {
  const { t, locale } = useI18n();
  const surplus = record?.surplus ?? 0;
  const surplusTone =
    surplus > 0
      ? "text-emerald-600 dark:text-emerald-400"
      : surplus < 0
        ? "text-red-600 dark:text-red-400"
        : "";
  const variance = record?.variance ?? 0;

  return (
    <div className="grid auto-rows-min content-start gap-4 sm:grid-cols-2 lg:col-span-2">
      <div className="card">
        <p className="text-sm muted">{t("mon.surplus")}</p>
        <p className={`mt-1 text-2xl font-semibold tabular-nums ${surplusTone}`}>
          {record ? fmtMoney(surplus, base, locale) : "—"}
        </p>
        <p className="mt-1 text-xs subtle">
          {record?.savings_rate != null
            ? t("mon.savedPct", { rate: fmtNum(record.savings_rate, 1, locale) })
            : t("mon.addIncomeHint")}
        </p>
      </div>
      <div className="card">
        <p className="text-sm muted">{t("mon.actualVsCommitted")}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">
          {record ? fmtMoney(variance, base, locale) : "—"}
        </p>
        <p className="mt-1 text-xs subtle">
          {variance > 0
            ? t("mon.above")
            : variance < 0
              ? t("mon.below")
              : t("mon.matches")}
        </p>
      </div>
      {showEffective && (
        <div className="card">
          <p className="flex items-center text-sm muted">
            {t("mon.effective")}
            <InfoTip text={t("gloss.effectiveSpend")} label={t("mon.effective")} />
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">
            {record?.effective_spent != null
              ? fmtMoney(record.effective_spent, base, locale)
              : "—"}
          </p>
          <p className="mt-1 text-xs subtle">{t("mon.effectiveHint")}</p>
          <p className="mt-1 text-xs subtle">
            {record?.effective_spent != null && record.wallet_change != null
              ? t("mon.walletChange", {
                  value: `${record.wallet_change >= 0 ? "+" : ""}${fmtMoney(
                    record.wallet_change,
                    base,
                    locale,
                  )}`,
                })
              : t("mon.effectiveUnavailable")}
          </p>
        </div>
      )}
      <div className="card">
        <p className="flex items-center text-sm muted">
          {t("mon.avgSavings")}
          <InfoTip text={t("gloss.savingsRate")} label={t("mon.avgSavings")} />
        </p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">
          {analytics?.avg_savings_rate != null
            ? `${fmtNum(analytics.avg_savings_rate, 1, locale)}%`
            : "—"}
        </p>
        <p className="mt-1 text-xs subtle">
          {t(
            analytics?.months_recorded === 1
              ? "mon.acrossMonth"
              : "mon.acrossMonths",
            { count: analytics?.months_recorded ?? 0 }
          )}
        </p>
      </div>
    </div>
  );
}
