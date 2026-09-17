import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import { fmtMoney, fmtNum } from "@/lib/api";
import { monthLabel, useChartTheme } from "@/lib/chartTheme";
import type { TimelinePoint } from "@/lib/types";
import { useI18n } from "@/lib/i18n";

interface Props {
  points: TimelinePoint[];
  currency: string;
  currentMonth: string;
}

/**
 * Committed, income and actual share one money axis - they are the same unit,
 * so they belong on one scale. The savings rate is a percentage and lives in
 * its own chart rather than on a second axis.
 */
export default function BudgetTimelineChart({
  points,
  currency,
  currentMonth,
}: Props) {
  const theme = useChartTheme();
  const { t, locale } = useI18n();

  if (points.length === 0) {
    return (
      <div className="grid h-64 place-items-center text-sm subtle">
        {t("mon.noMonths")}
      </div>
    );
  }

  const data = points.map((p) => ({ ...p, label: monthLabel(p.month, locale) }));
  // Slot order is fixed; income takes aqua (positive) and actual orange.
  const [committed, actual, income] = theme.series;

  return (
    <div className="h-80 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 11, fill: theme.axis }}
            stroke={theme.axis}
            interval="preserveStartEnd"
            minTickGap={16}
          />
          <YAxis
            tick={{ fontSize: 11, fill: theme.axis }}
            stroke={theme.axis}
            tickFormatter={(v) => fmtNum(v, 0, locale)}
            width={64}
          />
          <Tooltip
            cursor={{ fill: theme.dark ? "#1e293b80" : "#f1f5f980" }}
            contentStyle={theme.tooltip}
            labelStyle={{ fontWeight: 600, color: theme.tooltip.color }}
            formatter={(value, name) => [
              fmtMoney(Number(value), currency, locale),
              String(name),
            ]}
          />
          <Legend
            wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
            iconType="circle"
            iconSize={8}
          />
          <ReferenceLine
            x={monthLabel(currentMonth, locale)}
            stroke={theme.axis}
            strokeDasharray="2 4"
            label={{
              value: t("mon.now"),
              position: "insideTopRight",
              fontSize: 10,
              fill: theme.axis,
            }}
          />
          {/* 1px surface-coloured stroke keeps adjacent bars from touching. */}
          <Bar
            dataKey="committed"
            name={t("mon.legendCommitted")}
            fill={committed}
            stroke={theme.surface}
            strokeWidth={1}
            radius={[4, 4, 0, 0]}
            maxBarSize={28}
          />
          <Line
            type="monotone"
            dataKey="income"
            name={t("mon.legendIncome")}
            stroke={income}
            strokeWidth={2}
            dot={{ r: 3, strokeWidth: 0, fill: income }}
            activeDot={{ r: 5, stroke: theme.surface, strokeWidth: 2 }}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="actual"
            name={t("mon.legendActual")}
            stroke={actual}
            strokeWidth={2}
            dot={{ r: 3, strokeWidth: 0, fill: actual }}
            activeDot={{ r: 5, stroke: theme.surface, strokeWidth: 2 }}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
