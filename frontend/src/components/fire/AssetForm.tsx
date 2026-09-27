import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import { fireApi } from "@/lib/fireApi";
import type { AssetWithWrapper, Wrapper } from "@/lib/fireTypes";

const KINDS = ["currency", "gold", "crypto"] as const;
const PROFILES = ["", "safe", "moderate", "risky", "illiquid"] as const;
const WRAPPERS: Wrapper[] = ["", "ike", "ikze", "ppk", "oipe", "oki"];

interface Props {
  /** Present = editing (name/category/profile/icon/wrapper only - kind and
   *  units are fixed at creation because they decide how every past
   *  snapshot was priced). Absent = adding a new asset. */
  existing?: AssetWithWrapper | null;
  onDone: () => void;
  onCancel: () => void;
}

export default function AssetForm({ existing, onDone, onCancel }: Props) {
  const { t } = useI18n();
  const [name, setName] = useState(existing?.name ?? "");
  const [kind, setKind] = useState<(typeof KINDS)[number]>(
    (existing?.kind as (typeof KINDS)[number]) ?? "currency"
  );
  const [category, setCategory] = useState(existing?.category ?? "");
  const [profile, setProfile] = useState(existing?.profile ?? "");
  const [icon, setIcon] = useState(existing?.icon ?? "");
  const [units, setUnits] = useState(existing?.units ?? "");
  const [wrapper, setWrapper] = useState<Wrapper>(existing?.wrapper ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      if (existing) {
        await fireApi.updateAsset(existing.id, {
          name: name.trim(),
          category: category.trim(),
          profile,
          icon: icon.trim(),
          wrapper,
        });
      } else {
        await fireApi.createAsset({
          name: name.trim(),
          kind,
          category: category.trim(),
          profile,
          icon: icon.trim(),
          units: units.trim(),
          wrapper,
        });
      }
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="label" htmlFor="asset-name">
          {t("fire.asset.name")}
        </label>
        <input
          id="asset-name"
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </div>

      {!existing && (
        <div>
          <label className="label" htmlFor="asset-kind">
            {t("fire.asset.kind")}
          </label>
          <select
            id="asset-kind"
            className="input"
            value={kind}
            onChange={(e) => setKind(e.target.value as (typeof KINDS)[number])}
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`fire.asset.kind.${k}`)}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label" htmlFor="asset-category">
            {t("fire.asset.category")}
          </label>
          <input
            id="asset-category"
            className="input"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder={t("fire.asset.categoryPlaceholder")}
          />
        </div>
        <div>
          <label className="label" htmlFor="asset-icon">
            {t("fire.asset.icon")}
          </label>
          <input
            id="asset-icon"
            className="input"
            value={icon}
            onChange={(e) => setIcon(e.target.value)}
            placeholder="💰"
            maxLength={8}
          />
        </div>
      </div>

      {!existing && (
        <div>
          <label className="label" htmlFor="asset-units">
            {t("fire.asset.units")}
          </label>
          <input
            id="asset-units"
            className="input"
            value={units}
            onChange={(e) => setUnits(e.target.value)}
            placeholder={t("fire.asset.unitsPlaceholder")}
          />
        </div>
      )}

      <div>
        <label className="label" htmlFor="asset-profile">
          {t("fire.asset.profile")}
        </label>
        <select
          id="asset-profile"
          className="input"
          value={profile}
          onChange={(e) => setProfile(e.target.value)}
        >
          {PROFILES.map((p) => (
            <option key={p} value={p}>
              {p === "" ? t("fire.asset.profileAuto") : t(`profile.${p}`)}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="label" htmlFor="asset-wrapper">
          {t("fire.asset.wrapper")}
        </label>
        <select
          id="asset-wrapper"
          className="input"
          value={wrapper}
          onChange={(e) => setWrapper(e.target.value as Wrapper)}
        >
          {WRAPPERS.map((w) => (
            <option key={w} value={w}>
              {w === "" ? t("fire.wrapper.none") : t(`fire.wrapper.${w}`)}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs muted">
          {wrapper === "oki" ? t("fire.wrapper.oki.hint") : t("fire.asset.wrapperHint")}
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button type="button" onClick={onCancel} className="btn-ghost flex-1">
          {t("common.cancel")}
        </button>
        <button type="submit" className="btn-primary flex-1" disabled={busy}>
          {busy
            ? t("common.saving")
            : existing
              ? t("common.save")
              : t("fire.asset.addTitle")}
        </button>
      </div>
    </form>
  );
}
