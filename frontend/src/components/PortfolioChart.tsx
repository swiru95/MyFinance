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
} from "recharts";
import { fmtMoney, fmtNum } from "@/lib/api";
import { useChartTheme } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";
import type { BreakdownMode, SeriesKey, ValueRow } from "@/lib/types";

const MODES: BreakdownMode[] = ["total", "asset", "category", "profile"];

interface Props {
  rows: ValueRow[];
  keys: SeriesKey[];
  mode: BreakdownMode;
  onModeChange: (mode: BreakdownMode) => void;
  currency: string;
}

export default function PortfolioChart({
  rows,
  keys,
  mode,
  onModeChange,
  currency,
}: Props) {
  const { t, locale } = useI18n();
  const theme = useChartTheme();

  const data = rows.map((r) => ({
    ...r,
    label: new Date(`${r.date}T00:00:00`).toLocaleDateString(locale, {
      month: "short",
      day: "numeric",
    }),
  }));

  const labelFor = (k: SeriesKey) =>
    k.key === "__other__"
      ? `${t("chart.other")} (${k.members?.length ?? 0})`
      : mode === "profile"
        ? t(`profile.${k.label}`)
        : k.label;

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

  return (
    <div>
      {picker}
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
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
            {mode !== "total" && <Legend wrapperStyle={{ fontSize: 12 }} />}

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
              keys.map((k, i) => (
                <Area
                  key={k.key}
                  type="monotone"
                  dataKey={k.key}
                  name={labelFor(k)}
                  stackId="v"
                  stroke={colorAt(i)}
                  fill={colorAt(i)}
                  fillOpacity={0.85}
                  strokeWidth={0}
                  dot={data.length === 1 ? { r: 3, strokeWidth: 0, fill: colorAt(i) } : false}
                />
              ))
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {data.length === 1 && (
        <p className="mt-2 text-xs subtle">{t("chart.singleDay")}</p>
      )}
      {keys.find((k) => k.key === "__other__")?.members?.length ? (
        <p className="mt-2 text-xs subtle">
          {t("dash.otherDetail", {
            names: keys.find((k) => k.key === "__other__")!.members!.join(" · "),
          })}
        </p>
      ) : null}
    </div>
  );
}
