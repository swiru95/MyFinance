import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  ReferenceLine,
} from "recharts";
import { fmtMoney, fmtNum } from "@/lib/api";
import { useChartTheme, profileColor } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";
import type { BreakdownMode, SeriesKey, ValueRow } from "@/lib/types";

const MODES: BreakdownMode[] = ["total", "asset", "category", "profile"];

interface Props {
  rows: ValueRow[];
  keys: SeriesKey[];
  mode: BreakdownMode;
  onModeChange: (mode: BreakdownMode) => void;
  currency: string;
  /** Months of committed spend the reserve line marks, and its value. Omitted
   *  when there are no recurring expenses to derive a target from. */
  reserve?: { months: number; value: number };
  /** Monthly scenario values appended after the recorded history. Only drawn
   *  in "total" mode: the split views are about what the portfolio is made of,
   *  and a forecast of composition would be a much bigger claim than a
   *  forecast of size. */
  projection?: { date: string; low: number; base: number; high: number }[];
}

export default function PortfolioChart({
  rows,
  keys,
  mode,
  onModeChange,
  currency,
  reserve,
  projection = [],
}: Props) {
  const { t, td, locale } = useI18n();
  const theme = useChartTheme();

  const showProjection = mode === "total" && projection.length > 1;
  const fmtLabel = (iso: string) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString(locale, {
      month: "short",
      day: "numeric",
    });

  const data = [
    ...rows.map((r) => ({ ...r, label: fmtLabel(r.date) })),
    ...(showProjection
      ? // The first projected point repeats today's total, so the dashed lines
        // start from the end of the solid one instead of beside it.
        projection.slice(1).map((p) => ({
          date: p.date,
          // Month and year, not day and month: these points are monthly and
          // run two years out, where "28 lut" alone names three different days.
          label: new Date(`${p.date}T00:00:00`).toLocaleDateString(locale, {
            month: "short",
            year: "2-digit",
          }),
          projLow: p.low,
          projBase: p.base,
          projHigh: p.high,
        }))
      : []),
  ];

  const labelFor = (k: SeriesKey) =>
    k.key === "__other__"
      ? `${t("chart.other")} (${k.members?.length ?? 0})`
      : mode === "profile"
        ? t(`profile.${k.label}`)
        : td(k.label);

  // Filters live in one row above the plot, never inside it.
  const picker = (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <span className="text-xs uppercase tracking-wide subtle">{t("chart.by")}</span>
      <div className="flex flex-wrap gap-1">
        {MODES.map((m) => (
          <button
            key={m}
            onClick={() => onModeChange(m)}
            aria-pressed={mode === m}
            className={
              "rounded px-2.5 py-1 text-xs font-medium transition-colors " +
              (mode === m
                ? "bg-brand-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700")
            }
          >
            {t(`chart.${m}`)}
          </button>
        ))}
      </div>
    </div>
  );

  if (data.length === 0) {
    return (
      <div>
        {picker}
        <div className="grid h-64 place-items-center text-sm subtle">
          {t("dash.noHistory")}
        </div>
      </div>
    );
  }

  const axis = { stroke: theme.axis, fontSize: 12 };
  const colorAt = (i: number) => theme.series[i % theme.series.length];
  // In profile mode, use semantic colors (risk bands); otherwise positional palette
  const colorForSeries = (k: SeriesKey, i: number) =>
    mode === "profile" ? profileColor(k.label, theme.dark) ?? colorAt(i) : colorAt(i);

  return (
    <div>
      {picker}
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data}
            margin={{ top: 4, right: reserve ? 96 : 8, bottom: 0, left: 8 }}
          >
            <CartesianGrid stroke={theme.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" tickLine={false} {...axis} />
            <YAxis
              tickFormatter={(v) => fmtNum(Number(v), 0, locale)}
              tickLine={false}
              width={72}
              {...axis}
            />
            <Tooltip
              formatter={(value, name) => [fmtMoney(Number(value), currency, locale), name]}
              contentStyle={{
                background: theme.tooltip.background,
                border: theme.tooltip.border,
                borderRadius: theme.tooltip.borderRadius,
                color: theme.tooltip.color,
              }}
            />
            {(mode !== "total" || showProjection) && (
              <Legend wrapperStyle={{ fontSize: 12 }} />
            )}


            {mode === "total" ? (
              // A single measure needs no legend - the card title names it.
              <Line
                type="monotone"
                dataKey="total"
                name={t("chart.total")}
                stroke={colorAt(0)}
                strokeWidth={2}
                // A dot keeps a one-day history visible; a bare line would be
                // an invisible zero-length segment.
                dot={{ r: 3, strokeWidth: 0, fill: colorAt(0) }}
              />
            ) : (
              keys.map((k, i) => {
                const color = colorForSeries(k, i);
                return (
                  <Area
                    key={k.key}
                    type="monotone"
                    dataKey={k.key}
                    name={labelFor(k)}
                    stackId="v"
                    stroke={color}
                    fill={color}
                    fillOpacity={0.85}
                    strokeWidth={0}
                    dot={data.length === 1 ? { r: 3, strokeWidth: 0, fill: color } : false}
                  />
                );
              })
            )}

            {showProjection && (
              <>
                {/* All three share the total's hue: they are the same measure,
                    differing only in the rate assumed. Dashed throughout, so
                    the eye never reads them as recorded. */}
                <Line
                  type="monotone"
                  dataKey="projHigh"
                  name={t("chart.projHigh")}
                  stroke={colorAt(0)}
                  strokeWidth={1.5}
                  strokeDasharray="2 3"
                  strokeOpacity={0.65}
                  dot={false}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="projBase"
                  name={t("chart.projBase")}
                  stroke={colorAt(0)}
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  dot={false}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="projLow"
                  name={t("chart.projLow")}
                  stroke={colorAt(0)}
                  strokeWidth={1.5}
                  strokeDasharray="2 3"
                  strokeOpacity={0.65}
                  dot={false}
                  connectNulls
                />
              </>
            )}

            {/* Commitments and portfolio value are the same unit, so the
                target sits on the existing axis rather than inviting a second
                one. It earns its place in "profile" mode especially: the safe
                band is the bottom of the stack, so whether it clears this line
                is readable at a glance. */}
            {reserve && reserve.value > 0 && (
              <>
                {/* Drawn twice: a surface-coloured strand underneath gives the
                    dashes a halo, without which the line disappears into
                    whichever filled band it happens to cross. */}
                <ReferenceLine
                  y={reserve.value}
                  stroke={theme.surface}
                  strokeWidth={4}
                  ifOverflow="extendDomain"
                />
                <ReferenceLine
                  y={reserve.value}
                  stroke={theme.tooltip.color}
                  strokeWidth={1.5}
                  strokeDasharray="6 4"
                  ifOverflow="extendDomain"
                  label={{
                    value: t("chart.reserveLine", { months: reserve.months }),
                    position: "right",
                    fontSize: 10,
                    fill: theme.tooltip.color,
                  }}
                />
              </>
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {reserve && reserve.value > 0 && (
        <p className="mt-2 text-xs subtle">
          {t("chart.reserveHint", {
            months: reserve.months,
            value: fmtMoney(reserve.value, currency, locale),
          })}
        </p>
      )}

      {data.length === 1 && (
        <p className="mt-2 text-xs subtle">{t("chart.singleDay")}</p>
      )}
      {keys.find((k) => k.key === "__other__")?.members?.length ? (
        <p className="mt-2 text-xs subtle">
          {t("dash.otherDetail", {
            names: keys
              .find((k) => k.key === "__other__")!
              .members!.map(td)
              .join(" · "),
          })}
        </p>
      ) : null}
    </div>
  );
}
