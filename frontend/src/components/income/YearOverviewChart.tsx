import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from "recharts";
import { fmtMoney, fmtNum } from "@/lib/api";
import { monthLabel, useChartTheme } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";
import type { IncomeSummaryMonth } from "@/lib/incomeTypes";

interface Props {
  months: IncomeSummaryMonth[];
  currency: string;
}

/** Net take-home stacked with what's withheld (social, health, PIT, PPK) -
 *  VAT is deliberately excluded: it is pass-through money collected on the
 *  state's behalf, shown in the tax envelope instead, not a cost of income. */
export default function YearOverviewChart({ months, currency }: Props) {
  const theme = useChartTheme();
  const { t, locale } = useI18n();

  const hasData = months.some((m) => m.net > 0 || m.gross > 0);
  if (!hasData) {
    return (
      <div className="grid h-72 place-items-center text-sm subtle">
        {t("inc.chart.empty")}
      </div>
    );
  }

  const data = months.map((m) => ({
    label: monthLabel(m.month, locale),
    net: m.net,
    social: m.social,
    health: m.health,
    pit: m.pit,
    ppk: m.ppk,
  }));

  const [netColor, socialColor, healthColor, pitColor, ppkColor] = theme.series;
  const series = [
    { key: "net", name: t("inc.chart.net"), color: netColor },
    { key: "social", name: t("inc.chart.social"), color: socialColor },
    { key: "health", name: t("inc.chart.health"), color: healthColor },
    { key: "pit", name: t("inc.chart.pit"), color: pitColor },
    { key: "ppk", name: t("inc.chart.ppk"), color: ppkColor },
  ];

  return (
    <div className="h-80 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
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
            formatter={(value, name) => [fmtMoney(Number(value), currency, locale), String(name)]}
          />
          <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} iconType="circle" iconSize={8} />
          {series.map((s) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.name}
              stackId="income"
              fill={s.color}
              stroke={theme.surface}
              strokeWidth={1}
              maxBarSize={36}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
