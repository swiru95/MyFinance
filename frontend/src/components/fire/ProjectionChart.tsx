import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
  Legend,
} from "recharts";
import { fmtMoney, fmtNum } from "@/lib/api";
import { useChartTheme } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";
import type { FireProjectionPoint } from "@/lib/fireTypes";

interface Props {
  points: FireProjectionPoint[];
  fiAge: number | null;
  base: string;
}

/** Portfolio value vs the FI target, by age. The target line is not flat: it
 *  declines as the ZUS pension bridge shortens and flattens once the pension
 *  starts (see services/fire._regular_target), which is the "step-down"
 *  the spec asks for. */
export default function ProjectionChart({ points, fiAge, base }: Props) {
  const theme = useChartTheme();
  const { t, locale } = useI18n();

  if (points.length < 2) {
    return (
      <div className="grid h-72 place-items-center text-sm subtle">
        {t("fire.projection.empty")}
      </div>
    );
  }

  const [valueColour, targetColour] = theme.series;

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 20, right: 12, bottom: 0, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} vertical={false} />
          <XAxis
            dataKey="age"
            type="number"
            domain={["dataMin", "dataMax"]}
            tick={{ fontSize: 11, fill: theme.axis }}
            stroke={theme.axis}
            tickFormatter={(v) => fmtNum(Number(v), 0, locale)}
          />
          <YAxis
            tick={{ fontSize: 11, fill: theme.axis }}
            stroke={theme.axis}
            width={56}
            tickFormatter={(v) => fmtNum(Number(v), 0, locale)}
          />
          <Tooltip
            contentStyle={theme.tooltip}
            labelStyle={{ fontWeight: 600, color: theme.tooltip.color }}
            formatter={(value, name) => [fmtMoney(Number(value), base, locale), String(name)]}
            labelFormatter={(age) => t("fire.projection.ageLabel", { age: fmtNum(Number(age), 0, locale) })}
          />
          <Legend
            verticalAlign="top"
            align="right"
            height={24}
            iconType="plainline"
            wrapperStyle={{ fontSize: 12, color: theme.axis }}
          />
          {fiAge != null && (
            <ReferenceLine
              x={fiAge}
              stroke={theme.tooltip.color}
              strokeDasharray="4 4"
              label={{
                value: t("fire.projection.fiAge"),
                position: "top",
                fontSize: 10,
                fill: theme.tooltip.color,
              }}
            />
          )}
          <Line
            type="monotone"
            dataKey="value"
            name={t("fire.projection.portfolio")}
            stroke={valueColour}
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="target"
            name={t("fire.projection.target")}
            stroke={targetColour}
            strokeWidth={2}
            strokeDasharray="5 4"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
