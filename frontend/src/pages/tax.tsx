import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import { useFeatures } from "@/lib/features";
import Comparator from "@/components/tax/Comparator";
import ReverseCalculator from "@/components/tax/ReverseCalculator";
import ParamsTable from "@/components/tax/ParamsTable";
import FeatureOffCard from "@/components/FeatureOffCard";

export default function TaxPage() {
  const { t } = useI18n();
  const { tax } = useFeatures();
  const [year] = useState(new Date().getFullYear());

  if (!tax) {
    return <FeatureOffCard descriptionKey="feat.off.tax" />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t("tax.title")}</h1>
        <p className="text-sm muted">{t("tax.subtitle")}</p>
      </div>

      <Comparator />
      <ReverseCalculator />

      <div className="card">
        <h2 className="text-lg font-semibold">{t("tax.params.title", { year })}</h2>
        <p className="mb-3 text-sm muted">{t("tax.params.subtitle")}</p>
        <ParamsTable year={year} />
      </div>
    </div>
  );
}
