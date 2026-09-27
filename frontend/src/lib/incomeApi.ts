import { request } from "./api";
import type {
  B2bPreviewInput,
  B2bPreviewResult,
  ComparePreviewInput,
  CompareResult,
  IncomeEntry,
  IncomeEntryInput,
  IncomeSource,
  IncomeSourceInput,
  IncomeSummary,
  ReverseInput,
  ReverseResult,
  SourceYear,
  TaxParams,
  UopPreviewInput,
  UopPreviewResult,
} from "./incomeTypes";

/** /api/income - recurring sources, their month overrides, and the
 *  wallet-wide summary (routes/income.py). */
export const incomeApi = {
  sources: () => request<IncomeSource[]>("/income/sources"),
  createSource: (data: IncomeSourceInput) =>
    request<IncomeSource>("/income/sources", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateSource: (id: number, data: IncomeSourceInput) =>
    request<IncomeSource>(`/income/sources/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteSource: (id: number) =>
    request<void>(`/income/sources/${id}`, { method: "DELETE" }),
  sourceYear: (id: number, year: number) =>
    request<SourceYear>(`/income/sources/${id}/year/${year}`),
  upsertEntry: (id: number, month: string, data: IncomeEntryInput) =>
    request<IncomeEntry>(`/income/sources/${id}/entries/${month}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteEntry: (id: number, month: string) =>
    request<void>(`/income/sources/${id}/entries/${month}`, {
      method: "DELETE",
    }),
  summary: (year?: number) =>
    request<IncomeSummary>(`/income/summary${year ? `?year=${year}` : ""}`),
};

/** /api/tax - stateless Polish tax calculators (routes/tax.py). */
export const taxApi = {
  params: (year: number) => request<TaxParams>(`/tax/params/${year}`),
  previewUop: (data: UopPreviewInput) =>
    request<UopPreviewResult>("/tax/uop", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  previewB2b: (data: B2bPreviewInput) =>
    request<B2bPreviewResult>("/tax/b2b", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  compare: (data: ComparePreviewInput) =>
    request<CompareResult>("/tax/compare", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  reverse: (data: ReverseInput) =>
    request<ReverseResult>("/tax/reverse", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
