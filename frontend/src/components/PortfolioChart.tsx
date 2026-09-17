import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { fmtMoney, fmtNum } from "@/lib/api";
import type { ValuePoint } from "@/lib/types";
import { useI18n } from "@/lib/i18n";

interface Props {
  points: ValuePoint[];
  currency: string;
}

export default function PortfolioChart({ points, currency }: Props) {
  const { t, locale } = useI18n();
  const data = points.map((p) => ({
    ...p,
    label: new Date(p.timestamp).toLocaleDateString(locale, {
      month: "short",
      day: "numeric",
    }),
  }));

  if (data.length === 0) {
    return (
      <div className="grid h-64 place-items-center text-sm subtle">
        {t("dash.noHistory")}
      </div>
    );
  }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
          <XAxis dataKey="label" tick={{ fontSize: 12 }} stroke="var(--chart-axis)" />
          <YAxis
            tick={{ fontSize: 12 }}
            stroke="var(--chart-axis)"
            tickFormatter={(v) => fmtNum(v, 0, locale)}
            width={70}
          />
          <Tooltip
            formatter={(value) => [fmtMoney(Number(value), currency, locale), t("dash.total")]}
            labelStyle={{ fontWeight: 600, color: "var(--chart-tooltip-text)" }}
            contentStyle={{
              background: "var(--chart-tooltip-bg)",
              border: "1px solid var(--chart-tooltip-border)",
              borderRadius: 8,
              color: "var(--chart-tooltip-text)",
            }}
          />
          <Line
            type="monotone"
            dataKey="total"
            stroke="#4f46e5"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
