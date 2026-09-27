import { useI18n } from "@/lib/i18n";
import { fmtNum } from "@/lib/api";
import type { Rung } from "@/lib/insightsTypes";
import {
  RUNG_TITLE_KEY,
  rungWhyKey,
  STATUS_CLASS,
  STATUS_ICON,
} from "./ladderCopy";

function formatFigureValue(value: number | string | null, locale: string): string {
  if (value == null) return "—";
  if (typeof value === "number") return fmtNum(value, 2, locale);
  return value;
}

interface Props {
  /** Already sorted by `order` - see NextStepsTab. */
  rungs: Rung[];
}

/** The ladder as a vertical checklist: status icon, title, a one-line "why"
 *  and whatever figures the backend attached, rendered generically since the
 *  set of figure keys differs per rung and is not spelled out by the spec. */
export default function LadderChecklist({ rungs }: Props) {
  const { t, locale } = useI18n();

  if (rungs.length === 0) {
    return <p className="text-sm subtle">{t("ins.next.checklistEmpty")}</p>;
  }

  return (
    <ul className="divide-y divide-slate-100 dark:divide-slate-800">
      {rungs.map((r) => {
        const figureEntries = Object.entries(r.figures).filter(
          ([, v]) => v != null,
        );
        return (
          <li key={r.key} className="flex items-start gap-3 py-3">
            <span
              className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border border-current text-sm font-semibold ${STATUS_CLASS[r.status]}`}
              aria-label={t(`ins.ladder.status.${r.status}`)}
              title={t(`ins.ladder.status.${r.status}`)}
            >
              {STATUS_ICON[r.status]}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{t(RUNG_TITLE_KEY[r.key])}</p>
              <p className="text-xs muted">{t(rungWhyKey(r.key, r.status))}</p>
              {figureEntries.length > 0 && (
                <p className="mt-1 text-xs subtle tabular-nums">
                  {figureEntries
                    .map(([k, v]) => `${k}: ${formatFigureValue(v, locale)}`)
                    .join(" · ")}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
