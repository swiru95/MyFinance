import { useCallback, useEffect, useState } from "react";
import { api, fmtMoney, request } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Prices } from "@/lib/types";
import type { AssetWithWrapper, PositionWithFlow } from "@/lib/fireTypes";
import PositionForm from "@/components/PositionForm";
import PositionCard from "@/components/PositionCard";
import AssetForm from "@/components/fire/AssetForm";
import {
  WRAPPER_STYLES,
  wrapperAccessKey,
  wrapperLabelKey,
  type WrapperKey,
} from "@/lib/wrappers";

export default function PositionsPage() {
  const { t, td, locale } = useI18n();
  // The API always returns `wrapper` / `flow_in_base` (see AssetOut /
  // PositionOut on the backend); lib/types.ts just does not declare them, so
  // the fetched rows are cast rather than re-fetched through a second call.
  const [assets, setAssets] = useState<AssetWithWrapper[]>([]);
  const [positions, setPositions] = useState<PositionWithFlow[]>([]);
  const [prices, setPrices] = useState<Prices | null>(null);
  const [openFor, setOpenFor] = useState<number | null>(null); // asset id for add form
  const [historyFor, setHistoryFor] = useState<number | null>(null); // position id
  const [history, setHistory] = useState<PositionWithFlow[]>([]);
  const [assetFormOpen, setAssetFormOpen] = useState(false);
  const [editingAsset, setEditingAsset] = useState<AssetWithWrapper | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [a, p, pr] = await Promise.all([
        api.assets(),
        api.positions(),
        api.prices(),
      ]);
      setAssets(a as AssetWithWrapper[]);
      setPositions(p as PositionWithFlow[]);
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

  // Group the asset cards by class, preserving the order the classes first
  // appear in. An asset with no category forms a group of its own so nothing
  // is hidden under a nameless heading.
  const groups: { name: string; assets: AssetWithWrapper[] }[] = [];
  for (const asset of assets) {
    const key = asset.category || asset.name;
    const existing = groups.find((g) => g.name === key);
    if (existing) existing.assets.push(asset);
    else groups.push({ name: key, assets: [asset] });
  }

  const groupTotal = (group: AssetWithWrapper[]) =>
    group.reduce(
      (sum, a) => sum + (positionByAsset.get(a.id)?.value_in_base ?? 0),
      0,
    );

  async function toggleHistory(pos: PositionWithFlow) {
    if (historyFor === pos.id) {
      setHistoryFor(null);
      setHistory([]);
      return;
    }
    const res = await request<PositionWithFlow[]>(`/positions/${pos.id}/history`);
    setHistory(res);
    setHistoryFor(pos.id);
  }

  async function remove(pos: PositionWithFlow) {
    if (!confirm(t("pos.confirmDelete"))) return;
    await api.deletePosition(pos.id);
    refresh();
  }

  function openNewAsset() {
    setEditingAsset(null);
    setAssetFormOpen(true);
  }

  function openEditAsset(asset: AssetWithWrapper) {
    setEditingAsset(asset);
    setAssetFormOpen(true);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{t("pos.title")}</h1>
          <p className="text-sm muted">
            {t("pos.subtitle")}
          </p>
        </div>
        <button onClick={openNewAsset} className="btn-primary">
          {t("fire.asset.addNew")}
        </button>
      </div>

      {error && (
        <div className="banner-error">
          {error}
        </div>
      )}

      {groups.map((group) => (
        <section key={group.name} className="space-y-3">
          <div className="flex items-baseline justify-between border-b border-slate-200 pb-1 dark:border-slate-700">
            <h2 className="text-sm font-semibold uppercase tracking-wide subtle">
              {td(group.name)}
            </h2>
            <span className="text-sm font-medium tabular-nums">
              {fmtMoney(groupTotal(group.assets), base, locale)}
            </span>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {group.assets.map((asset) => {
          const pos = positionByAsset.get(asset.id);
          // Unwrapped assets keep the plain card; a wrapper adds a coloured
          // frame plus a badge naming it and its access rule, one colour per
          // wrapper (see lib/wrappers.ts) so the same wrapper reads the same
          // way on /positions, the dashboard tile and the FIRE inputs.
          const wrapperKey = (asset.wrapper || null) as WrapperKey | null;
          const style = wrapperKey ? WRAPPER_STYLES[wrapperKey] : null;
          return (
            <div
              key={asset.id}
              className={`card flex flex-col gap-3 ${style ? style.ring : ""}`}
            >
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-base font-medium">
                  <span className="text-lg">{asset.icon}</span> {td(asset.name)}
                </span>
                <span className="flex items-center gap-2">
                  {pos && (
                    <button
                      onClick={() => toggleHistory(pos)}
                      className="text-xs font-medium text-brand-600 hover:underline"
                    >
                      {historyFor === pos.id ? t("pos.hideHistory") : t("pos.history")}
                    </button>
                  )}
                  <button
                    onClick={() => openEditAsset(asset)}
                    className="text-xs font-medium text-brand-600 hover:underline"
                  >
                    {t("fire.asset.editButton")}
                  </button>
                </span>
              </div>

              {wrapperKey && style && (
                <span
                  className={`inline-flex w-fit items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${style.badge}`}
                  title={t(wrapperAccessKey(wrapperKey))}
                >
                  {t(wrapperLabelKey(wrapperKey))}
                  <span className="opacity-70">· {t(wrapperAccessKey(wrapperKey))}</span>
                </span>
              )}

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
                  {t("pos.addNamed", { name: td(asset.name) })}
                </button>
              )}
            </div>
          );
        })}
          </div>
        </section>
      ))}

      {openFor != null && prices && (
        <div className="fixed inset-0 z-20 grid place-items-center bg-black/40 p-4">
          <div className="card w-full max-w-sm">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                {assets.find((a) => a.id === openFor)?.icon}{" "}
                {td(assets.find((a) => a.id === openFor)?.name ?? "")}
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

      {assetFormOpen && (
        <div className="fixed inset-0 z-20 grid place-items-center bg-black/40 p-4">
          <div className="card w-full max-w-sm">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                {editingAsset ? t("fire.asset.editTitle") : t("fire.asset.addTitle")}
              </h2>
              <button onClick={() => setAssetFormOpen(false)} className="subtle">
                ✕
              </button>
            </div>
            <AssetForm
              existing={editingAsset}
              onDone={() => {
                setAssetFormOpen(false);
                refresh();
              }}
              onCancel={() => setAssetFormOpen(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
