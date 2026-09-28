import { useI18n } from "@/lib/i18n";
import { fmtMoney, fmtNum } from "@/lib/api";
import { useSettings } from "@/components/SettingsProvider";
import type { Rung, StepFeedback, StepFeedbackState } from "@/lib/insightsTypes";
import {
  RUNG_TITLE_KEY,
  rungWhyKey,
  STATUS_CLASS,
  STATUS_ICON,
} from "./ladderCopy";
import Markdown from "@/components/Markdown";

const FEEDBACK_STATES: StepFeedbackState[] = ["done", "dismissed", "later"];

type FigureKind = "money" | "percent" | "months" | "age" | "year" | "list";

/** Every figures{} key services/ladder.py can emit, mapped to how it reads
 *  to a person - a raw key like "marginal_rate_source: liniowy" means
 *  nothing without this. Kept as one flat table (rather than per-rung
 *  tables) because several rungs share keys (safe_assets, business_
 *  contributions_total, ...) and should read the same way wherever they
 *  show up. */
const FIGURE_KIND: Record<string, FigureKind> = {
  safe_assets: "money",
  target: "money",
  business_contributions_total: "money",
  envelope_outstanding: "money",
  required: "money",
  flows_ytd: "money",
  limit: "money",
  tax_saved: "money",
  marginal_rate: "percent",
  ppk_employee: "percent",
  ppk_employer: "percent",
  current_savings_rate: "percent",
  required_savings_rate: "percent",
  target_months: "months",
  target_fi_age: "age",
  birth_year: "year",
  stale_assets: "list",
  missing_months: "list",
};

/** Internal plumbing, not shown: `target_source`/`marginal_rate_source` say
 *  *where* a number came from rather than something to act on, and `note`
 *  is an unlocalised fallback message the rung's own "why" text (status
 *  "unknown"/"not_applicable") already covers. */
const DROPPED_FIGURE_KEYS = new Set(["target_source", "marginal_rate_source", "note"]);

/** "some_new_key" -> "Some new key", for a figure this table doesn't know
 *  about yet - shows something readable instead of crashing or printing
 *  the raw key untranslated. */
function humaniseKey(key: string): string {
  const words = key.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function formatFigureValue(
  value: number | string | string[] | null,
  kind: FigureKind | undefined,
  t: (key: string) => string,
  locale: string,
  baseCurrency: string,
): string | null {
  if (value == null) return null;
  if (Array.isArray(value)) {
    // Empty (e.g. data_fresh once nothing is stale) says nothing worth a
    // line - same treatment as a null figure.
    return value.length > 0 ? value.join(", ") : null;
  }
  switch (kind) {
    case "money":
      return typeof value === "number" ? fmtMoney(value, baseCurrency, locale) : String(value);
    case "percent":
      return typeof value === "number"
        ? new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 }).format(
            value,
          )
        : String(value);
    case "months":
      return typeof value === "number"
        ? `${fmtNum(value, 0, locale)} ${t("ins.fig.unit.months")}`
        : String(value);
    case "age":
      return typeof value === "number"
        ? `${fmtNum(value, 0, locale)} ${t("ins.fig.unit.age")}`
        : String(value);
    case "year":
      // A calendar year, not a duration - no unit word, no thousands
      // separator (fmtNum would otherwise write 1990 as "1,990").
      return typeof value === "number" ? String(Math.round(value)) : String(value);
    default:
      return typeof value === "number" ? fmtNum(value, 2, locale) : value;
  }
}

/** One rung's figures{} reduced to the "label: value" strings the row
 *  joins with " · ". Drops plumbing keys and empty values; unknown keys
 *  fall back to a humanised label formatted as a plain number/string. */
function figureLines(
  figures: Rung["figures"],
  t: (key: string) => string,
  locale: string,
  baseCurrency: string,
): string[] {
  const lines: string[] = [];
  for (const [key, value] of Object.entries(figures)) {
    if (DROPPED_FIGURE_KEYS.has(key)) continue;
    const kind = FIGURE_KIND[key];
    const formatted = formatFigureValue(value, kind, t, locale, baseCurrency);
    if (formatted == null) continue;
    const label = kind ? t(`ins.fig.${key}`) : humaniseKey(key);
    lines.push(`${label}: ${formatted}`);
  }
  return lines;
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
  const { baseCurrency } = useSettings();

  if (rungs.length === 0) {
    return <p className="text-sm subtle">{t("ins.next.checklistEmpty")}</p>;
  }

  return (
    <ul className="divide-y divide-slate-100 dark:divide-slate-800">
      {rungs.map((r) => {
        const figureLinesForRow = figureLines(r.figures, t, locale, baseCurrency);
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
              {figureLinesForRow.length > 0 && (
                <p className="mt-1 text-xs subtle tabular-nums">
                  {figureLinesForRow.join(" · ")}
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
