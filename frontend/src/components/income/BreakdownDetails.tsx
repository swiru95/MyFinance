import { fmtMoney } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface Props {
  // Concrete callers pass UopMonthBreakdown | B2bMonthBreakdown, neither of
  // which has a string index signature - `unknown` sidesteps that instead
  // of loosening those interfaces just for this generic table.
  breakdown: unknown;
  currency: string;
}

// Flags/enums that are not a money figure, so they don't belong in a
// generic "show the working" table - the UI surfaces zus_capped/over_threshold
// and health_tier separately where they matter.
const SKIP = new Set(["month", "zus_capped", "over_threshold", "health_tier"]);

/** Every field of a UoP/B2B month breakdown, expandable - "show the working"
 *  per 00-architecture.md: a derived figure carries its inputs, not just the
 *  final number. `social` (JDG's own sub-breakdown) is flattened in beside
 *  the rest rather than nested, so the table stays one level deep. */
export default function BreakdownDetails({ breakdown, currency }: Props) {
  const { t, locale } = useI18n();
  if (!breakdown) return null;
  const record = breakdown as Record<string, unknown>;

  const social = record.social as Record<string, number> | undefined;
  const rows = Object.entries(record).filter(
    ([k, v]) => !SKIP.has(k) && k !== "social" && typeof v === "number"
  );
  const socialRows = social
    ? Object.entries(social).filter(([, v]) => typeof v === "number")
    : [];

  if (rows.length === 0 && socialRows.length === 0) return null;

  return (
    <details className="mt-2 text-xs">
      <summary className="cursor-pointer select-none subtle">
        {t("inc.working.show")}
      </summary>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="muted">{t(`inc.field.${k}`)}</dt>
            <dd className="text-right tabular-nums">
              {fmtMoney(v as number, currency, locale)}
            </dd>
          </div>
        ))}
        {socialRows.map(([k, v]) => (
          <div key={`social-${k}`} className="contents">
            <dt className="muted">
              {t(`inc.field.${k}`)} (ZUS)
            </dt>
            <dd className="text-right tabular-nums">
              {fmtMoney(v as number, currency, locale)}
            </dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
