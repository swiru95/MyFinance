import { fmtMoney } from "@/lib/api";
import { useChartTheme, profileColor } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";
import type { AllocationProfile } from "@/lib/types";
import AllocationChart from "@/components/AllocationChart";

interface Props {
  bands: AllocationProfile[];
  currency: string;
}

/** Presentation order, not sort order: the ring reads safe -> illiquid, and a
 *  band keeps its hue even when its share changes. */
const ORDER = ["safe", "moderate", "risky", "illiquid"];

const ICON: Record<string, string> = {
  safe: "🛡️",
  moderate: "⚖️",
  risky: "📈",
  illiquid: "🔒",
};

export default function PortfolioProfile({ bands, currency }: Props) {
  const { t, locale } = useI18n();
  const theme = useChartTheme();

  const sorted = [...bands].sort(
    (a, b) => ORDER.indexOf(a.profile) - ORDER.indexOf(b.profile),
  );

  return (
    <div>
      <AllocationChart
        preserveOrder
        currency={currency}
        slices={sorted.map((b) => ({
          key: b.profile,
          label: t(`profile.${b.profile}`),
          icon: ICON[b.profile] ?? "",
          value: b.value,
          percent: b.percent,
          color: profileColor(b.profile, theme.dark),
        }))}
      />
      <p className="mt-3 text-xs subtle">{t("profile.hint")}</p>
    </div>
  );
}
