/** A PDF statement -> its printed lines, top to bottom, page after page. pdf.js runs in its own worker from this
 *  origin and is loaded only when a PDF is chosen. Only the text layer is read: a scanned statement (images only)
 *  gives no lines. Nothing is rendered and no fonts or wasm are fetched. */

/** The statement is password-protected (several Polish banks send them that way); `retry` = a wrong password. */
export class PdfPasswordError extends Error {
  constructor(public retry: boolean) {
    super("password");
  }
}

interface TextItem {
  str: string;
  transform: number[];
}

export async function pdfLines(bytes: ArrayBuffer, password?: string): Promise<string[]> {
  const pdfjs = await import("pdfjs-dist");
  if (!pdfjs.GlobalWorkerOptions.workerPort)
    pdfjs.GlobalWorkerOptions.workerPort = new Worker(new URL("./pdf.worker.ts", import.meta.url), { type: "module" });
  // pdf.js transfers the buffer to its worker; pass a copy so a password retry can reuse the original.
  const task = pdfjs.getDocument({ data: bytes.slice(0), password, useWasm: false, disableFontFace: true, useWorkerFetch: false });
  let doc;
  try {
    doc = await task.promise;
  } catch (e) {
    await task.destroy();
    if (e instanceof Error && e.name === "PasswordException") throw new PdfPasswordError(password !== undefined);
    throw e;
  }
  const lines: string[] = [];
  try {
    for (let p = 1; p <= doc.numPages; p++) {
      const page = await doc.getPage(p);
      const content = await page.getTextContent();
      // Items on one baseline (within 2 pt) form a line; lines run top to bottom, items left to right.
      const rows: { y: number; items: { x: number; s: string }[] }[] = [];
      for (const it of content.items as TextItem[]) {
        if (!("str" in it) || !it.str.trim()) continue;
        const [x, y] = [it.transform[4], it.transform[5]];
        const row = rows.find((r) => Math.abs(r.y - y) <= 2);
        if (row) row.items.push({ x, s: it.str });
        else rows.push({ y, items: [{ x, s: it.str }] });
      }
      rows.sort((a, b) => b.y - a.y);
      for (const r of rows) {
        const text = r.items
          .sort((a, b) => a.x - b.x)
          .map((i) => i.s.trim())
          .join("  ")
          .replace(/\s{3,}/g, "  ");
        if (text) lines.push(text);
      }
      page.cleanup();
    }
  } finally {
    await task.destroy();
  }
  return lines;
}
