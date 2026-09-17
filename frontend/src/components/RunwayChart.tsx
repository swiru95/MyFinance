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
import { monthLabel, profileColor, useChartTheme } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";

export interface RunwayPoint {
  month: string;
  /** Safe assets divided by that month's committed spend. */
  months: number;
}

interface Props {
  points: RunwayPoint[];
  /** Same shape, drawn dashed. Shares its first month with the last recorded
   *  point so the two lines meet rather than floating apart. */
  projected?: RunwayPoint[];
  target: number;
}

/**
 * How many months of commitments the safe band would cover, month by month.
 *
 * This is the one place portfolio and expenses genuinely belong on a shared
 * axis: dividing one by the other leaves months, not money, so the scale is
 * its own rather than a second money scale competing with the first. Plotting
 * spend against portfolio value directly would need two axes for one unit,
 * where any crossing is an artefact of the ranges chosen rather than a fact
 * about the portfolio.
 */
export default function RunwayChart({ points, projected = [], target }: Props) {
  const theme = useChartTheme();
  const { t, locale } = useI18n();

  if (points.length === 0) {
    return (
      <div className="grid h-48 place-items-center text-sm subtle">
        {t("dash.runwayEmpty")}
      </div>
    );
  }

  const colour = profileColor("safe", theme.dark) ?? theme.series[0];

  // One row per month carrying both series, so recharts draws a single
  // continuous x-axis rather than two charts stacked on each other.
  const byMonth = new Map<string, { months?: number; projected?: number }>();
  for (const p of points) {
    byMonth.set(p.month, { ...byMonth.get(p.month), months: p.months });
  }
  for (const p of projected) {
    byMonth.set(p.month, { ...byMonth.get(p.month), projected: p.months });
  }
  const data = Array.from(byMonth.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, v]) => ({ ...v, month, label: monthLabel(month, locale) }));

  // Keep the target line in frame even when cover never gets near it.
  const peak = Math.max(
    target,
    ...points.map((p) => p.months),
    ...projected.map((p) => p.months),
  );

  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 72, bottom: 0, left: 8 }}>
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
            width={48}
            domain={[0, Math.ceil(peak * 1.15)]}
            tickFormatter={(v) => fmtNum(Number(v), 0, locale)}
          />
          <Tooltip
            contentStyle={theme.tooltip}
            labelStyle={{ fontWeight: 600, color: theme.tooltip.color }}
            formatter={(value, name) => [
              t("dash.runwayMonths", { months: fmtNum(Number(value), 1, locale) }),
              String(name),
            ]}
          />
          {/* Same halo trick as the portfolio chart: the target has to stay
              readable wherever the line happens to cross it. */}
          <ReferenceLine y={target} stroke={theme.surface} strokeWidth={4} />
          <ReferenceLine
            y={target}
            stroke={theme.tooltip.color}
            strokeWidth={1.5}
            strokeDasharray="6 4"
            label={{
              value: t("dash.runwayTarget", { months: target }),
              position: "right",
              fontSize: 10,
              fill: theme.tooltip.color,
            }}
          />
          <Line
            type="monotone"
            dataKey="months"
            name={t("dash.runwayRecorded")}
            stroke={colour}
            strokeWidth={2}
            dot={{ r: 3, strokeWidth: 0, fill: colour }}
            activeDot={{ r: 5, stroke: theme.surface, strokeWidth: 2 }}
            connectNulls
          />
          {/* Dashed and hollow-dotted: this half is arithmetic about the
              future, not something that happened, and should never be mistaken
              for a record. */}
          {projected.length > 1 && (
            <Line
              type="monotone"
              dataKey="projected"
              name={t("dash.runwayProjected")}
              stroke={colour}
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={{ r: 3, strokeWidth: 1.5, fill: theme.surface, stroke: colour }}
              activeDot={{ r: 5, stroke: theme.surface, strokeWidth: 2 }}
              connectNulls
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
