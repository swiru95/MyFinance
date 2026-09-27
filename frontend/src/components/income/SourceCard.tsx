import { fmtDay, fmtMoney, fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type {
  B2bIncomeParams,
  IncomeSource,
  OtherIncomeParams,
  UopIncomeParams,
} from "@/lib/incomeTypes";

interface Props {
  source: IncomeSource;
  base: string;
  onEdit: () => void;
  onDelete: () => void;
}

const KIND_BADGE: Record<string, string> = {
  uop: "bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
  b2b: "bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  other: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
};

const KIND_LABEL_KEY: Record<string, string> = {
  uop: "inc.kindUop",
  b2b: "inc.kindB2b",
  other: "inc.kindOther",
};

const TAX_FORM_KEY: Record<string, string> = {
  skala: "inc.form.taxFormSkala",
  liniowy: "inc.form.taxFormLiniowy",
  ryczalt: "inc.form.taxFormRyczalt",
};

const ZUS_STAGE_KEY: Record<string, string> = {
  start: "inc.form.zusStart",
  preferential: "inc.form.zusPreferential",
  maly_zus_plus: "inc.form.zusMzp",
  full: "inc.form.zusFull",
};

/** The one-line params summary from the spec ("20 000 PLN gross · PPK 2% ·
 *  PIT-2" / "B2B liniowy · full ZUS · VAT 23% · 1 200/day × 20"), built from
 *  small translated fragments rather than one templated sentence per kind -
 *  each option a source can carry is either present or absent in the list. */
function summaryLine(
  source: IncomeSource,
  t: (key: string, vars?: Record<string, string | number>) => string,
  locale: string
): string {
  const currency = source.currency;
  const parts: string[] = [];

  if (source.kind === "uop") {
    const p = source.params as UopIncomeParams;
    parts.push(t("inc.sum.gross", { amount: fmtMoney(p.gross_monthly, currency, locale) }));
    parts.push(
      p.ppk_employee > 0
        ? t("inc.sum.ppk", { pct: fmtNum(p.ppk_employee * 100, 1, locale) })
        : t("inc.sum.ppkOptedOut")
    );
    if (p.pit2) parts.push(t("inc.sum.pit2"));
    if (p.young_relief) parts.push(t("inc.sum.youngRelief"));
    if (p.creative_share > 0) {
      parts.push(t("inc.sum.creative", { pct: fmtNum(p.creative_share * 100, 0, locale) }));
    }
  } else if (source.kind === "b2b") {
    const p = source.params as B2bIncomeParams;
    parts.push(t("inc.sum.b2bForm", { form: t(TAX_FORM_KEY[p.tax_form]) }));
    if (p.tax_form === "ryczalt") {
      parts.push(t("inc.sum.ryczaltRate", { rate: fmtNum(p.ryczalt_rate * 100, 1, locale) }));
    }
    parts.push(t(ZUS_STAGE_KEY[p.zus_stage]));
    if (p.sickness) parts.push(t("inc.sum.sickness"));
    if (p.vat === "standard") {
      parts.push(`${t("inc.form.vatStandard")} ${fmtNum(p.vat_rate * 100, 0, locale)}%`);
    } else if (p.vat === "exempt") {
      parts.push(t("inc.form.vatExempt"));
    } else {
      parts.push(t("inc.form.vatReverseCharge"));
    }
    if (p.billing === "monthly") {
      parts.push(t("inc.sum.billingMonthly", { amount: fmtMoney(p.invoice_monthly ?? 0, currency, locale) }));
    } else {
      const unit = p.billing === "daily" ? "inc.sum.billingDaily" : "inc.sum.billingHourly";
      parts.push(
        t(unit, {
          rate: fmtMoney(p.rate ?? 0, currency, locale),
          units: fmtNum(p.units_per_month ?? 0, 0, locale),
        })
      );
    }
  } else {
    const p = source.params as OtherIncomeParams;
    parts.push(t("inc.sum.otherNet", { amount: fmtMoney(p.net_monthly, currency, locale) }));
  }

  return parts.join(" · ");
}

export default function SourceCard({ source, base, onEdit, onDelete }: Props) {
  const { t, locale } = useI18n();
  const ys = source.year_summary;
  const totals = (ys?.totals ?? {}) as Record<string, number>;

  let grossTotal: number | undefined;
  let netTotal: number | undefined;
  let taxesTotal: number | undefined;
  let effRate: number | null | undefined;
  let currencyForTotals = "PLN"; // uop/b2b schedule totals are always PLN

  if (source.kind === "uop") {
    grossTotal = totals.gross;
    netTotal = totals.net;
    effRate = ys?.effective_rate;
  } else if (source.kind === "b2b") {
    grossTotal = totals.revenue;
    netTotal = totals.take_home;
    effRate = ys?.effective_rate;
  } else {
    // "other" has no tax maths - gross and net are the same figure, and
    // there is nothing withheld, so 0% is the true effective rate, not an
    // unknown one.
    netTotal = totals.net_in_base;
    grossTotal = netTotal;
    taxesTotal = 0;
    effRate = 0;
    currencyForTotals = base;
  }
  if (taxesTotal === undefined && grossTotal != null && netTotal != null) {
    taxesTotal = grossTotal - netTotal;
  }

  return (
    <div className="card space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-slate-900 dark:text-slate-50">
              {source.name}
            </span>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${KIND_BADGE[source.kind]}`}>
              {t(KIND_LABEL_KEY[source.kind])}
            </span>
          </div>
          <p className="mt-1 text-xs muted">{summaryLine(source, t, locale)}</p>
          <p className="mt-0.5 text-xs subtle">
            {t("inc.since", { date: fmtDay(source.starts_on, locale) })}
            {source.ends_on ? ` · ${t("inc.until", { date: fmtDay(source.ends_on, locale) })}` : ""}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            onClick={onEdit}
            className="btn-ghost text-xs"
            aria-label={`${t("common.edit")} ${source.name}`}
          >
            {t("common.edit")}
          </button>
          <button
            onClick={onDelete}
            className="btn-ghost text-xs text-red-600"
            aria-label={`${t("common.delete")} ${source.name}`}
          >
            ✕
          </button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <p className="text-xs muted">{t("inc.thisYearGross")}</p>
          <p className="font-semibold tabular-nums">
            {grossTotal != null ? fmtMoney(grossTotal, currencyForTotals, locale) : "—"}
          </p>
        </div>
        <div>
          <p className="text-xs muted">{t("inc.thisYearNet")}</p>
          <p className="font-semibold tabular-nums">
            {netTotal != null ? fmtMoney(netTotal, currencyForTotals, locale) : "—"}
          </p>
        </div>
        <div>
          <p className="text-xs muted">{t("inc.thisYearTaxes")}</p>
          <p className="font-semibold tabular-nums">
            {taxesTotal != null ? fmtMoney(taxesTotal, currencyForTotals, locale) : "—"}
          </p>
        </div>
        <div>
          <p className="text-xs muted">{t("inc.effectiveRate")}</p>
          <p className="font-semibold tabular-nums">
            {effRate != null ? `${fmtNum(effRate * 100, 1, locale)}%` : "—"}
          </p>
        </div>
      </div>
    </div>
  );
}
