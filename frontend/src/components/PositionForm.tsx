import { useMemo, useState } from "react";
import { api, fmtMoney } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { INPUT_CURRENCIES } from "@/lib/types";
import type { Asset, Prices } from "@/lib/types";

interface Props {
  asset: Asset;
  prices: Prices;
  onSubmit: () => void;
  initial?: { amount: number; currency: string; notes: string };
}

export default function PositionForm({ asset, prices, onSubmit, initial }: Props) {
  const { t, locale } = useI18n();
  const isCurrency = asset.kind === "currency";
  const [amount, setAmount] = useState<string>(
    initial ? String(initial.amount) : ""
  );
  const [currency, setCurrency] = useState<string>(
    initial?.currency ?? prices.base_currency
  );
  const [notes, setNotes] = useState<string>(initial?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const unitLabel =
    asset.kind === "gold" ? t("pos.grams") : asset.units || t("pos.units");
  const unitPrice =
    asset.kind === "gold"
      ? prices.gold_per_gram
      : asset.kind === "crypto"
        ? (prices.crypto as Record<string, number>)[asset.units]
        : null;

  const estimate = useMemo(() => {
    const a = parseFloat(amount);
    if (isNaN(a) || a <= 0) return null;
    if (asset.kind === "currency") {
      const rate = a ? prices.fx[currency] ?? 1 : 1;
      const baseRate = prices.fx[prices.base_currency] ?? 1;
      // amount in `currency` -> USD -> base
      return a * (1 / rate) * baseRate;
    }
    if (unitPrice) return a * unitPrice;
    return null;
  }, [amount, currency, asset.kind, unitPrice, prices]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const a = parseFloat(amount);
    if (isNaN(a)) {
      setError(t("pos.invalidAmount"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.createPosition({
        asset_id: asset.id,
        amount: a,
        currency: isCurrency ? currency : prices.base_currency,
        notes,
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
          {t("pos.amountLabel", { name: asset.name, unit: unitLabel })}
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
      </div>

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
            {asset.kind === "gold" ? "g" : asset.units}
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
        {busy ? t("common.saving") : t("pos.addNamed", { name: asset.name })}
      </button>
    </form>
  );
}
