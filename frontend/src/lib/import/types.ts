import type { CsvMapping } from "./csv";

/** The statement assistant's contract (lib/import/assist.ts implements it in the browser and on the server). Kept
 *  apart from assist.ts so code that only needs the shapes (match.ts, the checks) does not load WebLLM. */

export type AssistMode = "off" | "browser" | "server";

export interface Extracted {
  line: number;
  date: string;
  amount: number;
  direction: "out" | "in";
  currency: string;
  description: string;
}

export interface CommitmentBrief {
  id: number;
  name: string;
  category: string;
  amount: number;
  currency: string;
}

export interface PaymentBrief {
  id: number;
  date: string;
  amount: number;
  note: string;
}

export interface Assistant {
  columns(header: string[], sample: string[][]): Promise<CsvMapping>;
  /** One chunk of PDF lines; `firstLine` is the 1-based number of lines[0]. */
  extractChunk(lines: string[], firstLine: number): Promise<Extracted[]>;
  match(commitments: CommitmentBrief[], payments: PaymentBrief[]): Promise<{ commitment: number; payment: number }[]>;
  close(): void;
}
