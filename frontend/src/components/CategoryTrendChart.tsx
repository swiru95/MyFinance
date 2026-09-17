import { useMemo } from "react";
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
import { MAX_SERIES, monthLabel, useChartTheme } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";

interface Props {
  series: Record<string, number | string>[];
  categories: string[];
  currency: string;
}

/**
 * Committed spend per category, stacked by month. Categories are ranked by
 * total and take the palette slots in that fixed order; anything past the
 * eighth slot folds into "Other" rather than being given a generated hue.
 */
export default function CategoryTrendChart({ series, categories, currency }: Props) {
  const theme = useChartTheme();
  const { t, td, locale } = useI18n();

  const OTHER = t("mon.other");

  const { rows, keys } = useMemo(() => {
    const totals = new Map<string, number>();
    for (const cat of categories) {
      totals.set(
        cat,
        series.reduce((sum, row) => sum + Number(row[cat] ?? 0), 0)
      );
    }
    const ranked = [...categories].sort(
      (a, b) => (totals.get(b) ?? 0) - (totals.get(a) ?? 0)
    );
    // Keep one slot free for "Other" only when folding is actually needed.
    const keep = ranked.length > MAX_SERIES ? ranked.slice(0, MAX_SERIES - 1) : ranked;
    const folded = ranked.slice(keep.length);

    const rows = series.map((row) => {
      const out: Record<string, number | string> = {
        label: monthLabel(String(row.month), locale),
      };
      for (const cat of keep) out[cat] = Number(row[cat] ?? 0);
      if (folded.length > 0) {
        out[OTHER] = folded.reduce((sum, cat) => sum + Number(row[cat] ?? 0), 0);
      }
      return out;
    });

    return { rows, keys: folded.length > 0 ? [...keep, OTHER] : keep };
  }, [series, categories, OTHER]);

  if (keys.length === 0) {
    return (
      <div className="grid h-64 place-items-center text-sm subtle">
        {t("mon.needCategories")}
      </div>
    );
  }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
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
          {keys.map((key, idx) => (
            <Bar
              key={key}
              dataKey={key}
              name={td(key)}
              stackId="spend"
              fill={theme.series[idx % theme.series.length]}
              /* Surface-coloured stroke gives each segment a 2px visual gap. */
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
