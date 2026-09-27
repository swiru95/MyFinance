import { fmtMoney, fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { FireInputs } from "@/lib/fireTypes";

interface Props {
  inputs: FireInputs;
  base: string;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="muted">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  );
}

export default function InputsPanel({ inputs, base }: Props) {
  const { t, locale } = useI18n();

  return (
    <div className="card">
      <h2 className="text-lg font-semibold">{t("fire.inputs.title")}</h2>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-3">
        <Row label={t("fire.inputs.fiAssets")} value={fmtMoney(inputs.fi_assets, base, locale)} />
        <Row
          label={t("fire.inputs.accessible")}
          value={fmtMoney(inputs.accessible_assets, base, locale)}
        />
        <Row label={t("fire.inputs.wrapped")} value={fmtMoney(inputs.wrapped_assets, base, locale)} />
        <Row
          label={t("fire.inputs.excludedIlliquid")}
          value={fmtMoney(inputs.excluded_illiquid, base, locale)}
        />
        <Row label={t("fire.inputs.reserve")} value={fmtMoney(inputs.reserve, base, locale)} />
        <Row
          label={t("fire.inputs.blendedNominal")}
          value={`${fmtNum(inputs.blended_nominal * 100, 1, locale)}%`}
        />
        <Row
          label={t("fire.inputs.realReturn")}
          value={`${fmtNum(inputs.real_return * 100, 1, locale)}%`}
        />
        <Row
          label={t("fire.inputs.inflation")}
          value={`${fmtNum(inputs.inflation * 100, 1, locale)}%`}
        />
        <Row
          label={t("fire.inputs.monthlySpend")}
          value={fmtMoney(inputs.monthly_spend, base, locale)}
        />
        <Row
          label={t("fire.inputs.monthlyContribution")}
          value={fmtMoney(inputs.monthly_contribution, base, locale)}
        />
      </dl>
      <details className="mt-3 text-xs subtle">
        <summary className="cursor-pointer">{t("fire.inputs.sources")}</summary>
        <ul className="mt-1 space-y-1">
          <li>
            {t("fire.inputs.spendSource", { source: t(`fire.source.${inputs.spend_source}`) })}
          </li>
          <li>
            {t("fire.inputs.contributionSource", {
              source: t(`fire.source.${inputs.contribution_source}`),
            })}
          </li>
          <li>{t("fire.inputs.paramsYear", { year: inputs.params_year })}</li>
        </ul>
      </details>
    </div>
  );
}
