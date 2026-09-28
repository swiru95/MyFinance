/** FIRE, asset-editing and flow-aware position calls, kept out of lib/api.ts
 *  so feature work does not collide there. Uses the same `request` helper
 *  api.ts exports, so auth headers and error handling stay identical. */
import { request } from "./api";
import type { Catalogue } from "./types";
import type {
  AssetWithWrapper,
  FireResponse,
  FireSettings,
  PortfolioGrowth,
  PositionWithFlow,
  Wrapper,
} from "./fireTypes";

export interface AssetIn {
  name: string;
  kind: string;
  category: string;
  profile: string;
  icon: string;
  units: string;
  wrapper: Wrapper;
}

export interface AssetUpdateIn {
  name: string;
  category: string;
  profile: string;
  icon: string;
  wrapper: Wrapper;
}

export interface PositionFlowIn {
  asset_id: number;
  amount: number;
  currency: string;
  notes: string;
  accrues_from?: string | null;
  /** Money moved into (+) or out of (-) this position; undefined means not
   *  entered (server treats that as unknown, not zero). */
  flow?: number;
}

export const fireApi = {
  get: () => request<FireResponse>("/fire"),
  /** The metals/crypto AssetForm can offer when adding a "metal" or
   *  "crypto" asset (name/icon/category/profile/units per symbol). */
  catalogue: () => request<Catalogue>("/prices/catalogue"),
  getSettings: () => request<FireSettings>("/fire/settings"),
  saveSettings: (data: FireSettings) =>
    request<FireSettings>("/fire/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  createAsset: (data: AssetIn) =>
    request<AssetWithWrapper>("/assets", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateAsset: (id: number, data: Partial<AssetUpdateIn>) =>
    request<AssetWithWrapper>(`/assets/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteAsset: (id: number) =>
    request<void>(`/assets/${id}`, {
      method: "DELETE",
    }),
  /** Soft delete: the asset disappears from current holdings but keeps its
   *  history (see backend routes/assets.py::archive_asset). */
  archiveAsset: (id: number) =>
    request<AssetWithWrapper>(`/assets/${id}/archive`, {
      method: "POST",
    }),
  unarchiveAsset: (id: number) =>
    request<AssetWithWrapper>(`/assets/${id}/unarchive`, {
      method: "POST",
    }),

  createPosition: (data: PositionFlowIn) =>
    request<PositionWithFlow>("/positions", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  /** Your money vs. growth, per asset and in total (see
   *  backend/src/services/growth.py). */
  growth: () => request<PortfolioGrowth>("/positions/growth"),
};
