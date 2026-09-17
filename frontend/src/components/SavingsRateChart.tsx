import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import { fmtNum } from "@/lib/api";
import { monthLabel, useChartTheme } from "@/lib/chartTheme";
import type { TimelinePoint } from "@/lib/types";
import { useI18n } from "@/lib/i18n";

interface Props {
  points: TimelinePoint[];
}

/** Percentages get their own chart - never a second axis on the money chart. */
export default function SavingsRateChart({ points }: Props) {
  const theme = useChartTheme();
  const { t, locale } = useI18n();

  const data = points
    .filter((p) => p.income != null && p.income > 0)
    .map((p) => ({
      label: monthLabel(p.month, locale),
      rate: Math.round((100 * (p.surplus ?? 0)) / (p.income || 1) * 10) / 10,
    }));

  if (data.length === 0) {
    return (
      <div className="grid h-72 place-items-center text-sm subtle">
        {t("mon.needIncome")}
      </div>
    );
  }

  const [primary] = theme.series;

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 11, fill: theme.axis }}
            stroke={theme.axis}
            minTickGap={16}
          />
          <YAxis
            tick={{ fontSize: 11, fill: theme.axis }}
            stroke={theme.axis}
            tickFormatter={(v) => `${v}%`}
            width={48}
          />
          <Tooltip
            contentStyle={theme.tooltip}
            labelStyle={{ fontWeight: 600, color: theme.tooltip.color }}
            formatter={(value) => [`${fmtNum(Number(value), 1, locale)}%`, t("mon.savedTooltip")]}
          />
          {/* Below zero you spent more than you earned. */}
          <ReferenceLine y={0} stroke={theme.axis} strokeWidth={1} />
          <Line
            type="monotone"
            dataKey="rate"
            stroke={primary}
            strokeWidth={2}
            dot={{ r: 3, strokeWidth: 0, fill: primary }}
            activeDot={{ r: 5, stroke: theme.surface, strokeWidth: 2 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
