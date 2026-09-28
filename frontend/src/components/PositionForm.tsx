import { useMemo, useState } from "react";
import { fmtMoney, fmtSigned } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { fireApi } from "@/lib/fireApi";
import { INPUT_CURRENCIES } from "@/lib/types";
import type { Asset, Prices } from "@/lib/types";
import type { PositionWithFlow } from "@/lib/fireTypes";

interface Props {
  asset: Asset;
  prices: Prices;
  onSubmit: () => void;
  initial?: { amount: number; currency: string; notes: string };
  /** The asset's latest existing snapshot. Undefined for a brand new asset's
   *  first entry - there the opening balance is never a flow, so the field
   *  is hidden rather than relabelled (see the flow field below). */
  previous?: PositionWithFlow;
}

// 1 troy oz = this many grams - the standard used for precious metals.
const OZ_TO_GRAM = 31.1034768;

export default function PositionForm({ asset, prices, onSubmit, initial, previous }: Props) {
  const { t, td, locale } = useI18n();
  const isCurrency = asset.kind === "currency";
  const isInterest = asset.kind === "interest";
  // "gold" is the pre-existing kind (always XAU); "metal" generalises it to
  // silver/platinum/palladium too - both are entered in grams and both take
  // the g/oz switch below.
  const isMetal = asset.kind === "gold" || asset.kind === "metal";
  const isCrypto = asset.kind === "crypto";
  const isQuantity = isMetal || isCrypto;
  // An update starts from the last recorded amount: a monthly update is
  // usually a correction of it, and the growth preview then reads 0 until
  // something actually changes.
  const [amount, setAmount] = useState<string>(
    initial
      ? String(initial.amount)
      : previous
        ? // Money amounts are shown to the grosz; a quantity (grams, coins)
          // keeps its full precision - 0.00012345 BTC must not round to 0.
          String(isQuantity ? previous.amount : Math.round(previous.amount * 100) / 100)
        : ""
  );
  // Metals only: whether the amount typed above is grams or troy ounces.
  // Ounces are converted to grams before the position is saved, since
  // Asset.amount for a metal is always grams (see backend compute_value).
  const [unitMode, setUnitMode] = useState<"g" | "oz">("g");
  const [currency, setCurrency] = useState<string>(
    initial?.currency ?? previous?.currency ?? prices.base_currency
  );
  const [flow, setFlow] = useState<string>("");
  const [notes, setNotes] = useState<string>(initial?.notes ?? "");
  const [accruesFrom, setAccruesFrom] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Currency and interest positions record the flow in the same currency the
  // amount itself is in; metal/crypto only take a flow when entered (in base
  // currency), otherwise it is derived server-side from the quantity change.
  const flowUnit = isCurrency ? currency : prices.base_currency;

  const unitLabel = isMetal
    ? t("pos.grams")
    : isInterest
      ? prices.base_currency
      : asset.units || t("pos.units");
  const unitPrice = asset.kind === "gold"
    ? prices.gold_per_gram
    : asset.kind === "metal"
      ? prices.metals[asset.units] ?? null
      : isCrypto
        ? prices.crypto[asset.units] ?? null
        : null;

  // The amount actually priced/saved: a metal typed in troy oz is converted
  // to grams first (unitPrice is always per gram); everything else is used
  // as typed.
  const amountInGrams = useMemo(() => {
    const a = parseFloat(amount);
    if (isNaN(a)) return NaN;
    return isMetal && unitMode === "oz" ? a * OZ_TO_GRAM : a;
  }, [amount, unitMode, isMetal]);

  const estimate = useMemo(() => {
    const a = parseFloat(amount);
    if (isNaN(a) || a <= 0) return null;
    if (asset.kind === "currency") {
      const rate = a ? prices.fx[currency] ?? 1 : 1;
      const baseRate = prices.fx[prices.base_currency] ?? 1;
      // amount in `currency` -> USD -> base
      return a * (1 / rate) * baseRate;
    }
    if (unitPrice) return (isMetal ? amountInGrams : a) * unitPrice;
    // Interest is deliberately not estimated here: the accrual needs the NBP
    // rate schedule, which lives on the server. Showing a client-side guess
    // would only disagree with the figure that gets stored.
    return null;
  }, [amount, amountInGrams, currency, asset.kind, isMetal, unitPrice, prices]);

  // "Paid in", converted to base currency the same way the server will read
  // it - so the live preview below matches what GrowthLast will show once
  // this snapshot is saved. Currency: flow is typed in `currency`, same
  // conversion as `estimate`. Metal/crypto: flow is already base currency
  // as typed, or derived from the quantity change when left blank (see
  // routes/positions.py::_flow_in_base, mirrored here client-side).
  const previewPaid = useMemo(() => {
    if (!previous || estimate == null) return null;
    if (isCurrency) {
      if (flow.trim() === "") return 0;
      const f = parseFloat(flow);
      if (isNaN(f)) return null;
      const rate = prices.fx[currency] ?? 1;
      const baseRate = prices.fx[prices.base_currency] ?? 1;
      return f * (1 / rate) * baseRate;
    }
    if (isQuantity) {
      if (flow.trim() !== "") {
        const f = parseFloat(flow);
        return isNaN(f) ? null : f;
      }
      if (isNaN(amountInGrams) || unitPrice == null) return null;
      return (amountInGrams - previous.amount) * unitPrice;
    }
    return null; // interest: no client estimate, so no preview at all (below)
  }, [previous, estimate, isCurrency, isQuantity, flow, currency, prices, amountInGrams, unitPrice]);

  const preview = useMemo(() => {
    if (!previous || estimate == null || previewPaid == null) return null;
    const change = estimate - previous.value_in_base;
    return { change, paid: previewPaid, growth: change - previewPaid };
  }, [previous, estimate, previewPaid]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const a = isMetal ? amountInGrams : parseFloat(amount);
    if (isNaN(a)) {
      setError(t("pos.invalidAmount"));
      return;
    }
    if (isInterest && !accruesFrom) {
      setError(t("pos.needStartDate"));
      return;
    }
    let flowValue: number | undefined;
    if (flow.trim() !== "") {
      flowValue = parseFloat(flow);
      if (isNaN(flowValue)) {
        setError(t("fire.pos.invalidFlow"));
        return;
      }
    }
    setBusy(true);
    setError(null);
    try {
      await fireApi.createPosition({
        asset_id: asset.id,
        amount: a,
        currency: isCurrency ? currency : prices.base_currency,
        notes,
        accrues_from: isInterest ? accruesFrom : null,
        flow: flowValue,
      });
      onSubmit();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="label">
          {t("pos.amountLabel", { name: td(asset.name), unit: unitLabel })}
        </label>
        <input
          className="input"
          type="number"
          step="any"
          min="0"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="0.00"
          required
        />
        {isMetal && (
          <>
            <div className="mt-1 flex gap-3 text-xs">
              <label className="flex items-center gap-1">
                <input
                  type="radio"
                  name="unit-mode"
                  checked={unitMode === "g"}
                  onChange={() => setUnitMode("g")}
                />
                {t("pos.grams")}
              </label>
              <label className="flex items-center gap-1">
                <input
                  type="radio"
                  name="unit-mode"
                  checked={unitMode === "oz"}
                  onChange={() => setUnitMode("oz")}
                />
                {t("pos.troyOz")}
              </label>
            </div>
            {unitMode === "oz" && <p className="mt-1 text-xs subtle">{t("pos.ozHint")}</p>}
          </>
        )}
      </div>

      {isInterest && (
        <div>
          <label className="label">{t("pos.accruesFrom")}</label>
          <input
            className="input"
            type="date"
            value={accruesFrom}
            onChange={(e) => setAccruesFrom(e.target.value)}
            required
          />
          <p className="mt-1 text-xs muted">{t("pos.interestNote")}</p>
        </div>
      )}

      {isCurrency && (
        <div>
          <label className="label">{t("common.currency")}</label>
          <select
            className="input"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            {INPUT_CURRENCIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      )}

      {unitPrice != null && (
        <p className="text-xs muted">
          {t("pos.livePrice")}:{" "}
          <span className="font-medium">
            {fmtMoney(unitPrice, prices.base_currency, locale)}/
            {isMetal ? "g" : asset.units}
          </span>
        </p>
      )}

      {estimate != null && (
        <p className="banner-info">
          {t("pos.estimate", {
            value: fmtMoney(estimate, prices.base_currency, locale),
          })}
        </p>
      )}

      {previous && (
        <div>
          <label className="label">
            {t("growth.flowLabelWithPrevious", { unit: flowUnit })}
          </label>
          <input
            className="input"
            type="number"
            step="any"
            value={flow}
            onChange={(e) => setFlow(e.target.value)}
            placeholder="0.00"
          />
          <p className="mt-1 text-xs muted">
            {isQuantity ? t("fire.pos.flowHintQuantity") : t("growth.flowHintWithPrevious")}
          </p>
        </div>
      )}

      {preview != null && (
        <p className="banner-info">
          {t("growth.previewLine", {
            change: fmtSigned(preview.change, prices.base_currency, locale),
            paid: fmtSigned(preview.paid, prices.base_currency, locale),
            growth: fmtSigned(preview.growth, prices.base_currency, locale),
          })}
        </p>
      )}

      <div>
        <label className="label">{t("common.notes")}</label>
        <input
          className="input"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          
        />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button type="submit" className="btn-primary w-full" disabled={busy}>
        {busy
          ? t("common.saving")
          : previous
            ? t("growth.saveUpdate")
            : t("pos.addNamed", { name: td(asset.name) })}
      </button>
    </form>
  );
}
