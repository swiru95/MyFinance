import { useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { fireApi } from "@/lib/fireApi";
import type { CatalogueEntry } from "@/lib/types";
import type { AssetWithWrapper, Wrapper } from "@/lib/fireTypes";

// "gold" (the pre-existing, XAU-only kind) is not offered for new assets -
// picking "Gold" from the precious-metal catalogue below creates a "metal"
// asset with units="XAU" instead, so every new gold holding goes through the
// same generalised path as silver/platinum/palladium. Existing kind="gold"
// assets keep working unchanged (see backend routes/helpers.compute_value).
const KINDS = ["currency", "metal", "crypto"] as const;
type FormKind = (typeof KINDS)[number];
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
  const { t, lang } = useI18n();
  const [name, setName] = useState(existing?.name ?? "");
  const [kind, setKind] = useState<FormKind>(
    existing?.kind === "metal" ? "metal" : existing?.kind === "crypto" ? "crypto" : "currency"
  );
  const [category, setCategory] = useState(existing?.category ?? "");
  const [profile, setProfile] = useState(existing?.profile ?? "");
  const [icon, setIcon] = useState(existing?.icon ?? "");
  const [units, setUnits] = useState(existing?.units ?? "");
  const [wrapper, setWrapper] = useState<Wrapper>(existing?.wrapper ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The catalogue (4 metals + 5 coins, see backend price_service.CATALOGUE)
  // - fetched once so picking a symbol can fill name/icon/category/profile/
  // units in one go. Left null on a fetch failure rather than blocking the
  // form: the fields below just fall back to plain manual entry.
  const [catalogue, setCatalogue] = useState<{
    metals: CatalogueEntry[];
    crypto: CatalogueEntry[];
  } | null>(null);
  const [symbol, setSymbol] = useState("");

  useEffect(() => {
    if (existing) return; // editing never needs the catalogue (kind is fixed)
    fireApi
      .catalogue()
      .then(setCatalogue)
      .catch(() => setCatalogue(null));
  }, [existing]);

  const catalogueEntries: CatalogueEntry[] =
    kind === "metal" ? catalogue?.metals ?? [] : kind === "crypto" ? catalogue?.crypto ?? [] : [];

  function handleKindChange(next: FormKind) {
    setKind(next);
    setSymbol("");
  }

  function pickCatalogueEntry(sym: string) {
    setSymbol(sym);
    const entry = catalogueEntries.find((e) => e.symbol === sym);
    if (!entry) return;
    setName(entry.name[lang] ?? entry.name.en);
    setIcon(entry.icon);
    setCategory(entry.category);
    setProfile(entry.profile);
    setUnits(entry.symbol);
  }

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

  async function handleArchive() {
    if (!confirm(t("fire.asset.archiveConfirm", { name }))) return;
    setBusy(true);
    setError(null);
    try {
      await fireApi.archiveAsset(existing!.id);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!confirm(t("fire.asset.deleteConfirm", { name }))) return;
    setBusy(true);
    setError(null);
    try {
      await fireApi.deleteAsset(existing!.id);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failedSave"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {!existing && (
        <div>
          <label className="label" htmlFor="asset-kind">
            {t("fire.asset.kind")}
          </label>
          <select
            id="asset-kind"
            className="input"
            value={kind}
            onChange={(e) => handleKindChange(e.target.value as FormKind)}
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`fire.asset.kind.${k}`)}
              </option>
            ))}
          </select>
        </div>
      )}

      {!existing && (kind === "metal" || kind === "crypto") && (
        <div>
          <label className="label" htmlFor="asset-catalogue">
            {t(kind === "metal" ? "fire.asset.catalogueMetal" : "fire.asset.catalogueCrypto")}
          </label>
          <select
            id="asset-catalogue"
            className="input"
            value={symbol}
            onChange={(e) => pickCatalogueEntry(e.target.value)}
          >
            <option value="">{t("fire.asset.catalogueManual")}</option>
            {catalogueEntries.map((entry) => (
              <option key={entry.symbol} value={entry.symbol}>
                {entry.icon} {entry.name[lang] ?? entry.name.en}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs muted">{t("fire.asset.catalogueHint")}</p>
        </div>
      )}

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

      {!existing && kind !== "currency" && (
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
          <p className="mt-1 text-xs muted">{t("fire.asset.unitsHint")}</p>
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

      {existing && (
        <div className="space-y-3 border-t border-slate-200 pt-4 dark:border-slate-800">
          <button
            type="button"
            onClick={handleArchive}
            className="btn-ghost w-full"
            disabled={busy}
          >
            {t("fire.asset.archiveButton")}
          </button>
          <button
            type="button"
            onClick={handleDelete}
            className="block w-full text-center text-xs font-medium text-red-600 hover:underline"
            disabled={busy}
          >
            {t("fire.asset.deleteButton")}
          </button>
        </div>
      )}
    </form>
  );
}
