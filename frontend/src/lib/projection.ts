import type { Allocation } from "./types";

/**
 * Expected nominal annual returns, in PLN, used to project the portfolio.
 *
 * These are long-run averages for the asset class, not forecasts, and they are
 * the only guessed input in the projection - the contribution side comes from
 * what the user actually recorded. Deliberately conservative: a projection is
 * most useful when it under-promises.
 *
 * Crypto is 0%. It is not an oversight and it is not a claim that crypto goes
 * nowhere: it is a refusal to put a number on something whose dispersion is
 * wider than the projection horizon. With a fifth of a portfolio in it, any
 * rate picked here would dominate the chart while being indistinguishable from
 * a wish.
 *
 * Receivables are 0% because a holding valued by kind="interest" already
 * accrues statutory interest on the server; growing it again here would count
 * the same interest twice.
 */
export const CATEGORY_RETURNS: Record<string, number> = {
  Cash: 0.02,
  Savings: 0.04,
  Bonds: 0.05,
  TFI: 0.06,
  Retirement: 0.06,
  Stocks: 0.08,
  Gold: 0.03,
  Crypto: 0,
  Watches: 0,
  "Fixed Assets": 0,
  Receivables: 0,
};

/** Fallback for a class the table does not name - a category the user typed
 *  themselves. Every asset carries a risk band, so that answers it without
 *  inventing a rate for a name nobody has seen before. */
export const PROFILE_RETURNS: Record<string, number> = {
  safe: 0.03,
  moderate: 0.05,
  risky: 0.07,
  illiquid: 0,
};

export interface RateLine {
  category: string;
  value: number;
  share: number;
  rate: number;
  /** share x rate: what this class contributes to the blended figure. */
  contribution: number;
}

/** Expected return of the portfolio as actually held, plus the per-class
 *  working so the number can be argued with rather than taken on trust. */
export function blendedRate(alloc: Allocation | null): {
  rate: number;
  lines: RateLine[];
} {
  if (!alloc || alloc.total <= 0) return { rate: 0, lines: [] };

  // A class's band is whatever its assets carry; by_category does not hold it,
  // so it is read back off the items that rolled up into it.
  const profileOf = new Map<string, string>();
  for (const item of alloc.items) {
    if (!profileOf.has(item.category)) {
      const band = alloc.by_profile.find((b) =>
        b.categories.includes(item.category),
      );
      if (band) profileOf.set(item.category, band.profile);
    }
  }

  const lines = alloc.by_category.map((g) => {
    const fallback = PROFILE_RETURNS[profileOf.get(g.category) ?? ""] ?? 0;
    const rate = CATEGORY_RETURNS[g.category] ?? fallback;
    const share = g.value / alloc.total;
    return {
      category: g.category,
      value: g.value,
      share,
      rate,
      contribution: share * rate,
    };
  });

  return {
    rate: lines.reduce((sum, l) => sum + l.contribution, 0),
    lines,
  };
}

/** Compound `value` monthly at an annual `rate`, adding `contribution` at the
 *  end of each month. Returns one figure per month, `months` long. */
export function compound(
  value: number,
  rate: number,
  contribution: number,
  months: number,
): number[] {
  const monthly = rate / 12;
  const out: number[] = [];
  let v = value;
  for (let i = 0; i < months; i++) {
    v = v * (1 + monthly) + contribution;
    out.push(v);
  }
  return out;
}

/** Scenario multipliers applied to the blended rate. Half and one-and-a-half
 *  rather than anything cleverer: the point is to show that the middle line is
 *  one draw from a range, not to imply a modelled confidence interval. */
export const SCENARIOS = { low: 0.5, base: 1, high: 1.5 } as const;
