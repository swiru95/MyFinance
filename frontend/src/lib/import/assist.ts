import type { AppConfig, ChatCompletionRequestNonStreaming, ModelRecord, WebWorkerMLCEngine } from "@mlc-ai/web-llm";
import { ApiError, request } from "@/lib/api";
import type { CsvMapping } from "./csv";
import type { Assistant, Extracted } from "./types";
import { cleanNote, CURRENCIES, groundTruth, type ImportRow } from "./parse";

/** The statement import's helper model, for what code alone cannot settle: CSV columns it does not recognise, PDFs
 *  whose payments carry no minus sign, recurring expenses whose amount varies. Settings → "Statement import"
 *  picks where it runs (backend routes/statement.py, setting `statement_assist`):
 *  - "browser": WebLLM on WebGPU in this tab. Qwen3 0.6B (~335 MB) maps columns, Qwen3 1.7B (~970 MB) does the
 *    rest; downloaded once from Hugging Face at pinned revisions (or NEXT_PUBLIC_MODELS_URL), checked against the
 *    SRI hashes below, kept in the browser's cache. The statement never leaves the tab.
 *  - "server": the backend's llama-server model (MYFINANCE_LLM_IMPORT_MODEL). Only the part a job needs is sent
 *    (a CSV header and 8 rows, 30 lines of PDF text, one month's expenses and candidate payments), never stored.
 *  Either way every answer is checked here: amounts and dates against the statement text, ids against what was
 *  offered. */

export type { AssistMode, Assistant, CommitmentBrief, Extracted, PaymentBrief } from "./types";

// ---- Server -----------------------------------------------------------------------------------------------------

/** The backend's model. One retry on a timeout: the first call can run out while the server loads the model. */
export function serverAssistant(): Assistant {
  async function post<T>(path: string, body: unknown): Promise<T> {
    const init = { method: "POST", body: JSON.stringify(body) };
    try {
      return await request<T>(path, init);
    } catch (e) {
      // 503: the backend's own timeout; 504: the gateway's.
      if (e instanceof ApiError && (e.status === 503 || e.status === 504)) return request<T>(path, init);
      throw e;
    }
  }
  return {
    columns: (header, sample) => post<CsvMapping>("/statement/columns", { header: header.map(cell), sample: sample.map((r) => r.map(cell)) }),
    extractChunk: async (lines, firstLine) =>
      (await post<{ transactions: Extracted[] }>("/statement/extract", { lines: lines.map((l) => l.slice(0, 300)), first_line: firstLine })).transactions,
    match: async (commitments, payments) => (await post<{ matches: { commitment: number; payment: number }[] }>("/statement/match", { commitments, payments })).matches,
    close() {},
  };
}

const cell = (c: string) => c.slice(0, 80);

// ---- Browser ----------------------------------------------------------------------------------------------------

export type ModelSize = "small" | "large";

const SELF_HOSTED = (process.env.NEXT_PUBLIC_MODELS_URL || "").replace(/\/$/, "");
const LIB = "v0_2_86";
const LIB_COMMIT = "00fe7a40e57e5e8eb9fef87526a4bf28ad5846c0"; // mlc-ai/binary-mlc-llm-libs with web-llm-models/v0_2_86

/** Where a model's files come from: Hugging Face and GitHub at pinned revisions, or a self-hosted copy laid out as
 *  <base>/<model_id>/<rev[0:8]>/resolve/main/ and <base>/libs/<lib version>/<wasm>. */
function record(id: string, rev: string, wasm: string, vram: number, sri: { config: string; lib: string }): ModelRecord {
  return {
    model_id: id,
    model: SELF_HOSTED ? `${SELF_HOSTED}/${id}/${rev.slice(0, 8)}/` : `https://huggingface.co/mlc-ai/${id}/resolve/${rev}/`,
    model_lib: SELF_HOSTED
      ? `${SELF_HOSTED}/libs/${LIB}/${wasm}`
      : `https://raw.githubusercontent.com/mlc-ai/binary-mlc-llm-libs/${LIB_COMMIT}/web-llm-models/${LIB}/base/${wasm}`,
    vram_required_MB: vram,
    low_resource_required: true,
    required_features: ["shader-f16"],
    overrides: { context_window_size: 4096 },
    integrity: {
      config: sri.config,
      model_lib: sri.lib,
      tokenizer: { "tokenizer.json": "sha384-bBcp1iraOY8O3lJXFKDjSlRbqFZ2wbSX1HMscuq4lbj4bO+YyBt2tRf6Kj8+hxFw" },
    },
  };
}

const MODELS: Record<ModelSize, ModelRecord> = {
  small: record("Qwen3-0.6B-q4f16_1-MLC", "8c14ce481d4c692769976ad52afea453a102df19", "Qwen3-0.6B-q4f16_1_cs1k-webgpu.wasm", 1403.34, {
    config: "sha384-9fxUxKNOFFPlaUNBJNRKF5bctTgaxIbd2eszFnw4jzDyqL0O7tuJxJYFqeBz54z4",
    lib: "sha384-l+z226DC4XeJrqhzjXTtmWuMke7hpfJbQc4fElaJevDKbOEPqRlh2j/c+J9nzcu5",
  }),
  large: record("Qwen3-1.7B-q4f16_1-MLC", "80b3abcec6c3b3f5355dc0cc99cc4fb578f192bc", "Qwen3-1.7B-q4f16_1_cs1k-webgpu.wasm", 2036.66, {
    config: "sha384-X+UwGfB2vtN1DuSZFxz1/41rzSrFguvyGeha2kgsNuD8HOxT7CgMQqI+8+70J0co",
    lib: "sha384-Nl0m2ynzyk2i2j+XyK8Og/dAjX2xlKfgrkjOCwmhQEgmOit1qbAqcrhKy9WjE0J4",
  }),
};

export const DOWNLOAD_MB: Record<ModelSize, number> = { small: 335, large: 968 };

const APP_CONFIG: AppConfig = { model_list: Object.values(MODELS), cacheBackend: "cache" };

interface GpuNavigator {
  gpu?: { requestAdapter: () => Promise<{ features: Set<string> } | null> };
}

/** WebGPU with 16-bit shaders: what both models need. */
export async function browserSupported(): Promise<boolean> {
  try {
    const adapter = await (navigator as GpuNavigator).gpu?.requestAdapter();
    return !!adapter?.features.has("shader-f16");
  } catch {
    return false;
  }
}

export async function modelCached(size: ModelSize): Promise<boolean> {
  const { hasModelInCache } = await import("@mlc-ai/web-llm");
  return hasModelInCache(MODELS[size].model_id, APP_CONFIG).catch(() => false);
}

export async function deleteBrowserModels(): Promise<void> {
  const { deleteModelAllInfoInCache } = await import("@mlc-ai/web-llm");
  for (const m of Object.values(MODELS)) await deleteModelAllInfoInCache(m.model_id, APP_CONFIG).catch(() => {});
}

/** Which model a job uses in the browser: column mapping is small enough for the 0.6B one. */
export const SIZE_FOR = { columns: "small", extract: "large", match: "large" } as const satisfies Record<string, ModelSize>;

const COLUMNS_SCHEMA = {
  type: "object",
  properties: {
    date: { type: "integer" },
    amount: { type: "integer" },
    debit: { type: "integer" },
    credit: { type: "integer" },
    outgoing: { type: "string", enum: ["negative", "positive"] },
    description: { type: "array", items: { type: "integer" }, maxItems: 3 },
    currency: { type: "integer" },
  },
  required: ["date", "amount", "debit", "credit", "outgoing", "description", "currency"],
};
const COLUMNS_SYSTEM =
  "You map the columns of a bank statement CSV. Columns are numbered from 0. Answer with JSON only. " +
  "date: the transaction or booking date column. amount: one signed amount column, or -1 if amounts are split. " +
  "debit / credit: separate money-out / money-in columns, or -1. outgoing: whether money going out is printed " +
  "negative or positive in the amount column. description: up to 3 columns describing the payee or title. " +
  "currency: the currency column, or -1.";

const EXTRACT_SCHEMA = {
  type: "object",
  properties: {
    transactions: {
      type: "array",
      maxItems: 30,
      items: {
        type: "object",
        properties: {
          line: { type: "integer" },
          date: { type: "string", pattern: "^\\d{4}-\\d{2}-\\d{2}$" },
          amount: { type: "number" },
          direction: { type: "string", enum: ["out", "in"] },
          currency: { type: "string", pattern: "^[A-Z]{3}$" },
          description: { type: "string", maxLength: 80 },
        },
        required: ["line", "date", "amount", "direction", "currency", "description"],
      },
    },
  },
  required: ["transactions"],
};
const EXTRACT_SYSTEM =
  "You read transactions from the text of a Polish bank statement. Each line starts with its number (L12:). " +
  "List every transaction once. line: the number of the line holding its amount. date: the transaction date as " +
  "YYYY-MM-DD, exactly as printed (convert the format only). amount: the amount as printed, without a sign. " +
  "direction: out for money leaving the account (card payment, transfer out, BLIK, fee, withdrawal), in for money " +
  "arriving. currency: as printed, PLN if none. description: the merchant or title, short. Ignore balances, " +
  "totals and page headers. Answer with JSON only.";

const MATCH_SCHEMA = {
  type: "object",
  properties: {
    matches: {
      type: "array",
      items: {
        type: "object",
        properties: { commitment: { type: "integer" }, payment: { type: "integer" } },
        required: ["commitment", "payment"],
      },
    },
  },
  required: ["matches"],
};
const MATCH_SYSTEM =
  "You match recurring expenses (rent, utilities, subscriptions, loans) to the payments of one month of a Polish " +
  "bank statement. A payment pays an expense when its payee or title names the same company or service, even if " +
  "the amount differs a little. For each expense give the id of the paying payment, or -1 if none clearly pays " +
  "it. Use a payment at most once. Answer with JSON only.";

/** The in-browser models. Each job loads the model it needs (and frees the other), so the GPU holds one at a time;
 *  `onLoad` gets 0..1 while a model downloads and compiles. */
export function browserAssistant(onLoad: (p: number) => void): Assistant {
  let worker: Worker | null = null;
  let engine: WebWorkerMLCEngine | null = null;
  let loaded: ModelSize | null = null;

  async function ensure(size: ModelSize): Promise<WebWorkerMLCEngine> {
    if (engine && loaded === size) return engine;
    close();
    const { CreateWebWorkerMLCEngine } = await import("@mlc-ai/web-llm");
    worker = new Worker(new URL("./llm.worker.ts", import.meta.url), { type: "module" });
    engine = await CreateWebWorkerMLCEngine(worker, MODELS[size].model_id, {
      appConfig: APP_CONFIG,
      initProgressCallback: (r) => onLoad(r.progress),
    });
    loaded = size;
    return engine;
  }

  async function json<T>(size: ModelSize, system: string, user: string, schema: object, maxTokens: number): Promise<T> {
    const e = await ensure(size);
    const req: ChatCompletionRequestNonStreaming = {
      messages: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
      temperature: 0,
      max_tokens: maxTokens,
      response_format: { type: "json_object", schema: JSON.stringify(schema) },
      extra_body: { enable_thinking: false },
    };
    const res = await e.chat.completions.create(req);
    return JSON.parse(res.choices[0]?.message?.content || "{}") as T;
  }

  function close() {
    engine?.unload().catch(() => {});
    worker?.terminate();
    engine = null;
    worker = null;
    loaded = null;
  }

  return {
    async columns(header, sample) {
      const show = (r: string[]) => r.map((c, i) => `${i}: ${c.slice(0, 40)}`).join(" | ");
      const m = await json<CsvMapping>(SIZE_FOR.columns, COLUMNS_SYSTEM, `Header: ${show(header)}\nRows:\n${sample.map(show).join("\n")}`, COLUMNS_SCHEMA, 120);
      const width = Math.max(header.length, ...sample.map((r) => r.length));
      const col = (v: number) => (Number.isInteger(v) && v >= 0 && v < width ? v : -1);
      return {
        date: col(m.date),
        amount: col(m.amount),
        debit: col(m.debit),
        credit: col(m.credit),
        outgoing: m.outgoing === "positive" ? "positive" : "negative",
        description: (m.description ?? []).filter((c) => col(c) >= 0).slice(0, 3),
        currency: col(m.currency),
      };
    },
    async extractChunk(lines, firstLine) {
      const user = lines.map((l, j) => `L${firstLine + j}: ${l}`).join("\n");
      const out = await json<{ transactions?: Extracted[] }>(SIZE_FOR.extract, EXTRACT_SYSTEM, user, EXTRACT_SCHEMA, 1800);
      return out.transactions ?? [];
    },
    async match(commitments, payments) {
      const user =
        "Recurring expenses:\n" +
        commitments.map((c) => `id ${c.id}: ${c.name} (${c.category}), usually ${c.amount.toFixed(2)} ${c.currency}`).join("\n") +
        "\n\nPayments:\n" +
        payments.map((p) => `id ${p.id}: ${p.date}  ${p.amount.toFixed(2)}  ${p.note}`).join("\n");
      const out = await json<{ matches?: { commitment: number; payment: number }[] }>(SIZE_FOR.match, MATCH_SYSTEM, user, MATCH_SCHEMA, 40 + 20 * commitments.length);
      return out.matches ?? [];
    },
    close,
  };
}

// ---- Shared: a whole PDF through extractChunk, every row checked against the text ------------------------------

const CHUNK = 30;
const OVERLAP = 4;

export async function extractStatement(
  assistant: Assistant,
  lines: string[],
  onChunk: (done: number, total: number) => void,
): Promise<{ rows: ImportRow[]; skipped: number; incomplete: boolean }> {
  const starts: number[] = [];
  for (let s = 0; s < lines.length; s += CHUNK - OVERLAP) {
    starts.push(s);
    if (s + CHUNK >= lines.length) break;
  }
  const byLine = new Map<number, Extracted>();
  let incomplete = false;
  for (let i = 0; i < starts.length; i++) {
    onChunk(i, starts.length);
    const from = starts[i];
    const part = lines.slice(from, from + CHUNK);
    let found: Extracted[];
    try {
      found = await assistant.extractChunk(part, from + 1);
    } catch {
      incomplete = true; // a cut-off or failed answer: this part is missing, and the review says so
      continue;
    }
    // A line read twice (the overlap) keeps its first reading.
    for (const t of found) if (t.line > from && t.line <= from + part.length && !byLine.has(t.line)) byLine.set(t.line, t);
  }
  onChunk(starts.length, starts.length);

  const rows: ImportRow[] = [];
  let skipped = 0;
  for (const t of [...byLine.values()].sort((a, b) => a.line - b.line)) {
    const amount = Math.abs(t.amount);
    if (t.direction !== "out" || !(amount > 0) || !CURRENCIES.includes(t.currency)) {
      skipped++;
      continue;
    }
    // The amount must be printed on its line; the date on that line or the few around it.
    const near = groundTruth(lines.slice(Math.max(0, t.line - 3), t.line + 2).join("\n"));
    const onLine = groundTruth(lines[t.line - 1] ?? "");
    const unverified = !onLine.amounts.has(Math.round(amount * 100)) || !near.dates.has(t.date);
    rows.push({
      key: `pdf-${t.line}`,
      date: t.date,
      amount: Math.round(amount * 100) / 100,
      currency: t.currency,
      note: cleanNote(t.description),
      commitment: null,
      checked: !unverified,
      unverified,
      transfer: false,
    });
  }
  return { rows, skipped, incomplete };
}
