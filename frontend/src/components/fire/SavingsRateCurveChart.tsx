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
import { useChartTheme } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";
import type { FireSavingsRatePoint } from "@/lib/fireTypes";

interface Props {
  curve: FireSavingsRatePoint[];
  currentRate: number | null;
}

export default function SavingsRateCurveChart({ curve, currentRate }: Props) {
  const theme = useChartTheme();
  const { t, locale } = useI18n();

  const data = curve
    .filter((p) => p.years != null)
    .map((p) => ({ rate: Math.round(p.rate * 100), years: p.years as number }));

  if (data.length === 0) {
    return (
      <div className="grid h-64 place-items-center text-sm subtle">
        {t("fire.curve.empty")}
      </div>
    );
  }

  const [colour] = theme.series;
  const currentPct = currentRate != null ? Math.round(currentRate * 100) : null;
  // Rates whose FI date lies past the simulation horizon have no point; say
  // so rather than letting the line silently start at 20%.
  const firstReachable = data[0].rate;

  return (
    <div className="w-full">
      <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 20, right: 12, bottom: 0, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} vertical={false} />
          {/* Numeric, not categorical: the user's own rate (say 47%) falls
              between the 5% steps and a categorical axis drops the marker. */}
          <XAxis
            dataKey="rate"
            type="number"
            domain={[5, 80]}
            ticks={[5, 10, 20, 30, 40, 50, 60, 70, 80]}
            allowDataOverflow
            tickFormatter={(v) => `${v}%`}
            tick={{ fontSize: 11, fill: theme.axis }}
            stroke={theme.axis}
          />
          <YAxis
            tick={{ fontSize: 11, fill: theme.axis }}
            stroke={theme.axis}
            width={48}
            tickFormatter={(v) => fmtNum(Number(v), 0, locale)}
          />
          <Tooltip
            contentStyle={theme.tooltip}
            labelStyle={{ fontWeight: 600, color: theme.tooltip.color }}
            formatter={(value) => [
              t("fire.curve.yearsValue", { years: fmtNum(Number(value), 1, locale) }),
              t("fire.curve.years"),
            ]}
            labelFormatter={(rate) => `${rate}%`}
          />
          {currentPct != null && (
            <ReferenceLine
              x={currentPct}
              stroke={theme.tooltip.color}
              strokeDasharray="4 4"
              label={{
                value: t("fire.curve.you"),
                position: "top",
                fontSize: 10,
                fill: theme.tooltip.color,
              }}
            />
          )}
          <Line
            type="monotone"
            dataKey="years"
            stroke={colour}
            strokeWidth={2}
            dot={{ r: 3, strokeWidth: 0, fill: colour }}
            activeDot={{ r: 5, stroke: theme.surface, strokeWidth: 2 }}
          />
        </LineChart>
      </ResponsiveContainer>
      </div>
      {firstReachable > 5 && (
        <p className="mt-2 text-xs subtle">
          {t("fire.curve.unreachableBelow", { rate: firstReachable })}
        </p>
      )}
    </div>
  );
}
