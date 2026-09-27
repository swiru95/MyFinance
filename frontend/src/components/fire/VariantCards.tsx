import { fmtMoney, fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { FireInputs, FireResult } from "@/lib/fireTypes";
import InfoTip from "@/components/InfoTip";

/** Which glossary entry explains each variant, for the InfoTip next to its
 *  name - lean/fat share one entry since they are the same concept priced
 *  two ways, "regular" needs none (it is just today's spending). */
const VARIANT_GLOSSARY: Partial<Record<string, string>> = {
  lean: "gloss.leanFatFire",
  fat: "gloss.leanFatFire",
  barista: "gloss.baristaFire",
};

const VARIANTS = ["lean", "regular", "fat", "barista"] as const;

interface Props {
  result: FireResult;
  inputs: FireInputs;
  base: string;
}

export default function VariantCards({ result, inputs, base }: Props) {
  const { t, locale } = useI18n();

  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold">{t("fire.variants.title")}</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {VARIANTS.map((v) => (
          <div key={v} className="card">
            <p className="flex items-center text-sm font-semibold">
              {t(`fire.variant.${v}.name`)}
              {VARIANT_GLOSSARY[v] && (
                <InfoTip text={t(VARIANT_GLOSSARY[v]!)} label={t(`fire.variant.${v}.name`)} />
              )}
            </p>
            <p className="mt-1 text-xl font-semibold tabular-nums">
              {fmtMoney(result.targets[v], base, locale)}
            </p>
            <p className="mt-1 text-xs muted">
              {v === "lean" &&
                t("fire.variant.lean.hint", {
                  pct: fmtNum(inputs.lean_factor * 100, 0, locale),
                })}
              {v === "regular" && t("fire.variant.regular.hint")}
              {v === "fat" &&
                t("fire.variant.fat.hint", {
                  pct: fmtNum(inputs.fat_factor * 100, 0, locale),
                })}
              {v === "barista" && t("fire.variant.barista.hint")}
            </p>
          </div>
        ))}

        <div className="card">
          <p className="flex items-center text-sm font-semibold">
            {t("fire.variant.coast.name")}
            <InfoTip text={t("gloss.coastFire")} label={t("fire.variant.coast.name")} />
          </p>
          <p className="mt-1 text-xl font-semibold tabular-nums">
            {fmtMoney(result.coast.number, base, locale)}
          </p>
          <p
            className={`mt-1 text-xs ${
              result.coast.reached ? "text-emerald-600 dark:text-emerald-400" : "muted"
            }`}
          >
            {result.coast.reached ? t("fire.stat.coastReached") : t("fire.variant.coast.hint")}
          </p>
        </div>
      </div>
    </div>
  );
}
