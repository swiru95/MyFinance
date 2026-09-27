import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useFeatures } from "@/lib/features";
import { fireApi } from "@/lib/fireApi";
import { fireNeedsSetup } from "@/lib/fireTypes";
import type { FireResponse, FireSettings } from "@/lib/fireTypes";
import SettingsCard from "@/components/fire/SettingsCard";
import HeadlineStats from "@/components/fire/HeadlineStats";
import TwoQuestions from "@/components/fire/TwoQuestions";
import VariantCards from "@/components/fire/VariantCards";
import ProjectionChart from "@/components/fire/ProjectionChart";
import SavingsRateCurveChart from "@/components/fire/SavingsRateCurveChart";
import LeversCard from "@/components/fire/LeversCard";
import BridgeCheckCard from "@/components/fire/BridgeCheckCard";
import InputsPanel from "@/components/fire/InputsPanel";
import FeatureOffCard from "@/components/FeatureOffCard";
import InfoTip from "@/components/InfoTip";

export default function FirePage() {
  const { t } = useI18n();
  const { fire: fireEnabled } = useFeatures();
  const [data, setData] = useState<FireResponse | null>(null);
  const [base, setBase] = useState("PLN");
  const [error, setError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [fire, summary] = await Promise.all([fireApi.get(), api.summary()]);
      setData(fire);
      setBase(summary.base_currency);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedLoad"));
    }
  }, [t]);

  useEffect(() => {
    if (fireEnabled) refresh();
  }, [refresh, fireEnabled]);

  async function saveSettings(next: FireSettings) {
    await fireApi.saveSettings(next);
    await refresh();
  }

  if (!fireEnabled) {
    return <FeatureOffCard descriptionKey="feat.off.fire" />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center text-2xl font-semibold">
          {t("fire.title")}
          <InfoTip text={t("gloss.fireAcronym")} label="FIRE" />
        </h1>
        <p className="text-sm muted">{t("fire.subtitle")}</p>
      </div>

      {error && <div className="banner-error">{error}</div>}

      {!data ? (
        <p className="muted">{t("common.loading")}</p>
      ) : fireNeedsSetup(data) ? (
        <>
          <SettingsCard
            settings={data.settings}
            open
            needsSetup
            onToggle={() => {}}
            onSave={saveSettings}
          />
          <div className="card">
            <p className="muted">{t("fire.needBirthYear")}</p>
          </div>
        </>
      ) : (
        <>
          <SettingsCard
            settings={data.settings}
            open={settingsOpen}
            needsSetup={false}
            onToggle={() => setSettingsOpen((o) => !o)}
            onSave={saveSettings}
          />

          <HeadlineStats result={data.result} base={base} />

          <TwoQuestions
            result={data.result}
            inputs={data.inputs}
            requiredIncome={data.required_income}
            base={base}
          />

          <VariantCards result={data.result} inputs={data.inputs} base={base} />

          <div className="card">
            <h2 className="mb-3 text-lg font-semibold">{t("fire.projection.title")}</h2>
            <ProjectionChart
              points={data.result.projection}
              fiAge={data.result.simulate.fi_age}
              base={base}
            />
          </div>

          <div className="card">
            <h2 className="text-lg font-semibold">{t("fire.curve.title")}</h2>
            <p className="mb-3 text-sm muted">{t("fire.curve.caption")}</p>
            <SavingsRateCurveChart
              curve={data.result.savings_rate_curve}
              currentRate={data.result.current_savings_rate}
            />
          </div>

          <LeversCard levers={data.result.levers} />

          <BridgeCheckCard bridge={data.result.bridge_check} base={base} />

          <InputsPanel inputs={data.inputs} base={base} />

          <p className="text-xs subtle">{t("fire.disclaimer")}</p>
        </>
      )}
    </div>
  );
}
