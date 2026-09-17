import { fmtDateTime, fmtMoney, fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSettings } from "@/components/SettingsProvider";
import type { Asset, Position } from "@/lib/types";

interface Props {
  pos: Position;
  asset: Asset;
  base: string;
  historyFor: number | null;
  history: Position[];
  onUpdate: () => void;
  onDelete: () => void;
}

export default function PositionCard({
  pos,
  asset,
  base,
  historyFor,
  history,
  onUpdate,
  onDelete,
}: Props) {
  const { t, locale } = useI18n();
  const { timeZone } = useSettings();
  const unit =
    asset.kind === "currency" ? pos.currency : asset.kind === "gold" ? "g" : asset.units;
  return (
    <>
      <div>
        <p className="text-2xl font-semibold tabular-nums">
          {fmtNum(pos.amount, pos.amount % 1 === 0 ? 0 : 2, locale)}
          <span className="ml-1 text-sm font-normal subtle">{unit}</span>
        </p>
        <p className="text-sm muted">= {fmtMoney(pos.value_in_base, base, locale)}</p>
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
              </tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <tr key={h.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-2 py-1 muted">
                    {new Date(h.timestamp).toLocaleDateString(locale, { timeZone })}
                  </td>
                  <td className="px-2 py-1 tabular-nums">{fmtNum(h.amount, 2, locale)}</td>
                  <td className="px-2 py-1 text-right tabular-nums">
                    {fmtMoney(h.value_in_base, base, locale)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
