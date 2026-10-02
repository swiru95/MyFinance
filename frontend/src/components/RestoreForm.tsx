import { useEffect, useState } from "react";
import { ApiError, RateLimitError, api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { fmtCountdown, isNetworkError, normalizeRecoveryCode } from "@/lib/recovery";

type RestoreError =
  | { kind: "invalid" | "exists" | "network" | "generic" }
  | { kind: "rate"; until: number | null };

/** Recovery-code input + Restore button, shared by the full-page locked
 *  screen and the Settings page. On success it reloads the page so every
 *  provider refetches against the re-attached data.
 *
 *  The server's 400 text is deliberately uninformative and the 409 text is
 *  not user-facing copy, so both are replaced by translated messages here
 *  rather than echoed. A 429 starts a countdown from Retry-After and keeps
 *  the button disabled until it reaches zero. */
export default function RestoreForm({ inputId }: { inputId: string }) {
  const { t } = useI18n();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<RestoreError | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const until = error?.kind === "rate" ? error.until : null;
  const remaining = until !== null ? Math.max(0, Math.ceil((until - now) / 1000)) : 0;

  useEffect(() => {
    if (until === null) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [until]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const normalized = normalizeRecoveryCode(code);
    if (!normalized || busy || remaining > 0) return;
    setBusy(true);
    setError(null);
    try {
      await api.restoreRecoveryCode(normalized);
      setDone(true);
      window.location.reload();
    } catch (err) {
      if (err instanceof RateLimitError) {
        setError({
          kind: "rate",
          until: err.retryAfter !== null ? Date.now() + err.retryAfter * 1000 : null,
        });
      } else if (err instanceof ApiError && err.status === 400) {
        setError({ kind: "invalid" });
      } else if (err instanceof ApiError && err.status === 409) {
        setError({ kind: "exists" });
      } else if (isNetworkError(err)) {
        setError({ kind: "network" });
      } else {
        setError({ kind: "generic" });
      }
      setBusy(false);
    }
  }

  let message: string | null = null;
  if (error) {
    switch (error.kind) {
      case "invalid":
        message = t("rec.restore.invalid");
        break;
      case "exists":
        message = t("rec.restore.exists");
        break;
      case "network":
        message = t("rec.err.network");
        break;
      case "rate":
        message =
          error.until === null
            ? t("rec.restore.rateLimitedNoTime")
            : remaining > 0
              ? t("rec.restore.rateLimited", { time: fmtCountdown(remaining) })
              : null;
        break;
      default:
        message = t("rec.err.generic");
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div>
        <label className="label" htmlFor={inputId}>
          {t("rec.restore.label")}
        </label>
        <input
          id={inputId}
          type="text"
          className="input font-mono"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder={t("rec.restore.placeholder")}
          autoComplete="off"
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
          disabled={busy || done}
        />
      </div>
      {message ? (
        <p role="alert" className="banner-error">
          {message}
        </p>
      ) : null}
      {done ? <p className="banner-info">{t("rec.restore.done")}</p> : null}
      <button
        type="submit"
        className="btn-primary"
        disabled={busy || done || remaining > 0 || !normalizeRecoveryCode(code)}
      >
        {busy || done ? t("rec.restore.working") : t("rec.restore.button")}
      </button>
    </form>
  );
}
