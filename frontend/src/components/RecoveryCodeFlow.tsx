import { useEffect, useRef, useState } from "react";
import { ApiError, api, saveBlob } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { isNetworkError, normalizeRecoveryCode } from "@/lib/recovery";
import type { RecoveryStatus } from "@/lib/types";

type Phase = "idle" | "creating" | "shown" | "confirming";

interface Props {
  /** Send replace:true - needed when a confirmed code already exists. */
  replace?: boolean;
  /** Content shown above the start button while idle. */
  intro?: React.ReactNode;
  startLabel: string;
  /** If set, window.confirm() with this text must be accepted before a code
   *  is created (used when the old code will stop working). */
  confirmStart?: string;
  onConfirmed: (status: RecoveryStatus) => void;
  /** Adds a "Not now" button; shown codes ask for confirmation first since
   *  leaving discards the only copy. */
  onDismiss?: () => void;
  /** Also show "Not now" before a code has been created (the blocking
   *  prompt wants it; the Settings card does not). */
  dismissWhileIdle?: boolean;
}

/** Create -> show once -> confirm, shared by the blocking prompt and the
 *  Settings card.
 *
 *  The code exists ONLY in this component's state: it is never written to
 *  storage, a URL or the console, and is dropped on confirm, dismiss and
 *  unmount. Creation is triggered from a click handler, not an effect,
 *  because React strict mode double-runs effects in dev and the second call
 *  would silently replace the code that was just displayed. */
export default function RecoveryCodeFlow({
  replace = false,
  intro,
  startLabel,
  confirmStart,
  onConfirmed,
  onDismiss,
  dismissWhileIdle = false,
}: Props) {
  const { t, locale } = useI18n();
  const [phase, setPhase] = useState<Phase>("idle");
  const [code, setCode] = useState<string | null>(null);
  const [createdAt, setCreatedAt] = useState<Date | null>(null);
  const [saved, setSaved] = useState(false);
  const [typed, setTyped] = useState("");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const codeBoxRef = useRef<HTMLDivElement>(null);

  // Move focus onto the code once it appears so keyboard and screen-reader
  // users land on it (the button that was clicked has just unmounted).
  useEffect(() => {
    if (phase === "shown") codeBoxRef.current?.focus();
  }, [phase]);

  function reset() {
    setPhase("idle");
    setCode(null);
    setCreatedAt(null);
    setSaved(false);
    setTyped("");
    setCopied(false);
  }

  function describe(err: unknown): string {
    if (err instanceof ApiError && err.status === 409) return t("rec.err.exists");
    if (err instanceof ApiError && err.status === 400) return t("rec.err.mismatch");
    if (isNetworkError(err)) return t("rec.err.network");
    return t("rec.err.generic");
  }

  async function start() {
    if (phase !== "idle") return;
    if (confirmStart && !window.confirm(confirmStart)) return;
    setPhase("creating");
    setError(null);
    try {
      const res = await api.createRecoveryCode(replace);
      setCode(res.code);
      setCreatedAt(new Date());
      setSaved(false);
      setTyped("");
      setCopied(false);
      setPhase("shown");
    } catch (err) {
      setError(describe(err));
      setPhase("idle");
    }
  }

  async function copy() {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setError(null);
    } catch {
      setCopied(false);
      setError(t("rec.flow.copyFailed"));
    }
  }

  function download() {
    if (!code) return;
    const date = (createdAt ?? new Date()).toLocaleString(locale);
    const body = [
      t("rec.flow.fileHeader"),
      t("rec.flow.fileCreated", { date }),
      "",
      code,
      "",
      t("rec.flow.fileBody"),
      "",
    ].join("\n");
    saveBlob(new Blob([body], { type: "text/plain;charset=utf-8" }), "myfinance-recovery-code.txt");
  }

  async function confirm() {
    if (!code || phase !== "shown") return;
    setPhase("confirming");
    setError(null);
    try {
      const status = await api.confirmRecoveryCode(normalizeRecoveryCode(typed));
      reset();
      onConfirmed(status);
    } catch (err) {
      setError(describe(err));
      setPhase("shown");
    }
  }

  function dismiss() {
    if (phase === "shown" && !window.confirm(t("rec.flow.discardConfirm"))) return;
    reset();
    setError(null);
    onDismiss?.();
  }

  if (phase === "idle" || phase === "creating") {
    return (
      <div className="space-y-3">
        {intro}
        {error ? (
          <p role="alert" className="banner-error">
            {error}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={start}
            disabled={phase === "creating"}
            className="btn-primary"
          >
            {phase === "creating" ? t("rec.flow.starting") : startLabel}
          </button>
          {onDismiss && dismissWhileIdle ? (
            <button type="button" onClick={dismiss} className="btn-ghost">
              {t("rec.flow.notNow")}
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  const typedOk = !!code && normalizeRecoveryCode(typed) === normalizeRecoveryCode(code);
  const showMismatch =
    !!code && !typedOk && normalizeRecoveryCode(typed).length >= normalizeRecoveryCode(code).length;
  const confirming = phase === "confirming";

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200">
        <p className="font-semibold">{t("rec.flow.warnTitle")}</p>
        <p className="mt-1">{t("rec.flow.warnBody")}</p>
      </div>

      <div>
        <span className="label" id="rec-code-label">
          {t("rec.flow.codeLabel")}
        </span>
        <div
          ref={codeBoxRef}
          tabIndex={-1}
          aria-labelledby="rec-code-label"
          className="select-all break-words rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 font-mono text-lg font-semibold leading-relaxed tracking-wider text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500/40 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-50"
        >
          {code}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button type="button" onClick={copy} className="btn-ghost">
            {copied ? t("rec.flow.copied") : t("rec.flow.copy")}
          </button>
          <button type="button" onClick={download} className="btn-ghost">
            {t("rec.flow.download")}
          </button>
        </div>
      </div>

      <label className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-200">
        <input
          type="checkbox"
          checked={saved}
          onChange={(e) => setSaved(e.target.checked)}
          disabled={confirming}
          className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-brand-600 focus:ring-2 focus:ring-brand-500/40 dark:border-slate-600"
        />
        <span>{t("rec.flow.saved")}</span>
      </label>

      <div>
        <label className="label" htmlFor="rec-type-back">
          {t("rec.flow.typeBack")}
        </label>
        <input
          id="rec-type-back"
          type="text"
          className="input font-mono"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          autoComplete="off"
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
          disabled={confirming}
        />
        <p className="mt-1 text-xs muted">{t("rec.flow.typeBackHint")}</p>
        {showMismatch ? (
          <p className="mt-1 text-xs text-rose-600 dark:text-rose-400">{t("rec.flow.mismatch")}</p>
        ) : null}
      </div>

      {error ? (
        <p role="alert" className="banner-error">
          {error}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={confirm}
          disabled={!saved || !typedOk || confirming}
          className="btn-primary"
        >
          {confirming ? t("rec.flow.confirming") : t("rec.flow.confirm")}
        </button>
        {onDismiss ? (
          <button type="button" onClick={dismiss} disabled={confirming} className="btn-ghost">
            {t("rec.flow.notNow")}
          </button>
        ) : null}
      </div>
    </div>
  );
}
