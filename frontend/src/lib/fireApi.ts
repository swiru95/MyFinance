/** FIRE, asset-editing and flow-aware position calls, kept out of lib/api.ts
 *  so feature work does not collide there. Uses the same `request` helper
 *  api.ts exports, so auth headers and error handling stay identical. */
import { request } from "./api";
import type {
  AssetWithWrapper,
  FireResponse,
  FireSettings,
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

  createPosition: (data: PositionFlowIn) =>
    request<PositionWithFlow>("/positions", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
