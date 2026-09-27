import { Fragment, useCallback, useEffect, useState } from "react";
import { fmtMoney, fmtNum } from "@/lib/api";
import { incomeApi } from "@/lib/incomeApi";
import { monthLabel } from "@/lib/chartTheme";
import { useI18n } from "@/lib/i18n";
import type {
  B2bIncomeParams,
  B2bMonthBreakdown,
  IncomeSource,
  SourceMonthRow,
  SourceYear,
  UnitsSource,
  UopMonthBreakdown,
} from "@/lib/incomeTypes";
import BreakdownDetails from "./BreakdownDetails";

const UNITS_SOURCE_KEY: Record<UnitsSource, string> = {
  calendar: "inc.schedule.unitsCalendar",
  fixed: "inc.schedule.unitsFixed",
  entry: "inc.schedule.unitsEntry",
};

interface Props {
  sources: IncomeSource[];
  base: string;
  selectedId: number | null;
  onSelect: (id: number) => void;
  year: number;
  onYear: (year: number) => void;
  /** Entries changed under this source - the wallet-wide summary and the
   *  source cards' year_summary need refreshing too. */
  onChanged: () => void;
}

function MonthEntryModal({
  source,
  row,
  onClose,
  onSaved,
}: {
  source: IncomeSource;
  row: SourceMonthRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t, locale } = useI18n();
  const bp = source.kind === "b2b" ? (source.params as B2bIncomeParams) : null;
  // A day/hour-billed source's revenue is derived, not typed in directly -
  // asking for units (prefilled with what's actually driving this month:
  // calendar, fixed, or a previous entry) and showing the resulting revenue
  // live keeps the source of truth the same one the schedule already shows.
  const isDayHour = bp != null && bp.billing !== "monthly";
  // Clearing an entry only "uses the calendar" when the source itself has
  // no fixed units_per_month - otherwise it reverts to that fixed number.
  const revertsToCalendar = isDayHour && bp?.units_per_month == null;
  const [amount, setAmount] = useState(String(row.amount ?? 0));
  const [units, setUnits] = useState(row.units != null ? String(row.units) : "");
  const [costs, setCosts] = useState(
    row.breakdown && "costs" in row.breakdown ? String((row.breakdown as B2bMonthBreakdown).costs) : "0"
  );
  const [overrideNet, setOverrideNet] = useState(
    row.overridden ? String(row.net_pln) : ""
  );
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const previewRevenue = isDayHour ? (bp?.rate ?? 0) * (parseFloat(units) || 0) : null;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await incomeApi.upsertEntry(source.id, row.month, {
        ...(isDayHour ? { units: parseFloat(units) || 0 } : { amount: parseFloat(amount) || 0 }),
        costs: source.kind === "b2b" ? parseFloat(costs) || 0 : 0,
        override_net: overrideNet.trim() === "" ? null : parseFloat(overrideNet),
        notes,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    if (!row.has_entry) return;
    const confirmMsg = revertsToCalendar
      ? t("inc.entry.confirmUseCalendar", { month: monthLabel(row.month, locale) })
      : t("inc.entry.confirmClear", { month: monthLabel(row.month, locale) });
    if (!confirm(confirmMsg)) return;
    setBusy(true);
    setError(null);
    try {
      await incomeApi.deleteEntry(source.id, row.month);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedDelete"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-20 grid place-items-center overflow-y-auto bg-black/40 p-4">
      <div className="card my-8 w-full max-w-sm">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">
            {t("inc.entry.title", { month: monthLabel(row.month, locale) })}
          </h2>
          <button onClick={onClose} className="subtle">✕</button>
        </div>
        <form onSubmit={save} className="space-y-4">
          {isDayHour ? (
            <div>
              <label className="label" htmlFor="entry-units">
                {bp?.billing === "daily" ? t("inc.schedule.unitsDays") : t("inc.schedule.unitsHours")}
              </label>
              <input
                id="entry-units"
                className="input"
                type="number"
                step="0.5"
                min="0"
                value={units}
                onChange={(e) => setUnits(e.target.value)}
              />
              <p className="mt-1 text-xs subtle">
                {t("inc.entry.revenuePreview", {
                  amount: fmtMoney(previewRevenue ?? 0, source.currency, locale),
                })}
              </p>
            </div>
          ) : (
            <div>
              <label className="label" htmlFor="entry-amount">{t("inc.entry.amount")}</label>
              <input
                id="entry-amount"
                className="input"
                type="number"
                step="0.01"
                min="0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>
          )}
          {source.kind === "b2b" && (
            <div>
              <label className="label" htmlFor="entry-costs">{t("inc.entry.costs")}</label>
              <input
                id="entry-costs"
                className="input"
                type="number"
                step="0.01"
                min="0"
                value={costs}
                onChange={(e) => setCosts(e.target.value)}
              />
            </div>
          )}
          <div>
            <label className="label" htmlFor="entry-override">{t("inc.entry.overrideNet")}</label>
            <input
              id="entry-override"
              className="input"
              type="number"
              step="0.01"
              value={overrideNet}
              onChange={(e) => setOverrideNet(e.target.value)}
              placeholder="—"
            />
            <p className="mt-1 text-xs subtle">{t("inc.entry.overrideNetHint")}</p>
          </div>
          <div>
            <label className="label" htmlFor="entry-notes">{t("common.notes")}</label>
            <input
              id="entry-notes"
              className="input"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-2">
            {row.has_entry && (
              <button type="button" onClick={clear} className="btn-ghost text-red-600" disabled={busy}>
                {revertsToCalendar ? t("inc.entry.useCalendar") : t("inc.entry.clear")}
              </button>
            )}
            <button type="button" onClick={onClose} className="btn-ghost flex-1">
              {t("common.cancel")}
            </button>
            <button type="submit" className="btn-primary flex-1" disabled={busy}>
              {busy ? t("common.saving") : t("common.save")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function YearSchedule({
  sources,
  base,
  selectedId,
  onSelect,
  year,
  onYear,
  onChanged,
}: Props) {
  const { t, locale } = useI18n();
  const [data, setData] = useState<SourceYear | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingRow, setEditingRow] = useState<SourceMonthRow | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const source = sources.find((s) => s.id === selectedId) ?? null;

  const load = useCallback(async () => {
    if (selectedId == null) {
      setData(null);
      return;
    }
    setLoading(true);
    try {
      const d = await incomeApi.sourceYear(selectedId, year);
      setData(d);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedLoad"));
    } finally {
      setLoading(false);
    }
  }, [selectedId, year]);

  useEffect(() => {
    load();
  }, [load]);

  function afterEntryChange() {
    setEditingRow(null);
    load();
    onChanged();
  }

  const bp = source?.kind === "b2b" ? (source.params as B2bIncomeParams) : null;
  const isDayHourSource = bp != null && bp.billing !== "monthly";
  const totalCols = !source ? 0 : (source.kind === "other" ? 2 : 6) + (isDayHourSource ? 1 : 0);

  const totals = (data?.totals ?? {}) as Record<string, number>;
  const yearsAvailable = (() => {
    const now = new Date().getFullYear();
    const startYear = source ? Number(source.starts_on.slice(0, 4)) : now;
    const from = Math.min(startYear, now - 1);
    const arr: number[] = [];
    for (let y = from; y <= now + 1; y++) arr.push(y);
    return arr;
  })();

  return (
    <div className="card space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">{t("inc.schedule.title")}</h2>
        <div className="flex gap-2">
          <select
            className="input"
            value={selectedId ?? ""}
            onChange={(e) => onSelect(Number(e.target.value))}
          >
            {sources.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <select
            className="input"
            value={year}
            onChange={(e) => onYear(Number(e.target.value))}
          >
            {yearsAvailable.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      {!source ? (
        <p className="text-sm subtle">{t("inc.schedule.selectSource")}</p>
      ) : error ? (
        <div className="banner-error">{error}</div>
      ) : loading || !data ? (
        <p className="text-sm subtle">{t("common.loading")}</p>
      ) : (
        <>
          <p className="text-xs subtle">{t("inc.schedule.clickToEdit")}</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                <tr>
                  <th className="px-3 py-2">{t("inc.schedule.month")}</th>
                  <th className="px-3 py-2 text-right">{t("inc.schedule.amount")}</th>
                  {isDayHourSource && (
                    <th className="px-3 py-2 text-right">
                      {bp?.billing === "daily" ? t("inc.schedule.unitsDays") : t("inc.schedule.unitsHours")}
                    </th>
                  )}
                  {source.kind !== "other" && (
                    <>
                      <th className="px-3 py-2 text-right">{t("inc.schedule.social")}</th>
                      <th className="px-3 py-2 text-right">{t("inc.schedule.health")}</th>
                      <th className="px-3 py-2 text-right">{t("inc.schedule.pit")}</th>
                      <th className="px-3 py-2 text-right">{t("inc.schedule.ppkOrVat")}</th>
                    </>
                  )}
                  <th className="px-3 py-2 text-right">{t("inc.schedule.net")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.months.map((row) => {
                  const breakdown = row.breakdown;
                  const uop = source.kind === "uop" ? (breakdown as UopMonthBreakdown | null) : null;
                  const b2b = source.kind === "b2b" ? (breakdown as B2bMonthBreakdown | null) : null;
                  const rowMuted = !row.active && !row.has_entry;
                  return (
                    <Fragment key={row.month}>
                      <tr
                        className={`cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/60 ${
                          rowMuted ? "opacity-50" : ""
                        }`}
                        onClick={() => setEditingRow(row)}
                      >
                        <td className="px-3 py-2 font-medium">
                          {monthLabel(row.month, locale)}
                          {row.overridden && (
                            <span className="ml-1 rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
                              {t("inc.schedule.overridden")}
                            </span>
                          )}
                          {!row.active && !row.has_entry && (
                            <span className="ml-1 text-[10px] subtle">{t("inc.schedule.inactive")}</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {fmtMoney(row.amount, source.currency, locale)}
                        </td>
                        {isDayHourSource && (
                          <td className="px-3 py-2 text-right tabular-nums">
                            {row.units != null ? fmtNum(row.units, 1, locale) : "—"}
                            {row.units_source && (
                              <span className="ml-1 text-[10px] subtle">
                                ({t(UNITS_SOURCE_KEY[row.units_source])})
                              </span>
                            )}
                          </td>
                        )}
                        {source.kind === "uop" && (
                          <>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {uop ? fmtMoney(uop.employee_social, "PLN", locale) : "—"}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {uop ? fmtMoney(uop.health, "PLN", locale) : "—"}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {uop ? fmtMoney(uop.pit_advance, "PLN", locale) : "—"}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {uop ? fmtMoney(uop.ppk_employee, "PLN", locale) : "—"}
                            </td>
                          </>
                        )}
                        {source.kind === "b2b" && (
                          <>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {b2b ? fmtMoney(b2b.social_total, "PLN", locale) : "—"}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {b2b ? fmtMoney(b2b.health, "PLN", locale) : "—"}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {b2b ? fmtMoney(b2b.pit_advance, "PLN", locale) : "—"}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {row.vat_due != null ? fmtMoney(row.vat_due, "PLN", locale) : "—"}
                            </td>
                          </>
                        )}
                        <td className="px-3 py-2 text-right font-medium tabular-nums">
                          {fmtMoney(row.net_in_base, base, locale)}
                          {breakdown && (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setExpanded(expanded === row.month ? null : row.month);
                              }}
                              className="ml-2 subtle hover:underline"
                            >
                              {expanded === row.month ? "▲" : "▾"}
                            </button>
                          )}
                        </td>
                      </tr>
                      {expanded === row.month && breakdown && (
                        <tr>
                          <td colSpan={totalCols} className="bg-slate-50 px-3 py-2 dark:bg-slate-800/40">
                            <BreakdownDetails breakdown={breakdown} currency="PLN" />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <h3 className="mb-2 text-sm font-semibold">{t("inc.schedule.summaryTitle")}</h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {source.kind !== "other" && (
                <div>
                  <p className="text-xs muted">{t("inc.schedule.totalGross")}</p>
                  <p className="font-semibold tabular-nums">
                    {fmtMoney(totals[source.kind === "uop" ? "gross" : "revenue"] ?? 0, "PLN", locale)}
                  </p>
                </div>
              )}
              <div>
                <p className="text-xs muted">{t("inc.schedule.totalNet")}</p>
                <p className="font-semibold tabular-nums">
                  {fmtMoney(
                    source.kind === "uop"
                      ? totals.net ?? 0
                      : source.kind === "b2b"
                        ? totals.take_home ?? 0
                        : (totals as unknown as { net_in_base: number }).net_in_base ?? 0,
                    source.kind === "other" ? base : "PLN",
                    locale
                  )}
                </p>
              </div>
              {source.kind !== "other" && (
                <div>
                  <p className="text-xs muted">{t("inc.schedule.totalTaxes")}</p>
                  <p className="font-semibold tabular-nums">
                    {fmtMoney(
                      (totals[source.kind === "uop" ? "gross" : "revenue"] ?? 0) -
                        (source.kind === "uop" ? totals.net ?? 0 : totals.take_home ?? 0),
                      "PLN",
                      locale
                    )}
                  </p>
                </div>
              )}
              {data.effective_rate != null && (
                <div>
                  <p className="text-xs muted">{t("inc.effectiveRate")}</p>
                  <p className="font-semibold tabular-nums">
                    {(data.effective_rate * 100).toFixed(1)}%
                  </p>
                </div>
              )}
              {source.kind === "uop" && data.settlement != null && (
                <div>
                  <p className="text-xs muted">{t("inc.schedule.settlement")}</p>
                  <p className="font-semibold tabular-nums">
                    {data.settlement >= 0
                      ? t("inc.schedule.settlementPay", { amount: fmtMoney(data.settlement, "PLN", locale) })
                      : t("inc.schedule.settlementRefund", { amount: fmtMoney(-data.settlement, "PLN", locale) })}
                  </p>
                </div>
              )}
              {source.kind === "uop" && (
                <div>
                  <p className="text-xs muted">{t("inc.schedule.employerCost")}</p>
                  <p className="font-semibold tabular-nums">
                    {fmtMoney((totals as unknown as { employer_cost: number }).employer_cost ?? 0, "PLN", locale)}
                  </p>
                </div>
              )}
              {source.kind === "b2b" && (
                <div>
                  <p className="text-xs muted">{t("inc.schedule.setAside")}</p>
                  <p className="font-semibold tabular-nums">
                    {fmtMoney((totals as unknown as { set_aside: number }).set_aside ?? 0, "PLN", locale)}
                  </p>
                </div>
              )}
              {source.kind === "b2b" &&
                data.ryczalt_health_reconciliation != null &&
                data.ryczalt_health_reconciliation !== 0 && (
                  <div>
                    <p className="text-xs muted">{t("inc.schedule.healthSettlementTitle")}</p>
                    <p className="font-semibold tabular-nums">
                      {data.ryczalt_health_reconciliation > 0
                        ? t("inc.schedule.healthSettlementPay", {
                            amount: fmtMoney(data.ryczalt_health_reconciliation, "PLN", locale),
                            tier: String(data.ryczalt_health_tier_actual ?? ""),
                          })
                        : t("inc.schedule.healthSettlementRefund", {
                            amount: fmtMoney(-data.ryczalt_health_reconciliation, "PLN", locale),
                            tier: String(data.ryczalt_health_tier_actual ?? ""),
                          })}
                    </p>
                  </div>
                )}
            </div>
            {source.kind === "other" && (
              <p className="mt-2 text-xs subtle">{t("inc.schedule.otherNote")}</p>
            )}
          </div>
        </>
      )}

      {editingRow && source && (
        <MonthEntryModal
          source={source}
          row={editingRow}
          onClose={() => setEditingRow(null)}
          onSaved={afterEntryChange}
        />
      )}
    </div>
  );
}
