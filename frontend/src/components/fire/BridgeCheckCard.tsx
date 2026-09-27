import { fmtMoney } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { FireResult } from "@/lib/fireTypes";

interface Props {
  bridge: FireResult["bridge_check"];
  base: string;
}

export default function BridgeCheckCard({ bridge, base }: Props) {
  const { t, locale } = useI18n();

  if (!bridge) {
    return (
      <div className="card">
        <h2 className="text-lg font-semibold">{t("fire.bridge.title")}</h2>
        <p className="mt-2 text-sm muted">{t("fire.bridge.unavailable")}</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h2 className="text-lg font-semibold">{t("fire.bridge.title")}</h2>
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <div>
          <p className="text-sm muted">{t("fire.bridge.needed")}</p>
          <p className="mt-1 text-xl font-semibold tabular-nums">
            {fmtMoney(bridge.needed, base, locale)}
          </p>
        </div>
        <div>
          <p className="text-sm muted">{t("fire.bridge.projected")}</p>
          <p className="mt-1 text-xl font-semibold tabular-nums">
            {fmtMoney(bridge.projected_accessible, base, locale)}
          </p>
        </div>
      </div>
      <p
        className={`mt-3 text-sm font-medium ${
          bridge.ok ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"
        }`}
      >
        {bridge.ok ? t("fire.bridge.ok") : t("fire.bridge.notOk")}
      </p>
      {!bridge.ok && <p className="mt-1 text-xs muted">{t("fire.bridge.wrapperHint")}</p>}
    </div>
  );
}
