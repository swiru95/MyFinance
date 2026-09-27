import { useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { insightsApi } from "@/lib/insightsApi";
import type { InsightStatus, SuggestedStyle } from "@/lib/insightsTypes";
import type { ReportStyle } from "@/lib/types";
import NextStepsTab from "@/components/insights/NextStepsTab";
import DigestTab from "@/components/insights/DigestTab";
import ProfileTab from "@/components/insights/ProfileTab";
import WalletAssessmentTab from "@/components/insights/WalletAssessmentTab";

type TabKey = "next_steps" | "digest" | "profile" | "assessment";

const TABS: { key: TabKey; labelKey: string }[] = [
  { key: "next_steps", labelKey: "ins.tab.nextSteps" },
  { key: "digest", labelKey: "ins.tab.digest" },
  { key: "profile", labelKey: "ins.tab.profile" },
  { key: "assessment", labelKey: "ins.tab.assessment" },
];

/** /report, renamed Insights / Analizy in the nav (see lib/strings/insights
 *  "nav.report" override). The former whole page is now the "Wallet
 *  assessment" tab (WalletAssessmentTab), unchanged in behaviour; the other
 *  three tabs are new. `style` is lifted here rather than kept inside
 *  WalletAssessmentTab so the Profile tab's "use suggested style" button can
 *  set it without the two tabs importing each other. */
export default function ReportPage() {
  const { t } = useI18n();
  const [tab, setTab] = useState<TabKey>("next_steps");
  const [status, setStatus] = useState<InsightStatus | null>(null);
  const [style, setStyle] = useState<ReportStyle>("balanced");

  useEffect(() => {
    insightsApi
      .status()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  function useSuggestedStyle(suggested: SuggestedStyle) {
    setStyle(suggested);
    setTab("assessment");
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t("ins.title")}</h1>
        <p className="text-sm muted">{t("ins.subtitle")}</p>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2 dark:border-slate-800">
        {TABS.map((tabDef) => (
          <button
            key={tabDef.key}
            type="button"
            onClick={() => setTab(tabDef.key)}
            aria-pressed={tab === tabDef.key}
            className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              tab === tabDef.key
                ? "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            {t(tabDef.labelKey)}
          </button>
        ))}
      </div>

      {tab === "next_steps" && <NextStepsTab status={status} />}
      {tab === "digest" && <DigestTab status={status} />}
      {tab === "profile" && (
        <ProfileTab status={status} onUseStyle={useSuggestedStyle} />
      )}
      {tab === "assessment" && (
        <WalletAssessmentTab style={style} onStyleChange={setStyle} />
      )}
    </div>
  );
}
