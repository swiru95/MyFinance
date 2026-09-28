import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { MonthlyAnalytics, MonthlyRecord } from "@/lib/types";
import { useI18n } from "@/lib/i18n";
import { useFeatures } from "@/lib/features";
import BudgetTimelineChart from "@/components/BudgetTimelineChart";
import SavingsRateChart from "@/components/SavingsRateChart";
import CategoryTrendChart from "@/components/CategoryTrendChart";
import MonthEditorCard from "./MonthEditorCard";
import MonthStatTiles from "./MonthStatTiles";
import RecordedMonthsTable from "./RecordedMonthsTable";
import Disclosure from "@/components/Disclosure";

const currentMonthKey = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
};

/** What used to be the whole /monthly page: actual spend, cash-flow
 *  analytics and the recorded-months table, now a section of /expenses since
 *  income moved to /income and there is nothing else left to give it its own
 *  page. `id="monthly"` is the target of the /monthly -> /expenses#monthly
 *  redirect that keeps old links working. */
export default function MonthlySection() {
  const { t } = useI18n();
  const { portfolio } = useFeatures();
  const [months, setMonths] = useState<MonthlyRecord[]>([]);
  const [analytics, setAnalytics] = useState<MonthlyAnalytics | null>(null);
  const [selected, setSelected] = useState<string>(currentMonthKey());
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [list, stats] = await Promise.all([
        api.months(),
        api.monthlyAnalytics(11, 12),
      ]);
      setMonths(list);
      setAnalytics(stats);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedLoad"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const record = useMemo(
    () => months.find((m) => m.month === selected) ?? null,
    [months, selected]
  );
  const base = analytics?.base_currency ?? record?.base_currency ?? "PLN";

  return (
    <div id="monthly" className="scroll-mt-24 space-y-6">
      <div>
        <h2 className="text-xl font-semibold">{t("exp.monthly.title")}</h2>
        <p className="text-sm muted">{t("exp.monthly.subtitle")}</p>
      </div>

      {error && <div className="banner-error">{error}</div>}

      <MonthEditorCard
        months={months}
        selected={selected}
        onSelect={setSelected}
        record={record}
        base={base}
        onSaved={refresh}
      />

      <Disclosure title={t("exp.monthly.showAnalysis")} storageKey="myfinance-expenses-analysis-open">
        <MonthStatTiles
          record={record}
          analytics={analytics}
          base={base}
          showEffective={portfolio}
        />

        <div className="card">
          <h3 className="text-lg font-semibold">{t("mon.chartTitle")}</h3>
          <p className="mb-3 text-sm muted">{t("mon.chartSubtitle")}</p>
          {portfolio && <p className="mb-3 text-xs subtle">{t("mon.effectiveNote")}</p>}
          <BudgetTimelineChart
            points={analytics?.timeline ?? []}
            currency={base}
            currentMonth={currentMonthKey()}
            showEffective={portfolio}
          />
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card">
            <h3 className="text-lg font-semibold">{t("mon.savingsTitle")}</h3>
            <p className="mb-3 text-sm muted">{t("mon.savingsSubtitle")}</p>
            <SavingsRateChart points={analytics?.timeline ?? []} />
          </div>
          <div className="card">
            <h3 className="text-lg font-semibold">{t("mon.categoryTitle")}</h3>
            <p className="mb-3 text-sm muted">{t("mon.categorySubtitle")}</p>
            <CategoryTrendChart
              series={analytics?.category_series ?? []}
              categories={analytics?.categories ?? []}
              currency={base}
            />
          </div>
        </div>

        <RecordedMonthsTable months={months} base={base} />
      </Disclosure>
    </div>
  );
}
