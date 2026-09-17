import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
} from "recharts";
import { fmtMoney, fmtNum } from "@/lib/api";
import { MAX_SERIES, useChartTheme } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";

/** One ring segment. Deliberately not tied to AllocationItem so the same chart
 *  renders a per-asset breakdown and a per-class roll-up. */
export interface AllocationSlice {
  key: string | number;
  label: string;
  icon: string;
  value: number;
  percent: number;
  color?: string;
}

/** How many slices get their own hue before the tail is folded away. One slot
 *  is reserved for "Other", so this is the palette size minus one. */
const MAX_SLICES = MAX_SERIES - 1;

interface Props {
  slices: AllocationSlice[];
  currency: string;
  /** Keep the caller's order instead of ranking by value. Use it when the
   *  sequence carries meaning (risk bands run safe -> illiquid) so a hue stays
   *  attached to its band rather than to whichever band is currently biggest. */
  preserveOrder?: boolean;
}

export default function AllocationChart({ slices, currency, preserveOrder }: Props) {
  const { t, locale } = useI18n();
  const theme = useChartTheme();
  if (slices.length === 0) {
    return (
      <div className="grid h-64 place-items-center text-sm subtle">
        {t("dash.nothingToAllocate")}
      </div>
    );
  }

  // The palette has a fixed number of hues and they are never cycled: with
  // more classes than slots, two slices would share a colour and the donut
  // would stop being readable. Everything past the cap folds into one "Other"
  // slice, whose parts stay visible in the legend line.
  const ranked = preserveOrder
    ? [...slices]
    : [...slices].sort((a, b) => b.value - a.value);
  const head = ranked.slice(0, MAX_SLICES);
  const tail = ranked.slice(MAX_SLICES);
  const shown =
    tail.length > 0
      ? [
          ...head,
          {
            key: "__other__",
            label: t("dash.otherSlices", { count: String(tail.length) }),
            icon: "",
            value: tail.reduce((sum, i) => sum + i.value, 0),
            percent: tail.reduce((sum, i) => sum + i.percent, 0),
          },
        ]
      : head;

  const data = shown.map((i) => ({ name: i.label, value: i.value }));
  const colorAt = (idx: number) => theme.series[idx % theme.series.length];

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
                <Cell key={idx} fill={shown[idx].color ?? colorAt(idx)} />
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
        {shown.map((i, idx) => (
          <li key={i.key} className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2">
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ backgroundColor: shown[idx].color ?? colorAt(idx) }}
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
      {tail.length > 0 && (
        <p className="mt-3 text-xs subtle">
          {t("dash.otherDetail", { names: tail.map((i) => i.label).join(" · ") })}
        </p>
      )}
    </div>
  );
}
