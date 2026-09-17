import Link from "next/link";
import { useEffect, useState } from "react";
import { api, fmtMoney } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Allocation, BreakdownMode, Prices, Summary, ValueOverTime } from "@/lib/types";
import PortfolioChart from "@/components/PortfolioChart";
import AllocationChart from "@/components/AllocationChart";
import PortfolioProfile from "@/components/PortfolioProfile";

export default function Dashboard() {
  const { t, locale } = useI18n();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [valueTime, setValueTime] = useState<ValueOverTime | null>(null);
  const [allocation, setAllocation] = useState<Allocation | null>(null);
  const [mode, setMode] = useState<BreakdownMode>("total");
  const [prices, setPrices] = useState<Prices | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [s, a, p] = await Promise.all([
          api.summary(),
          api.allocation(),
          api.prices(),
        ]);
        if (!alive) return;
        setSummary(s);
        setAllocation(a);
        setPrices(p);
        setError(null);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : t("common.failedLoad"));
      }
    }
    load();
    const id = setInterval(load, 30000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  // The time series is the only thing the split affects, so it reloads on its
  // own rather than pulling the whole dashboard down with it.
  useEffect(() => {
    let alive = true;
    async function loadSeries() {
      try {
        const v = await api.valueOverTime(mode);
        if (alive) setValueTime(v);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : t("common.failedLoad"));
      }
    }
    loadSeries();
    const id = setInterval(loadSeries, 30000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [mode]);

  const currency = summary?.base_currency ?? "PLN";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t("dash.title")}</h1>
          <p className="text-sm muted">
            {t("dash.baseCurrency")}: <span className="font-medium">{currency}</span>
          </p>
        </div>
        <Link href="/positions" className="btn-primary">
          {t("dash.addPosition")}
        </Link>
      </div>

      {error && (
        <div className="banner-error">
          {error}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="card">
          <p className="text-sm muted">{t("dash.total")}</p>
          <p className="mt-1 text-3xl font-semibold tabular-nums">
            {summary ? fmtMoney(summary.total_value, currency, locale) : "—"}
          </p>
        </div>
        <div className="card">
          <p className="text-sm muted">{t("dash.goldPerGram")}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">
            {prices ? fmtMoney(prices.gold_per_gram, currency, locale) : "—"}
          </p>
        </div>
        <div className="card">
          <p className="text-sm muted">{t("dash.btcSol")}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">
            {prices ? `${fmtMoney(prices.crypto.BTC, currency, locale)} · ${fmtMoney(prices.crypto.SOL, currency, locale)}` : "—"}
          </p>
        </div>
      </div>

      <div className="card">
        <h2 className="mb-4 text-lg font-semibold">{t("dash.valueOverTime")}</h2>
        <PortfolioChart
          rows={valueTime?.rows ?? []}
          keys={valueTime?.keys ?? []}
          mode={mode}
          onModeChange={setMode}
          currency={currency}
        />
      </div>

      <div className="card">
        <h2 className="mb-4 text-lg font-semibold">{t("dash.breakdown")}</h2>
        <div className="grid gap-8 md:grid-cols-2">
          <section>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide subtle">
              {t("dash.allocation")}
            </h3>
            <AllocationChart
              currency={currency}
              slices={(allocation?.by_category ?? []).map((g) => ({
                key: g.category,
                label: g.category,
                icon: g.icon,
                value: g.value,
                percent: g.percent,
              }))}
            />
          </section>
          <section>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide subtle">
              {t("dash.profile")}
            </h3>
            <PortfolioProfile
              bands={allocation?.by_profile ?? []}
              currency={currency}
            />
          </section>
        </div>
      </div>
    </div>
  );
}
