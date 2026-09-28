import { useCallback, useEffect, useState } from "react";
import { api, fmtDateTime, fmtMoney, fmtSigned, fmtSignedPct, request } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useFeatures } from "@/lib/features";
import { useSettings } from "@/components/SettingsProvider";
import { fireApi } from "@/lib/fireApi";
import type { Prices } from "@/lib/types";
import type { AssetWithWrapper, PortfolioGrowth, PositionWithFlow } from "@/lib/fireTypes";
import PositionForm from "@/components/PositionForm";
import PositionCard from "@/components/PositionCard";
import AssetForm from "@/components/fire/AssetForm";
import FeatureOffCard from "@/components/FeatureOffCard";
import InfoTip from "@/components/InfoTip";
import {
  WRAPPER_STYLES,
  wrapperAccessKey,
  wrapperGlossaryKey,
  wrapperLabelKey,
  type WrapperKey,
} from "@/lib/wrappers";

export default function PositionsPage() {
  const { t, td, locale } = useI18n();
  const { portfolio } = useFeatures();
  const { timeZone } = useSettings();
  // The API always returns `wrapper` / `flow_in_base` (see AssetOut /
  // PositionOut on the backend); lib/types.ts just does not declare them, so
  // the fetched rows are cast rather than re-fetched through a second call.
  const [assets, setAssets] = useState<AssetWithWrapper[]>([]);
  const [positions, setPositions] = useState<PositionWithFlow[]>([]);
  const [prices, setPrices] = useState<Prices | null>(null);
  const [growth, setGrowth] = useState<PortfolioGrowth | null>(null);
  const [openFor, setOpenFor] = useState<number | null>(null); // asset id for add form
  const [historyFor, setHistoryFor] = useState<number | null>(null); // position id
  const [history, setHistory] = useState<PositionWithFlow[]>([]);
  const [assetFormOpen, setAssetFormOpen] = useState(false);
  const [editingAsset, setEditingAsset] = useState<AssetWithWrapper | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    // Started alongside the rest rather than after it, but kept off the
    // same Promise.all: growth is a nice-to-have summary, and a failure of
    // just this call must not blank out the assets/positions the rest of
    // the page depends on.
    const growthPromise = fireApi.growth().catch(() => null);
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
    setGrowth(await growthPromise);
  }, []);

  useEffect(() => {
    if (portfolio) refresh();
  }, [refresh, portfolio]);

  const positionByAsset = new Map(positions.map((p) => [p.asset_id, p]));
  const growthByAsset = new Map((growth?.assets ?? []).map((g) => [g.asset_id, g]));
  const base = prices?.base_currency ?? "PLN";

  // Archived assets (sold / account closed) keep their history on the charts
  // but drop out of the everyday cards/totals - they get their own collapsed
  // section further down instead, with a way back in.
  const activeAssets = assets.filter((a) => !a.archived_at);
  const archivedAssets = assets.filter((a) => a.archived_at);

  // Group the asset cards by class, preserving the order the classes first
  // appear in. An asset with no category forms a group of its own so nothing
  // is hidden under a nameless heading.
  const groups: { name: string; assets: AssetWithWrapper[] }[] = [];
  for (const asset of activeAssets) {
    const key = asset.category || asset.name;
    const existing = groups.find((g) => g.name === key);
    if (existing) existing.assets.push(asset);
    else groups.push({ name: key, assets: [asset] });
  }

  // Today's value of an asset: repriced by the growth endpoint the same way
  // the dashboard total is, falling back to the value stored at the last
  // update if that call failed. Without this the cards showed a metal or
  // coin at the price of its last update while the dashboard used today's.
  const valueNow = (assetId: number) =>
    growthByAsset.get(assetId)?.value ?? positionByAsset.get(assetId)?.value_in_base ?? 0;

  const groupTotal = (group: AssetWithWrapper[]) =>
    group.reduce((sum, a) => sum + valueNow(a.id), 0);

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

  async function restore(asset: AssetWithWrapper) {
    await fireApi.unarchiveAsset(asset.id);
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

  if (!portfolio) {
    return <FeatureOffCard descriptionKey="feat.off.positions" />;
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

      {growth && growth.total.invested > 0 && (
        <div className="card">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <p className="flex items-center text-sm muted">
                {t("growth.yourMoney")}
                <InfoTip text={t("growth.infoTip")} label={t("growth.yourMoney")} />
              </p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {fmtMoney(growth.total.invested, base, locale)}
              </p>
            </div>
            <div>
              <p className="text-sm muted">{t("growth.growth")}</p>
              <p
                className={`mt-1 text-2xl font-semibold tabular-nums ${
                  growth.total.growth >= 0
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-red-600 dark:text-red-400"
                }`}
              >
                {fmtSigned(growth.total.growth, base, locale)}
                {growth.total.growth_pct != null &&
                  ` (${fmtSignedPct(growth.total.growth_pct, locale)})`}
              </p>
            </div>
            <div>
              <p className="text-sm muted">{t("growth.valueNow")}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {fmtMoney(growth.total.value, base, locale)}
              </p>
            </div>
          </div>
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
                >
                  {t(wrapperLabelKey(wrapperKey))}
                  <span className="opacity-70">· {t(wrapperAccessKey(wrapperKey))}</span>
                  <InfoTip
                    text={t(wrapperGlossaryKey(wrapperKey))}
                    label={t(wrapperLabelKey(wrapperKey))}
                  />
                </span>
              )}

              {pos ? (
                <PositionCard
                  pos={pos}
                  asset={asset}
                  base={base}
                  growth={growthByAsset.get(asset.id) ?? null}
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

      {archivedAssets.length > 0 && (
        <details className="card">
          <summary className="cursor-pointer text-sm font-semibold uppercase tracking-wide subtle">
            {t("fire.asset.archivedSection", { n: archivedAssets.length })}
          </summary>
          <div className="mt-3 divide-y divide-slate-200 dark:divide-slate-700">
            {archivedAssets.map((asset) => (
              <div
                key={asset.id}
                className="flex items-center justify-between gap-3 py-2"
              >
                <span className="flex items-center gap-2 text-sm">
                  <span className="text-lg">{asset.icon}</span>
                  <span>
                    {td(asset.name)}
                    <span className="ml-2 text-xs subtle">
                      {t("fire.asset.archivedDate", {
                        date: fmtDateTime(asset.archived_at!, locale, timeZone),
                      })}
                    </span>
                  </span>
                </span>
                <button
                  onClick={() => restore(asset)}
                  className="text-xs font-medium text-brand-600 hover:underline"
                >
                  {t("fire.asset.restore")}
                </button>
              </div>
            ))}
          </div>
        </details>
      )}

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
              previous={positionByAsset.get(openFor)}
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
