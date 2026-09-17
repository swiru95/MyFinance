import Link from "next/link";
import { useEffect, useState } from "react";
import { api, fmtMoney } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Allocation, Prices, Summary, ValueOverTime } from "@/lib/types";
import PortfolioChart from "@/components/PortfolioChart";
import AllocationChart from "@/components/AllocationChart";

export default function Dashboard() {
  const { t, locale } = useI18n();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [valueTime, setValueTime] = useState<ValueOverTime | null>(null);
  const [allocation, setAllocation] = useState<Allocation | null>(null);
  const [prices, setPrices] = useState<Prices | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [s, v, a, p] = await Promise.all([
          api.summary(),
          api.valueOverTime(),
          api.allocation(),
          api.prices(),
        ]);
        if (!alive) return;
        setSummary(s);
        setValueTime(v);
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
        <PortfolioChart points={valueTime?.points ?? []} currency={currency} />
      </div>

      <div className="card">
        <h2 className="mb-4 text-lg font-semibold">{t("dash.allocation")}</h2>
        <AllocationChart
          slices={(allocation?.by_category ?? []).map((g) => ({
            key: g.category,
            label: g.category,
            icon: g.icon,
            value: g.value,
            percent: g.percent,
          }))}
          currency={currency}
        />
      </div>
    </div>
  );
}
