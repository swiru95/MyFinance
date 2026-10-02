import { ApiError, request, requestBlob, saveBlob } from "./api";

/** Mirrors backend/src/schemas/wallet.py (the file's size cap and the import
 *  preview shapes). The file itself is sent as the raw request body. */
export const MAX_WALLET_FILE_BYTES = 1_000_000;

export type PlanSection = "setting" | "asset" | "income_source" | "expense";
export type PlanAction = "create" | "fill" | "skip" | "keep";

export interface PlanItem {
  section: PlanSection;
  name: string;
  action: PlanAction;
  reason: string;
  existing: string | null;
  incoming: string | null;
}

export interface PlanCounts {
  create: number;
  fill: number;
  skip: number;
  keep: number;
}

export interface PlanWarning {
  code: string;
  args: string[];
}

export interface WalletPlan {
  version: number;
  applied: boolean;
  items: PlanItem[];
  counts: Record<PlanSection, PlanCounts>;
  warnings: PlanWarning[];
  writes: number;
}

/** The server refused the file; `problems` says where, when it can. */
export class WalletFileError extends Error {
  readonly status: number;
  readonly problems: { where: string; message: string }[];
  constructor(status: number, message: string, problems: { where: string; message: string }[] = []) {
    super(message);
    this.name = "WalletFileError";
    this.status = status;
    this.problems = problems;
  }
}

function asFileError(err: unknown): unknown {
  if (!(err instanceof ApiError) || ![400, 413, 422].includes(err.status)) return err;
  const body = err.message.replace(/^API \d+: /, "");
  try {
    const detail = JSON.parse(body).detail;
    if (typeof detail === "string") return new WalletFileError(err.status, detail);
    if (detail && typeof detail === "object") {
      return new WalletFileError(err.status, String(detail.message ?? body), detail.errors ?? []);
    }
  } catch {
    // not JSON: fall through to the raw text
  }
  return new WalletFileError(err.status, body);
}

async function send(path: string, text: string): Promise<WalletPlan> {
  try {
    return await request<WalletPlan>(path, { method: "POST", body: text });
  } catch (err) {
    throw asFileError(err);
  }
}

export const walletApi = {
  /** Downloads the wallet file (a plain, unencrypted JSON document). */
  async exportFile(): Promise<void> {
    const blob = await requestBlob("/wallet/export");
    const day = new Date().toISOString().slice(0, 10);
    saveBlob(blob, `myfinance-wallet-${day}.json`);
  },
  /** Dry run: what the file would create, and what it would leave alone. */
  preview: (text: string) => send("/wallet/import/preview", text),
  /** Writes it, in one transaction. */
  apply: (text: string) => send("/wallet/import", text),
};
