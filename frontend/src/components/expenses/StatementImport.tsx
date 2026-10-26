import { useEffect, useRef, useState } from "react";
import { api, fmtMoney } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSettings } from "@/components/SettingsProvider";
import type { MonthlyRecord } from "@/lib/types";
import { applyMapping, guessHeuristic, mappingFits, readCsv } from "@/lib/import/csv";
import { decodeText, MAX_CSV_BYTES, MAX_PDF_BYTES, type ImportRow } from "@/lib/import/parse";
import { findDebits } from "@/lib/import/statement";
import { matchByAmount, matchWithAssistant, planMonths, type CommitmentsByMonth } from "@/lib/import/match";
import type { Assistant } from "@/lib/import/assist";

/** "Wczytaj wyciąg" on the Expenses page: a bank statement (PDF or CSV) -> its outgoing payments -> per month, the
 *  recurring expenses it pays (marked paid at the statement's amount) and the rest as "other spending"
 *  (PATCH /api/monthly/{month}). The file is read in this browser (lib/import); the language model of Settings →
 *  "Statement import" (lib/import/assist.ts) is asked only for what code cannot settle. */

type Job = "columns" | "extract" | "match";
type Step =
  | { kind: "pick"; error?: string }
  | { kind: "password"; bytes: ArrayBuffer; wrong: boolean }
  | { kind: "consent"; mb: number; run: () => Promise<void>; back: Step }
  | { kind: "busy"; text: string }
  | { kind: "review"; skipped: number; incomplete: boolean; assisted: boolean };

const assistLib = () => import("@/lib/import/assist");

export default function StatementImport({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const { t, locale } = useI18n();
  const { settings, baseCurrency } = useSettings();
  const mode = settings?.statement_assist ?? "off";
  const [step, setStep] = useState<Step>({ kind: "pick" });
  const [rows, setRows] = useState<ImportRow[]>([]);
  const [byMonth, setByMonth] = useState<CommitmentsByMonth>({});
  const [records, setRecords] = useState<Record<string, MonthlyRecord | null>>({});
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const active = useRef<Assistant | null>(null);
  // Bumped on close: a run still going when the dialog closes drops its result.
  const run = useRef(0);

  useEffect(() => {
    if (!open) return;
    setStep({ kind: "pick" });
    setRows([]);
    setMsg(null);
  }, [open]);

  function close() {
    run.current++;
    active.current?.close();
    active.current = null;
    onClose();
  }

  /** Runs `task` with the wallet's assistant; in the browser, asks before the first download of a model. */
  async function withAssist(job: Job, task: (a: Assistant) => Promise<void>, back: Step, unavailable: string) {
    const lib = await assistLib();
    if (mode === "off") return setStep({ kind: "pick", error: unavailable });
    if (mode === "server") return task(lib.serverAssistant());
    if (!(await lib.browserSupported())) return setStep({ kind: "pick", error: t("stmt.unsupported") });
    const go = async () => {
      const a = lib.browserAssistant((p) => setStep({ kind: "busy", text: t("stmt.loadingModel", { pct: Math.round(p * 100) }) }));
      active.current = a;
      try {
        await task(a);
      } finally {
        a.close();
        active.current = null;
      }
    };
    const size = lib.SIZE_FOR[job];
    if (await lib.modelCached(size)) return go();
    setStep({ kind: "consent", mb: lib.DOWNLOAD_MB[size], run: () => guarded(go), back });
  }

  async function guarded(job: () => Promise<void>, onError: Step = { kind: "pick", error: t("stmt.failed") }) {
    const mine = run.current;
    try {
      await job();
    } catch {
      if (run.current === mine) setStep(onError);
    }
  }

  /** The months' checklists and records, code matching, then the review. */
  async function review(found: ImportRow[], skipped: number, incomplete: boolean, mine: number) {
    const months = [...new Set(found.map((r) => r.date.slice(0, 7)))].sort();
    const [lists, recs] = await Promise.all([
      Promise.all(months.map((m) => api.monthCommitments(m).catch(() => []))),
      Promise.all(months.map((m) => api.getMonth(m).catch(() => null))),
    ]);
    if (run.current !== mine) return;
    const commitments = Object.fromEntries(months.map((m, i) => [m, lists[i]]));
    const matched = matchByAmount(found, commitments);
    setByMonth(commitments);
    setRecords(Object.fromEntries(months.map((m, i) => [m, recs[i]])));
    setRows(matched);
    const { months: plan } = planMonths(matched, baseCurrency);
    setChosen(new Set(plan.filter((p) => !p.partial && sameCurrency(recs[months.indexOf(p.month)])).map((p) => p.month)));
    setStep({ kind: "review", skipped, incomplete, assisted: false });
  }

  const sameCurrency = (r: MonthlyRecord | null | undefined) => !r || r.currency === baseCurrency;

  async function onFile(file: File) {
    const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
    const isCsv = /\.(csv|txt)$/i.test(file.name) || file.type === "text/csv";
    if (!isPdf && !isCsv) return setStep({ kind: "pick", error: t("stmt.wrongType") });
    if (file.size > (isPdf ? MAX_PDF_BYTES : MAX_CSV_BYTES))
      return setStep({ kind: "pick", error: t("stmt.tooBig", { pdf: MAX_PDF_BYTES >> 20, csv: MAX_CSV_BYTES >> 20 }) });
    const bytes = await file.arrayBuffer();
    if (isPdf) await guarded(() => openPdf(bytes));
    else await guarded(() => openCsv(decodeText(bytes)));
  }

  async function openPdf(bytes: ArrayBuffer, pass?: string) {
    const mine = run.current;
    setStep({ kind: "busy", text: t("stmt.readingFile") });
    const { pdfLines, PdfPasswordError } = await import("@/lib/import/pdfText");
    let lines: string[];
    try {
      lines = await pdfLines(bytes, pass);
    } catch (e) {
      if (run.current !== mine) return;
      if (e instanceof PdfPasswordError) {
        setPassword("");
        return setStep({ kind: "password", bytes, wrong: e.retry });
      }
      return setStep({ kind: "pick", error: t("stmt.failed") });
    }
    if (run.current !== mine) return;
    if (!lines.length) return setStep({ kind: "pick", error: t("stmt.noText") });
    const debits = findDebits(lines, baseCurrency);
    if (debits.rows.length) return review(debits.rows, debits.skipped, false, mine);
    // No signed amounts (debits in their own column): the assistant reads the text.
    await withAssist(
      "extract",
      async (a) => {
        const { extractStatement } = await assistLib();
        const out = await extractStatement(a, lines, (done, total) =>
          setStep({ kind: "busy", text: t("stmt.reading", { done: Math.min(done + 1, total), total }) }),
        );
        await review(out.rows, out.skipped, out.incomplete, mine);
      },
      { kind: "pick" },
      t("stmt.needsAssist"),
    );
  }

  async function openCsv(text: string) {
    const mine = run.current;
    const table = readCsv(text);
    if (!table) return setStep({ kind: "pick", error: t("stmt.csvUnknown") });
    // The column guess is free; the assistant is asked only when it does not fit the rows.
    const guess = guessHeuristic(table);
    const fromGuess = mappingFits(guess, table) ? applyMapping(guess, table, baseCurrency) : null;
    if (fromGuess && fromGuess.rows.length) return review(fromGuess.rows, fromGuess.skipped, false, mine);
    await withAssist(
      "columns",
      async (a) => {
        setStep({ kind: "busy", text: t("stmt.readingFile") });
        const mapping = await a.columns(table.header, table.data.slice(0, 8));
        if (run.current !== mine) return;
        if (!mappingFits(mapping, table)) return setStep({ kind: "pick", error: t("stmt.csvUnknown") });
        const out = applyMapping(mapping, table, baseCurrency);
        await review(out.rows, out.skipped, false, mine);
      },
      { kind: "pick" },
      t("stmt.csvUnknown"),
    );
  }

  async function assistMatch(current: Extract<Step, { kind: "review" }>) {
    const mine = run.current;
    const before = rows;
    await withAssist(
      "match",
      (a) =>
        guarded(
          async () => {
            const out = await matchWithAssistant(a, before, byMonth, (done, total) =>
              setStep({ kind: "busy", text: t("stmt.matching", { done: Math.min(done + 1, total), total }) }),
            );
            if (run.current !== mine) return;
            setRows(out);
            setStep({ ...current, assisted: true });
          },
          { ...current, assisted: true },
        ),
      current,
      t("stmt.needsAssist"),
    );
  }

  const { months: plan, foreign } = planMonths(rows, baseCurrency);

  async function apply() {
    const todo = plan.filter((p) => chosen.has(p.month));
    setSaving(true);
    setMsg(null);
    let ok = 0;
    for (const p of todo) {
      try {
        await api.patchMonth(p.month, {
          commitments: (byMonth[p.month] ?? []).map((c) =>
            p.paid.has(c.expense_id)
              ? { expense_id: c.expense_id, amount: p.paid.get(c.expense_id)!, paid: true }
              : { expense_id: c.expense_id, amount: c.amount, paid: c.paid },
          ),
          other_spent: p.other,
        });
        ok++;
      } catch {
        // counted below; the dialog stays open so the rest can be retried
      }
    }
    setSaving(false);
    onSaved();
    if (ok === todo.length) close();
    else setMsg(t("stmt.applyFailed", { ok, n: todo.length }));
  }

  const patch = (key: string, p: Partial<ImportRow>) => setRows((all) => all.map((r) => (r.key === key ? { ...r, ...p } : r)));
  const money = (v: number, c = baseCurrency) => fmtMoney(v, c, locale);
  const openCommitments = Object.entries(byMonth).some(([m, cs]) => cs.some((c) => !rows.some((r) => r.commitment === c.expense_id && r.date.startsWith(m))));
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/60 px-4 py-6">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="stmt-title"
        className="flex max-h-full w-full max-w-2xl flex-col rounded-2xl border border-slate-200 bg-white shadow-lg dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-center justify-between gap-3 border-b p-5 divider">
          <h2 id="stmt-title" className="text-lg font-semibold">
            {t("stmt.title")}
          </h2>
          <button type="button" className="btn-ghost" onClick={close}>
            {t("stmt.cancel")}
          </button>
        </div>

        <div className="space-y-4 overflow-y-auto p-5">
          {step.kind === "pick" && (
            <>
              <p className="text-sm muted">{t("stmt.lead")}</p>
              <p className="text-xs subtle">{t(`stmt.where.${mode}`)}</p>
              <label className="btn-primary w-full cursor-pointer justify-center">
                {t("stmt.choose")}
                <input
                  type="file"
                  accept=".pdf,.csv,.txt,application/pdf,text/csv"
                  className="sr-only"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    e.target.value = "";
                    if (f) onFile(f);
                  }}
                />
              </label>
              {step.error && <p className="banner-error">{step.error}</p>}
            </>
          )}

          {step.kind === "password" && (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                guarded(() => openPdf(step.bytes, password));
              }}
            >
              <label htmlFor="stmt-pass" className="label">
                {t("stmt.password")}
              </label>
              <input id="stmt-pass" type="password" autoComplete="off" className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
              <p className="text-xs subtle">{t("stmt.passwordHint")}</p>
              {step.wrong && <p className="banner-error">{t("stmt.passwordWrong")}</p>}
              <button type="submit" className="btn-primary" disabled={!password}>
                {t("stmt.unlock")}
              </button>
            </form>
          )}

          {step.kind === "consent" && (
            <div className="space-y-4">
              <p className="text-sm">{t("stmt.consent", { mb: step.mb })}</p>
              <div className="flex gap-2">
                <button type="button" className="btn-ghost" onClick={() => setStep(step.back)}>
                  {t("stmt.cancel")}
                </button>
                <button type="button" className="btn-primary" onClick={() => step.run()}>
                  {t("stmt.download")}
                </button>
              </div>
            </div>
          )}

          {step.kind === "busy" && (
            <p className="py-6 text-center text-sm muted" role="status" aria-live="polite">
              {step.text}
            </p>
          )}

          {step.kind === "review" && (
            <>
              <div className="space-y-1 text-sm">
                <p className="font-medium">{t("stmt.found", { n: rows.length })}</p>
                {step.skipped > 0 && <p className="text-xs subtle">{t("stmt.skipped", { n: step.skipped })}</p>}
                {foreign > 0 && <p className="text-xs subtle">{t("stmt.foreign", { currency: baseCurrency, n: foreign })}</p>}
                {step.incomplete && <p className="banner-info">{t("stmt.incomplete")}</p>}
              </div>
              {mode !== "off" && !step.assisted && openCommitments && (
                <button type="button" className="btn-ghost w-full" onClick={() => assistMatch(step)}>
                  {t("stmt.matchAssist")}
                </button>
              )}

              <section className="space-y-2">
                <h3 className="font-semibold">{t("stmt.months")}</h3>
                <ul className="space-y-2">
                  {plan.map((p) => {
                    const rec = records[p.month];
                    const blocked = !sameCurrency(rec);
                    return (
                      <li key={p.month} className="flex items-start gap-3 rounded-xl border p-3 divider">
                        <input
                          type="checkbox"
                          className="mt-1 h-4 w-4"
                          checked={chosen.has(p.month)}
                          disabled={blocked}
                          aria-label={p.month}
                          onChange={(e) =>
                            setChosen((s) => {
                              const n = new Set(s);
                              if (e.target.checked) n.add(p.month);
                              else n.delete(p.month);
                              return n;
                            })
                          }
                        />
                        <div className="min-w-0 text-sm">
                          <p className="font-medium tabular-nums">{p.month}</p>
                          <p className="muted">{t("stmt.monthLine", { paid: p.paid.size, other: money(p.other) })}</p>
                          {rec && <p className="text-xs subtle">{t("stmt.monthNow", { other: money(rec.other_spent ?? rec.actual_spent, rec.currency) })}</p>}
                          {p.partial && <p className="text-xs subtle">{t("stmt.partial")}</p>}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>

              <ul className="divide-y rounded-xl border divider">
                {rows.map((r) => {
                  const options = byMonth[r.date.slice(0, 7)] ?? [];
                  return (
                    <li key={r.key} className={`flex flex-wrap items-center gap-2 p-3 text-sm ${r.checked ? "" : "opacity-60"}`}>
                      <input
                        type="checkbox"
                        className="h-4 w-4"
                        checked={r.checked}
                        aria-label={`${t("stmt.include")}: ${r.note}`}
                        onChange={(e) => patch(r.key, { checked: e.target.checked })}
                      />
                      <span className="w-24 shrink-0 tabular-nums subtle">{r.date}</span>
                      <span className="min-w-0 flex-1 truncate">{r.note}</span>
                      <span className="shrink-0 font-medium tabular-nums">{money(r.amount, r.currency)}</span>
                      <select
                        className="input w-auto py-1 text-xs"
                        value={r.commitment ?? ""}
                        aria-label={t("stmt.other")}
                        onChange={(e) => patch(r.key, { commitment: e.target.value ? Number(e.target.value) : null })}
                      >
                        <option value="">{t("stmt.other")}</option>
                        {options.map((c) => (
                          <option key={c.expense_id} value={c.expense_id}>
                            {c.name}
                          </option>
                        ))}
                      </select>
                      {(r.transfer || r.unverified) && (
                        <span className="w-full pl-6 text-xs subtle">{r.transfer ? t("stmt.transfer") : t("stmt.unverified")}</span>
                      )}
                    </li>
                  );
                })}
              </ul>
              {msg && <p className="banner-error">{msg}</p>}
            </>
          )}
        </div>

        {step.kind === "review" && (
          <div className="flex gap-2 border-t p-5 divider">
            <button type="button" className="btn-ghost" onClick={() => setStep({ kind: "pick" })} disabled={saving}>
              {t("stmt.another")}
            </button>
            <button type="button" className="btn-primary flex-1 justify-center" onClick={apply} disabled={saving || !chosen.size}>
              {saving ? t("stmt.applying") : t("stmt.apply", { n: chosen.size })}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
