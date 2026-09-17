import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, fmtMoney, fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type {
  Allocation,
  BreakdownMode,
  ExpenseSummary,
  MonthlyAnalytics,
  Prices,
  Summary,
  ValueOverTime,
} from "@/lib/types";
import PortfolioChart from "@/components/PortfolioChart";
import AllocationChart from "@/components/AllocationChart";
import PortfolioProfile from "@/components/PortfolioProfile";
import { monthLabel } from "@/lib/chartTheme";
import { blendedRate, compound, SCENARIOS } from "@/lib/projection";
import RunwayChart from "@/components/RunwayChart";

export default function Dashboard() {
  const { t, td, locale } = useI18n();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [valueTime, setValueTime] = useState<ValueOverTime | null>(null);
  const [allocation, setAllocation] = useState<Allocation | null>(null);
  const [mode, setMode] = useState<BreakdownMode>("total");
  const [prices, setPrices] = useState<Prices | null>(null);
  const [expenses, setExpenses] = useState<ExpenseSummary | null>(null);
  // The runway chart needs the safe band per day and the commitments per
  // month, which the main series cannot supply: it follows whichever split
  // the user is looking at.
  const [profileSeries, setProfileSeries] = useState<ValueOverTime | null>(null);
  const [analytics, setAnalytics] = useState<MonthlyAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [s, a, p, e, ps, an] = await Promise.all([
          api.summary(),
          api.allocation(),
          api.prices(),
          api.expenseSummary(),
          api.valueOverTime("profile"),
          api.monthlyAnalytics(11, 12),
        ]);
        if (!alive) return;
        setSummary(s);
        setAllocation(a);
        setPrices(p);
        setExpenses(e);
        setProfileSeries(ps);
        setAnalytics(an);
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

  // The holistic bit: commitments and holdings are the same unit, so they can
  // be divided into each other. "Safe" is the band meant to be reachable in a
  // hurry, which is what a reserve has to be - measuring runway against the
  // whole portfolio would count a watch collection as emergency money.
  const RESERVE_MONTHS = 6;
  const monthlyCommitted = expenses?.monthly_total ?? 0;
  const safeValue =
    allocation?.by_profile.find((b) => b.profile === "safe")?.value ?? 0;
  const runwayMonths =
    monthlyCommitted > 0 ? safeValue / monthlyCommitted : null;
  const reserve =
    monthlyCommitted > 0
      ? { months: RESERVE_MONTHS, value: RESERVE_MONTHS * monthlyCommitted }
      : undefined;

  // Cover per month: the safe band as it stood at each month's last snapshot,
  // over that same month's commitments. Committed spend is derived per month
  // from the expense definitions, so a month the user never filled in still
  // has a denominator - only the portfolio side can be missing.
  // Expected return of the portfolio as held, and two years of scenarios off
  // the back of it. Contributions come from recorded behaviour; only the rate
  // is assumed, which is why it is spelled out under the chart.
  const PROJECT_MONTHS = 24;
  const expected = useMemo(() => blendedRate(allocation), [allocation]);
  const projection = useMemo(() => {
    if (!summary || !analytics || summary.total_value <= 0) return [];
    const recorded = analytics.timeline.filter((p) => p.income != null);
    const contribution =
      recorded.length > 0
        ? recorded.reduce((sum, p) => sum + (p.surplus ?? 0), 0) / recorded.length
        : 0;

    // Built field by field rather than through toISOString: that converts a
    // local midnight to UTC, which lands on the previous day for any zone east
    // of Greenwich and would label every point one day early.
    const ymd = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
        d.getDate(),
      ).padStart(2, "0")}`;
    const start = new Date();
    const months = Array.from({ length: PROJECT_MONTHS }, (_, i) =>
      // Day 0 of the next month is the last day of this one.
      ymd(new Date(start.getFullYear(), start.getMonth() + i + 1, 0)),
    );
    const series = Object.fromEntries(
      Object.entries(SCENARIOS).map(([name, factor]) => [
        name,
        compound(
          summary.total_value,
          expected.rate * factor,
          contribution,
          PROJECT_MONTHS,
        ),
      ]),
    ) as Record<keyof typeof SCENARIOS, number[]>;

    const today = ymd(start);
    return [
      {
        date: today,
        low: summary.total_value,
        base: summary.total_value,
        high: summary.total_value,
      },
      ...months.map((date, i) => ({
        date,
        low: series.low[i],
        base: series.base[i],
        high: series.high[i],
      })),
    ];
  }, [summary, analytics, expected.rate]);

  const cryptoShare =
    expected.lines.find((l) => l.category === "Crypto")?.share ?? 0;
  const avgContribution = useMemo(() => {
    const recorded = analytics?.timeline.filter((p) => p.income != null) ?? [];
    return recorded.length > 0
      ? recorded.reduce((sum, p) => sum + (p.surplus ?? 0), 0) / recorded.length
      : 0;
  }, [analytics]);

  const runway = useMemo(() => {
    const empty = {
      actual: [] as { month: string; months: number }[],
      projected: [] as { month: string; months: number }[],
      avgSurplus: 0,
      crossesAt: null as string | null,
      startsBelow: false,
    };
    if (!profileSeries || !analytics) return empty;

    const committed = new Map(analytics.timeline.map((p) => [p.month, p.committed]));
    const safeAtMonthEnd = new Map<string, number>();
    for (const row of profileSeries.rows) {
      safeAtMonthEnd.set(String(row.date).slice(0, 7), Number(row.safe ?? 0));
    }
    const history = Array.from(safeAtMonthEnd.entries()).sort(([a], [b]) =>
      a.localeCompare(b),
    );
    const actual = history.flatMap(([month, safe]) => {
      const due = committed.get(month) ?? 0;
      return due > 0 ? [{ month, months: safe / due }] : [];
    });
    if (actual.length === 0 || history.length === 0) return empty;

    // Only the numerator is guessed. Commitments come from the expense
    // definitions, so a loan that ends next June really does stop counting
    // then - the projection is not extrapolating that side at all.
    const recorded = analytics.timeline.filter((p) => p.income != null);
    if (recorded.length === 0) return { ...empty, actual };
    const avgSurplus =
      recorded.reduce((sum, p) => sum + (p.surplus ?? 0), 0) / recorded.length;

    const lastMonth = history[history.length - 1][0];
    let safe = history[history.length - 1][1];
    const projected: { month: string; months: number }[] = [
      // Start on the last real point so the dashed line joins the solid one
      // instead of floating away from it.
      { month: lastMonth, months: actual[actual.length - 1].months },
    ];
    // Which direction the crossing matters in depends on where cover stands
    // today. Below target the useful question is when it gets there; above it,
    // when it stops being there. Reporting "falls below" while already below
    // is just restating the present as if it were news.
    const startsBelow = actual[actual.length - 1].months < RESERVE_MONTHS;
    let crossesAt: string | null = null;
    for (const point of analytics.timeline) {
      if (point.month <= lastMonth || point.committed <= 0) continue;
      safe = Math.max(0, safe + avgSurplus);
      const months = safe / point.committed;
      projected.push({ month: point.month, months });
      if (crossesAt === null) {
        const crossed = startsBelow
          ? months >= RESERVE_MONTHS
          : months < RESERVE_MONTHS;
        if (crossed) crossesAt = point.month;
      }
    }
    return { actual, projected, avgSurplus, crossesAt, startsBelow };
  }, [profileSeries, analytics]);

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
          <p className="text-sm muted">{t("dash.monthlyCommitted")}</p>
          <p className="mt-1 text-3xl font-semibold tabular-nums">
            {expenses ? fmtMoney(monthlyCommitted, currency, locale) : "—"}
          </p>
          <p className="mt-1 text-xs subtle">{t("dash.fromExpenses")}</p>
        </div>
        <div className="card">
          <p className="text-sm muted">{t("dash.runway")}</p>
          <p className="mt-1 text-3xl font-semibold tabular-nums">
            {runwayMonths != null && safeValue > 0
              ? t("dash.runwayMonths", {
                  months: fmtNum(runwayMonths, 1, locale),
                })
              : "—"}
          </p>
          <p className="mt-1 text-xs subtle">
            {monthlyCommitted <= 0
              ? t("dash.runwayNeedExpenses")
              : safeValue <= 0
                ? t("dash.runwayNoSafe")
                : t("dash.runwayFrom")}
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
          reserve={reserve}
          projection={projection}
        />
        {mode === "total" && projection.length > 1 && expected.rate > 0 && (
          <div className="mt-2 space-y-1">
            <p className="text-xs subtle">
              {t("chart.projNote", {
                years: Math.round(PROJECT_MONTHS / 12),
                rate: fmtNum(expected.rate * 100, 1, locale),
                contribution: fmtMoney(avgContribution, currency, locale),
              })}
            </p>
            {cryptoShare > 0.05 && (
              <p className="text-xs subtle">
                {t("chart.projCrypto", {
                  share: fmtNum(cryptoShare * 100, 0, locale),
                })}
              </p>
            )}
            <details className="text-xs subtle">
              <summary className="cursor-pointer">{t("chart.projRates")}</summary>
              <ul className="mt-1 space-y-0.5">
                {expected.lines.map((l) => (
                  <li key={l.category} className="tabular-nums">
                    {td(l.category)}: {fmtNum(l.share * 100, 1, locale)}% ×{" "}
                    {fmtNum(l.rate * 100, 1, locale)}% ={" "}
                    {fmtNum(l.contribution * 100, 2, locale)}%
                  </li>
                ))}
              </ul>
            </details>
          </div>
        )}
      </div>

      {reserve && (
        <div className="card">
          <h2 className="text-lg font-semibold">{t("dash.runwayTitle")}</h2>
          <p className="mb-3 text-sm muted">{t("dash.runwaySubtitle")}</p>
          <RunwayChart
            points={runway.actual}
            projected={runway.projected}
            target={RESERVE_MONTHS}
          />
          <p className="mt-2 text-xs subtle">
            {runway.projected.length > 1
              ? t("dash.runwayAssumption", {
                  value: fmtMoney(runway.avgSurplus, currency, locale),
                })
              : t("dash.runwayNoProjection")}
            {runway.projected.length > 1 &&
              " " +
                (runway.crossesAt
                  ? t(
                      runway.startsBelow
                        ? "dash.runwayReaches"
                        : "dash.runwayCrosses",
                      {
                        months: RESERVE_MONTHS,
                        month: monthLabel(runway.crossesAt, locale),
                      },
                    )
                  : t(
                      runway.startsBelow
                        ? "dash.runwayStaysBelow"
                        : "dash.runwayStaysAbove",
                      { months: RESERVE_MONTHS },
                    ))}
          </p>
        </div>
      )}

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
                label: td(g.category),
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
