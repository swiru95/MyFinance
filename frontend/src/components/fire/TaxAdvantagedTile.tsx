import Link from "next/link";
import { fmtMoney, fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  WRAPPER_STYLES,
  wrapperLabelKey,
  type WrapperKey,
} from "@/lib/wrappers";
import type { Allocation } from "@/lib/types";

const LOCKED: WrapperKey[] = ["ike", "ikze", "ppk", "oipe"];

// Mirrors backend/src/tax/pl/wrappers.py's exempt_asset_limit for 2027-2030
// (sources there: munipro.pl/ustawa-oki-limity-podatek-zasady,
// inwestomat.eu/jak-ma-dzialac-osobiste-konto-inwestycyjne-oki). Not read
// from the API - it is a display constant, not a computed figure.
const OKI_EXEMPT_LIMIT = 100_000;
const OKI_AVAILABLE_FROM = 2027;

interface Props {
  allocation: Allocation | null;
  currency: string;
}

/** Dashboard tile: how much of the portfolio sits in a tax-advantaged
 *  wrapper, split into the four wrappers locked before 60/65 and OKI, which
 *  is tax-advantaged but never locked (see routes/statistics.allocation's
 *  by_wrapper and tax_advantaged_total/percent). */
export default function TaxAdvantagedTile({ allocation, currency }: Props) {
  const { t, locale } = useI18n();

  if (!allocation) {
    return (
      <div className="card">
        <p className="text-sm muted">{t("fire.taxAdvantaged.title")}</p>
        <p className="mt-1 text-2xl font-semibold subtle">—</p>
      </div>
    );
  }

  const byWrapper = allocation.by_wrapper;
  const lockedRows = byWrapper.filter((w) => LOCKED.includes(w.wrapper as WrapperKey));
  const okiRow = byWrapper.find((w) => w.wrapper === "oki");
  const lockedTotal = lockedRows.reduce((sum, w) => sum + w.value, 0);
  const currentYear = new Date().getFullYear();

  if (byWrapper.length === 0) {
    return (
      <div className="card">
        <p className="text-sm muted">{t("fire.taxAdvantaged.title")}</p>
        <p className="mt-2 text-sm">
          {t("fire.taxAdvantaged.empty")}{" "}
          <Link href="/positions" className="font-medium text-brand-600 hover:underline">
            {t("nav.positions")}
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <p className="text-sm muted">{t("fire.taxAdvantaged.title")}</p>
      <p className="mt-1 text-3xl font-semibold tabular-nums">
        {fmtMoney(allocation.tax_advantaged_total, currency, locale)}
      </p>
      <p className="mt-0.5 text-xs subtle">
        {fmtNum(allocation.tax_advantaged_percent, 1, locale)}%{" "}
        {t("fire.taxAdvantaged.ofPortfolio")}
      </p>

      {lockedRows.length > 0 && (
        <div className="mt-3">
          <div className="flex flex-wrap items-center gap-1">
            {lockedRows.map((w) => (
              <span
                key={w.wrapper}
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  WRAPPER_STYLES[w.wrapper as WrapperKey].badge
                }`}
              >
                {t(wrapperLabelKey(w.wrapper as WrapperKey))}
              </span>
            ))}
            <span className="text-xs subtle">
              {t("fire.taxAdvantaged.locked")} · {fmtMoney(lockedTotal, currency, locale)}
            </span>
          </div>
        </div>
      )}

      {okiRow && (
        <div className="mt-3">
          <div className="flex flex-wrap items-center gap-1">
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${WRAPPER_STYLES.oki.badge}`}
            >
              {t(wrapperLabelKey("oki"))}
            </span>
            <span className="text-xs subtle">
              {t("fire.taxAdvantaged.accessible")} · {fmtMoney(okiRow.value, currency, locale)}
            </span>
          </div>
          <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
            <div
              className={`h-full ${WRAPPER_STYLES.oki.dot}`}
              style={{
                width: `${Math.min(100, (okiRow.value / OKI_EXEMPT_LIMIT) * 100)}%`,
              }}
            />
          </div>
          <p className="mt-1 text-xs subtle">
            {t("fire.taxAdvantaged.okiLimit", {
              value: fmtMoney(okiRow.value, currency, locale),
              limit: fmtMoney(OKI_EXEMPT_LIMIT, currency, locale),
            })}
            {currentYear < OKI_AVAILABLE_FROM && ` · ${t("fire.taxAdvantaged.okiFrom2027")}`}
          </p>
        </div>
      )}
    </div>
  );
}
