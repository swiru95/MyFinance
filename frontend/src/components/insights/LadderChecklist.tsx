import { useI18n } from "@/lib/i18n";
import { fmtNum } from "@/lib/api";
import type { Rung, StepFeedback, StepFeedbackState } from "@/lib/insightsTypes";
import {
  RUNG_TITLE_KEY,
  rungWhyKey,
  STATUS_CLASS,
  STATUS_ICON,
} from "./ladderCopy";
import Markdown from "@/components/Markdown";

const FEEDBACK_STATES: StepFeedbackState[] = ["done", "dismissed", "later"];

function formatFigureValue(value: number | string | null, locale: string): string {
  if (value == null) return "—";
  if (typeof value === "number") return fmtNum(value, 2, locale);
  return value;
}

/** One AI-ranked step, keyed by the same RungKey the ladder itself uses -
 *  see NextStepsTab for how this map is built and why the two lists share a
 *  key space (services/insights.py's next-steps candidates are literally
 *  drawn from the ladder rungs). */
export interface AiStep {
  title: string;
  why_md: string;
}

interface Props {
  /** Already sorted the merged way - AI-ranked rungs first, in AI order,
   *  then the rest in ladder order. See NextStepsTab. */
  rungs: Rung[];
  aiByKey: Map<string, AiStep>;
  feedback: Record<string, StepFeedback>;
  onFeedback: (key: string, state: StepFeedbackState) => void;
}

/** The ladder and the AI ranking as ONE checklist (round 2 spec item 9):
 *  every rung shows its deterministic status, key figures and a one-line
 *  "why"; a rung the latest AI ranking also picked out gets that model's
 *  title/explanation inline underneath, plus feedback buttons - there is no
 *  longer a second, separate "ranked by the model" list repeating the same
 *  question. */
export default function LadderChecklist({ rungs, aiByKey, feedback, onFeedback }: Props) {
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
        const ai = aiByKey.get(r.key);
        const rowFeedback = feedback[r.key];
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

              {ai && (
                <div className="mt-2 rounded-lg border border-brand-100 bg-brand-50/50 p-2.5 dark:border-brand-900/40 dark:bg-brand-500/5">
                  <p className="text-xs font-semibold text-brand-700 dark:text-brand-200">
                    {ai.title}
                  </p>
                  <div className="mt-1 text-xs">
                    <Markdown text={ai.why_md} />
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {FEEDBACK_STATES.map((state) => (
                      <button
                        key={state}
                        onClick={() => onFeedback(r.key, state)}
                        aria-pressed={rowFeedback?.state === state}
                        className={`btn-ghost text-xs ${rowFeedback?.state === state ? "border-brand-500 text-brand-700 dark:text-brand-100" : ""}`}
                      >
                        {t(`ins.next.feedback.${state}`)}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
