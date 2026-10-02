import { useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";
import {
  MAX_WALLET_FILE_BYTES,
  WalletFileError,
  walletApi,
  type PlanItem,
  type PlanSection,
  type WalletPlan,
} from "@/lib/walletApi";
import { useSettings } from "./SettingsProvider";

const SECTIONS: PlanSection[] = ["setting", "asset", "income_source", "expense"];

type Phase = "idle" | "reading" | "preview" | "importing" | "done";

/** Settings card: download the wallet's setup as one file, or import one.
 *  Import is always preview first (a dry run the server computes), and only a
 *  confirm writes - the file text is kept in memory between the two, so what
 *  was previewed is exactly what is sent. */
export default function WalletCard() {
  const { t, td } = useI18n();
  const { refresh } = useSettings();
  const input = useRef<HTMLInputElement>(null);
  const [exporting, setExporting] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [fileName, setFileName] = useState("");
  const [text, setText] = useState("");
  const [plan, setPlan] = useState<WalletPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [problems, setProblems] = useState<{ where: string; message: string }[]>([]);
  const [exportError, setExportError] = useState<string | null>(null);

  function reset() {
    setPhase("idle");
    setText("");
    setFileName("");
    setPlan(null);
    setError(null);
    setProblems([]);
    if (input.current) input.current.value = "";
  }

  function fail(err: unknown, fallback: string) {
    if (err instanceof WalletFileError) {
      setError(err.message);
      setProblems(err.problems);
    } else {
      setError(err instanceof Error ? err.message : fallback);
      setProblems([]);
    }
  }

  async function doExport() {
    setExporting(true);
    setExportError(null);
    try {
      await walletApi.exportFile();
    } catch (err) {
      setExportError(err instanceof Error ? err.message : t("wallet.exportFailed"));
    } finally {
      setExporting(false);
    }
  }

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setProblems([]);
    setPlan(null);
    setFileName(file.name);
    if (file.size > MAX_WALLET_FILE_BYTES) {
      setPhase("idle");
      setError(t("wallet.tooBig"));
      return;
    }
    setPhase("reading");
    try {
      const body = await file.text();
      setText(body);
      setPlan(await walletApi.preview(body));
      setPhase("preview");
    } catch (err) {
      setPhase("idle");
      setText("");
      fail(err, t("wallet.readFailed"));
    }
  }

  async function confirm() {
    setPhase("importing");
    setError(null);
    try {
      const done = await walletApi.apply(text);
      setPlan(done);
      setText("");
      setPhase("done");
      // The file may have set the base currency, time zone or feature switches.
      await refresh();
    } catch (err) {
      setPhase("preview");
      fail(err, t("wallet.importFailed"));
    }
  }

  function describe(item: PlanItem): string {
    const key = `wallet.reason.${item.reason}`;
    const text = t(key, {
      existing: item.existing ? td(item.existing) : "",
      incoming: item.incoming ?? "",
    });
    return text === key ? "" : text;
  }

  function itemName(item: PlanItem): string {
    return item.section === "setting" ? t(`wallet.setting.${item.name}`) : td(item.name);
  }

  const counts = plan
    ? SECTIONS.reduce(
        (sum, s) => ({
          create: sum.create + plan.counts[s].create,
          fill: sum.fill + plan.counts[s].fill,
          left: sum.left + plan.counts[s].skip + plan.counts[s].keep,
        }),
        { create: 0, fill: 0, left: 0 },
      )
    : { create: 0, fill: 0, left: 0 };

  return (
    <div className="card max-w-md space-y-4">
      <div>
        <h2 className="text-lg font-semibold">{t("wallet.title")}</h2>
        <p className="text-sm muted">{t("wallet.subtitle")}</p>
      </div>

      <div
        role="note"
        className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200"
      >
        {t("wallet.notEncrypted")}
      </div>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold">{t("wallet.exportTitle")}</h3>
        <p className="text-xs muted">{t("wallet.exportBody")}</p>
        {exportError && <p className="banner-error">{exportError}</p>}
        <button type="button" className="btn-primary" onClick={doExport} disabled={exporting}>
          {exporting ? t("wallet.exporting") : t("wallet.export")}
        </button>
      </section>

      <section className="divider space-y-3 border-t pt-4">
        <h3 className="text-sm font-semibold">{t("wallet.importTitle")}</h3>
        <p className="text-xs muted">{t("wallet.importBody")}</p>

        {error && (
          <div className="banner-error" role="alert">
            <p className="font-medium">{phase === "preview" ? error : t("wallet.invalid")}</p>
            {phase !== "preview" && <p className="mt-1 break-words">{error}</p>}
            {problems.length > 0 && (
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs">
                {problems.slice(0, 6).map((p, i) => (
                  <li key={i} className="break-words">
                    <span className="font-mono">{p.where}</span>: {p.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {(phase === "idle" || phase === "reading") && (
          <>
            <input
              ref={input}
              id="wallet-file"
              type="file"
              accept=".json,application/json"
              className="sr-only"
              onChange={onPick}
              disabled={phase === "reading"}
            />
            <label
              htmlFor="wallet-file"
              className={`btn-ghost cursor-pointer ${phase === "reading" ? "opacity-50" : ""}`}
            >
              {phase === "reading" ? t("wallet.reading") : t("wallet.choose")}
            </label>
          </>
        )}

        {plan && (phase === "preview" || phase === "importing") && (
          <div className="space-y-3">
            <div>
              <p className="text-sm font-medium break-words">
                {t("wallet.previewTitle", { file: fileName })}
              </p>
              <p className="text-xs muted">{t("wallet.summary", counts)}</p>
            </div>

            {plan.warnings.map((w, i) => (
              <p key={i} className="banner-info">
                {t(`wallet.warn.${w.code}`, { from: w.args[0] ?? "", to: w.args[1] ?? "" })}
              </p>
            ))}

            <PlanList plan={plan} t={t} itemName={itemName} describe={describe} />

            <p className="text-xs subtle">{t("wallet.rule")}</p>
            {plan.writes === 0 && <p className="banner-info">{t("wallet.nothing")}</p>}

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="btn-primary"
                onClick={confirm}
                disabled={phase === "importing" || plan.writes === 0}
              >
                {phase === "importing" ? t("wallet.importing") : t("wallet.confirm")}
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={reset}
                disabled={phase === "importing"}
              >
                {t("wallet.cancel")}
              </button>
            </div>
          </div>
        )}

        {plan && phase === "done" && (
          <div className="space-y-3">
            <p className="banner-info" role="status">
              {t("wallet.done", counts)}
            </p>
            <button type="button" className="btn-ghost" onClick={reset}>
              {t("wallet.another")}
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

const ACTION_STYLE: Record<PlanItem["action"], string> = {
  create: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  fill: "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100",
  skip: "bg-amber-100 text-amber-900 dark:bg-amber-500/15 dark:text-amber-200",
  keep: "bg-slate-100 text-slate-700 dark:bg-slate-700/50 dark:text-slate-200",
};

function PlanList({
  plan,
  t,
  itemName,
  describe,
}: {
  plan: WalletPlan;
  t: (key: string, vars?: Record<string, string | number>) => string;
  itemName: (item: PlanItem) => string;
  describe: (item: PlanItem) => string;
}) {
  return (
    <div className="max-h-72 space-y-3 overflow-y-auto rounded-lg border border-slate-200 p-3 dark:border-slate-700">
      {SECTIONS.map((section) => {
        const items = plan.items.filter((i) => i.section === section);
        if (items.length === 0) return null;
        return (
          <div key={section}>
            <h4 className="text-xs font-semibold uppercase tracking-wide muted">
              {t(`wallet.section.${section}`)}
            </h4>
            <ul className="mt-1 space-y-1.5">
              {items.map((item, i) => {
                const why = describe(item);
                return (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span
                      className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium ${ACTION_STYLE[item.action]}`}
                    >
                      {t(`wallet.action.${item.action}`)}
                    </span>
                    <span className="min-w-0 break-words">
                      {itemName(item)}
                      {why && <span className="block text-xs muted">{why}</span>}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
