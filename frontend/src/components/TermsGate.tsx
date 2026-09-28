import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { useSettings } from "./SettingsProvider";
import { api } from "@/lib/api";

/** Blocks the app behind a modal until the current terms version is
 *  accepted. Lives inside AuthProvider/SettingsProvider (see _app.tsx), so it
 *  never mounts on the sign-in screen and always has settings to read.
 *
 *  The /terms page itself is exempted (`onTermsPage`) so the link inside the
 *  modal can open in the same tab without the modal covering the very text
 *  it is asking the user to read - leaving that route hides the modal, and
 *  since "pending" is recomputed from settings.terms on every render, it
 *  reappears exactly if acceptance is still outstanding. */
export default function TermsGate({ children }: { children: React.ReactNode }) {
  const { settings, apply } = useSettings();
  const { t } = useI18n();
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const checkboxRef = useRef<HTMLInputElement>(null);

  const terms = settings?.terms;
  const onTermsPage = router.pathname === "/terms";
  // Undefined until settings has loaded - showing this on a guess would
  // flash it for a wallet that has already accepted.
  const pending = !!terms && terms.accepted_version !== terms.current_version;
  const show = pending && !onTermsPage;

  // Body scroll lock + initial focus while the modal is up.
  useEffect(() => {
    if (!show) return;
    checkboxRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [show]);

  // Focus trap; Escape is swallowed rather than closing anything, since
  // acceptance is required and there is nothing to cancel back to.
  useEffect(() => {
    if (!show) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      if (e.key !== "Tab") return;
      const container = dialogRef.current;
      if (!container) return;
      const focusable = container.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [show]);

  async function accept() {
    if (!terms || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await api.acceptTerms(terms.current_version);
      apply(updated);
    } catch {
      setError(t("common.failedSave"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      {children}
      {show ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/60 px-4">
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="terms-modal-title"
            className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-lg dark:border-slate-800 dark:bg-slate-900"
          >
            <h2
              id="terms-modal-title"
              className="text-lg font-semibold text-slate-900 dark:text-slate-50"
            >
              {t("termsModal.title")}
            </h2>
            <p className="mt-2 text-sm muted">{t("termsModal.body")}</p>
            <Link
              href="/terms"
              className="mt-3 inline-block text-sm font-medium text-brand-600 underline hover:text-brand-700 dark:text-brand-400"
            >
              {t("termsModal.link")}
            </Link>
            <label className="mt-4 flex items-start gap-2 text-sm text-slate-700 dark:text-slate-200">
              <input
                ref={checkboxRef}
                type="checkbox"
                checked={checked}
                onChange={(e) => setChecked(e.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-brand-600 focus:ring-2 focus:ring-brand-500/40 dark:border-slate-600"
              />
              <span>{t("termsModal.checkbox")}</span>
            </label>
            {error ? (
              <p className="mt-3 text-xs text-rose-600 dark:text-rose-400">{error}</p>
            ) : null}
            <button
              type="button"
              onClick={accept}
              disabled={!checked || submitting}
              className="btn-primary mt-5 w-full"
            >
              {t("termsModal.button")}
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}
