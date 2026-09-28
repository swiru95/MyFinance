import { fmtDateTime, fmtMoney, fmtNum, fmtSigned, fmtSignedPct } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSettings } from "@/components/SettingsProvider";
import type { Asset } from "@/lib/types";
import type { AssetGrowth, PositionWithFlow } from "@/lib/fireTypes";

interface Props {
  pos: PositionWithFlow;
  asset: Asset;
  base: string;
  /** Null when there is only one snapshot yet, or the growth call failed. */
  growth: AssetGrowth | null;
  historyFor: number | null;
  history: PositionWithFlow[];
  onUpdate: () => void;
  onDelete: () => void;
}

export default function PositionCard({
  pos,
  asset,
  base,
  growth,
  historyFor,
  history,
  onUpdate,
  onDelete,
}: Props) {
  const { t, locale } = useI18n();
  const { timeZone } = useSettings();
  const isInterest = asset.kind === "interest";
  // "gold" is the pre-existing kind (always XAU); "metal" generalises it to
  // the other three precious metals - both are held in grams.
  const isMetal = asset.kind === "gold" || asset.kind === "metal";
  const isCrypto = asset.kind === "crypto";
  const symbol = asset.kind === "gold" ? "XAU" : asset.units;
  const unit =
    asset.kind === "currency"
      ? pos.currency
      : isMetal
        ? "g"
        : isInterest
          ? pos.currency
          : asset.units;
  // For a debt the headline is what it is worth today; the principal it grew
  // from matters just as much, so show both rather than one bare figure.
  const accrued = isInterest ? pos.value_in_base - pos.amount : 0;
  return (
    <>
      <div>
        <p className="text-2xl font-semibold tabular-nums">
          {isInterest
            ? fmtMoney(pos.value_in_base, base, locale)
            : fmtNum(pos.amount, pos.amount % 1 === 0 ? 0 : 2, locale)}
          {!isInterest && (
            <span className="ml-1 text-sm font-normal subtle">{unit}</span>
          )}
        </p>
        {isInterest ? (
          <p className="text-sm muted">
            {t("pos.principal")} {fmtMoney(pos.amount, base, locale)} +{" "}
            {t("pos.accrued").toLowerCase()} {fmtMoney(accrued, base, locale)}
            {pos.price_used > 0 && (
              <>
                {" · "}
                {t("pos.rateNow")} {fmtNum(pos.price_used, 2, locale)}%
              </>
            )}
          </p>
        ) : (
          <p className="text-sm muted">= {fmtMoney(pos.value_in_base, base, locale)}</p>
        )}
        {growth?.last && (
          <p className="text-sm">
            {t("growth.yourMoney")} {fmtMoney(growth.invested, base, locale)} ·{" "}
            <span
              className={
                growth.growth >= 0
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-red-600 dark:text-red-400"
              }
            >
              {t("growth.growth")} {fmtSigned(growth.growth, base, locale)}
              {growth.growth_pct != null &&
                ` (${fmtSignedPct(growth.growth_pct, locale)})`}
            </span>
          </p>
        )}
        {growth?.last && (
          <p className="text-xs subtle">
            {t("growth.lastUpdate")}:{" "}
            {growth.last.flow != null
              ? t("growth.lastUpdateLine", {
                  change: fmtSigned(growth.last.change, base, locale),
                  flow: fmtSigned(growth.last.flow, base, locale),
                  growth: fmtSigned(growth.last.growth, base, locale),
                })
              : t("growth.lastUpdateLineNoFlow", {
                  change: fmtSigned(growth.last.change, base, locale),
                  growth: fmtSigned(growth.last.growth, base, locale),
                })}
          </p>
        )}
        {(isMetal || isCrypto) && pos.price_used > 0 && (
          <p className="text-xs subtle">
            {symbol} · {fmtMoney(pos.price_used, base, locale)}/{isMetal ? "g" : symbol}
          </p>
        )}
        {isInterest && pos.accrues_from && (
          <p className="text-xs subtle">
            {t("pos.accruesFrom")} {pos.accrues_from}
          </p>
        )}
        <p className="mt-1 text-xs subtle">
          {t("pos.updatedAt", {
            when: fmtDateTime(pos.timestamp, locale, timeZone),
          })}
        </p>
      </div>
      <div className="flex gap-2">
        <button onClick={onUpdate} className="btn-ghost flex-1">
          {t("pos.update")}
        </button>
        <button
          onClick={onDelete}
          className="btn-ghost text-red-600"
          aria-label={t("common.delete")}
        >
          ✕
        </button>
      </div>

      {historyFor === pos.id && (
        <div className="max-h-40 overflow-auto rounded-lg border border-slate-200 dark:border-slate-800">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-slate-50 text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              <tr>
                <th className="px-2 py-1">{t("pos.when")}</th>
                <th className="px-2 py-1">{t("common.amount")}</th>
                <th className="px-2 py-1 text-right">{t("pos.value")}</th>
                <th className="px-2 py-1 text-right">{t("fire.pos.historyFlow")}</th>
                <th className="px-2 py-1 text-right">{t("growth.historyColumn")}</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h, i) => {
                // Same maths as GrowthLast, applied row by row: the previous
                // row in this same ordered list stands in for "the snapshot
                // before this one" (history is ordered oldest-first, see
                // GET /positions/{id}/history).
                const previous = i > 0 ? history[i - 1] : null;
                const rowGrowth =
                  previous != null
                    ? h.value_in_base - previous.value_in_base - (h.flow_in_base ?? 0)
                    : null;
                return (
                  <tr key={h.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-2 py-1 muted">
                      {new Date(h.timestamp).toLocaleDateString(locale, { timeZone })}
                    </td>
                    <td className="px-2 py-1 tabular-nums">{fmtNum(h.amount, 2, locale)}</td>
                    <td className="px-2 py-1 text-right tabular-nums">
                      {fmtMoney(h.value_in_base, base, locale)}
                    </td>
                    <td className="px-2 py-1 text-right tabular-nums subtle">
                      {h.flow_in_base != null ? fmtSigned(h.flow_in_base, base, locale) : "—"}
                    </td>
                    <td className="px-2 py-1 text-right tabular-nums subtle">
                      {rowGrowth != null ? fmtSigned(rowGrowth, base, locale) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
