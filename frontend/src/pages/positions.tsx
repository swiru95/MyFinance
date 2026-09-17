import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Asset, Position, Prices } from "@/lib/types";
import PositionForm from "@/components/PositionForm";
import PositionCard from "@/components/PositionCard";

export default function PositionsPage() {
  const { t } = useI18n();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [prices, setPrices] = useState<Prices | null>(null);
  const [openFor, setOpenFor] = useState<number | null>(null); // asset id for add form
  const [historyFor, setHistoryFor] = useState<number | null>(null); // position id
  const [history, setHistory] = useState<Position[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [a, p, pr] = await Promise.all([
        api.assets(),
        api.positions(),
        api.prices(),
      ]);
      setAssets(a);
      setPositions(p);
      setPrices(pr);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failedLoad"));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const positionByAsset = new Map(positions.map((p) => [p.asset_id, p]));
  const base = prices?.base_currency ?? "PLN";

  async function toggleHistory(pos: Position) {
    if (historyFor === pos.id) {
      setHistoryFor(null);
      setHistory([]);
      return;
    }
    const res = await fetch(`/api/positions/${pos.id}/history`).then((r) => r.json());
    setHistory(res);
    setHistoryFor(pos.id);
  }

  async function remove(pos: Position) {
    if (!confirm(t("pos.confirmDelete"))) return;
    await api.deletePosition(pos.id);
    refresh();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t("pos.title")}</h1>
        <p className="text-sm muted">
          {t("pos.subtitle")}
        </p>
      </div>

      {error && (
        <div className="banner-error">
          {error}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {assets.map((asset) => {
          const pos = positionByAsset.get(asset.id);
          return (
            <div key={asset.id} className="card flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-base font-medium">
                  <span className="text-lg">{asset.icon}</span> {asset.name}
                </span>
                {pos && (
                  <button
                    onClick={() => toggleHistory(pos)}
                    className="text-xs font-medium text-brand-600 hover:underline"
                  >
                    {historyFor === pos.id ? t("pos.hideHistory") : t("pos.history")}
                  </button>
                )}
              </div>

              {pos ? (
                <PositionCard
                  pos={pos}
                  asset={asset}
                  base={base}
                  historyFor={historyFor}
                  history={history}
                  onUpdate={() => setOpenFor(asset.id)}
                  onDelete={() => remove(pos)}
                />
              ) : (
                <button
                  onClick={() => setOpenFor(asset.id)}
                  className="btn-primary w-full"
                >
                  {t("pos.addNamed", { name: asset.name })}
                </button>
              )}
            </div>
          );
        })}
      </div>

      {openFor != null && prices && (
        <div className="fixed inset-0 z-20 grid place-items-center bg-black/40 p-4">
          <div className="card w-full max-w-sm">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                {assets.find((a) => a.id === openFor)?.icon}{" "}
                {assets.find((a) => a.id === openFor)?.name}
              </h2>
              <button onClick={() => setOpenFor(null)} className="subtle">
                ✕
              </button>
            </div>
            <PositionForm
              asset={assets.find((a) => a.id === openFor)!}
              prices={prices}
              onSubmit={() => {
                setOpenFor(null);
                refresh();
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
