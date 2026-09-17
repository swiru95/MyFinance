import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
} from "recharts";
import { fmtMoney, fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** One ring segment. Deliberately not tied to AllocationItem so the same chart
 *  renders a per-asset breakdown and a per-class roll-up. */
export interface AllocationSlice {
  key: string | number;
  label: string;
  icon: string;
  value: number;
  percent: number;
}

const COLORS = [
  "#4f46e5",
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#14b8a6",
  "#f97316",
  "#64748b",
];

interface Props {
  slices: AllocationSlice[];
  currency: string;
}

export default function AllocationChart({ slices, currency }: Props) {
  const { t, locale } = useI18n();
  if (slices.length === 0) {
    return (
      <div className="grid h-64 place-items-center text-sm subtle">
        {t("dash.nothingToAllocate")}
      </div>
    );
  }

  const data = slices.map((i) => ({ name: i.label, value: i.value }));

  return (
    <div>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius={55}
              outerRadius={90}
              paddingAngle={2}
            >
              {data.map((_, idx) => (
                <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value) => fmtMoney(Number(value), currency, locale)}
              contentStyle={{
                background: "var(--chart-tooltip-bg)",
                border: "1px solid var(--chart-tooltip-border)",
                borderRadius: 8,
                color: "var(--chart-tooltip-text)",
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-4 space-y-2">
        {slices.map((i, idx) => (
          <li key={i.key} className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2">
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ backgroundColor: COLORS[idx % COLORS.length] }}
              />
              <span>
                {i.icon} {i.label}
              </span>
            </span>
            <span className="tabular-nums muted">
              {fmtNum(i.percent, 1, locale)}% · {fmtMoney(i.value, currency, locale)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
