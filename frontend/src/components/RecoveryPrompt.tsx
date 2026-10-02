import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { RecoveryStatus } from "@/lib/types";
import { useSettings } from "./SettingsProvider";
import RecoveryCodeFlow from "./RecoveryCodeFlow";

/** Blocks the app behind a "save your recovery code" modal until a code has
 *  been created AND confirmed (typed back).
 *
 *  Mounted inside TermsGate's children (see _app.tsx). TermsGate renders its
 *  children alongside its own acceptance modal rather than instead of it, so
 *  this component waits for settings to load and the current terms to be
 *  accepted before it even asks for the status - the two modals never stack.
 *
 *  "Not now" hides it until the next full page load; that flag is component
 *  state on purpose (no storage), so the prompt returns on reload. If the
 *  page is reloaded after a code was created but before it was confirmed,
 *  the code is gone for good: status says configured && !confirmed, and the
 *  modal restarts with a note that creating a new code replaces it. */
export default function RecoveryPrompt() {
  const { settings } = useSettings();
  const { t } = useI18n();
  const [status, setStatus] = useState<RecoveryStatus | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  const terms = settings?.terms;
  const termsAccepted = !!terms && terms.accepted_version === terms.current_version;

  useEffect(() => {
    if (!termsAccepted) return;
    let cancelled = false;
    api
      .recoveryStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        // No status means no prompt; the Settings page offers the same flow.
      });
    return () => {
      cancelled = true;
    };
  }, [termsAccepted]);

  const show =
    termsAccepted && !dismissed && !!status && !status.locked && (!status.configured || !status.confirmed);

  // Body scroll lock + initial focus while the modal is up.
  useEffect(() => {
    if (!show) return;
    const first = dialogRef.current?.querySelector<HTMLElement>("button:not([disabled])");
    first?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [show]);

  // Focus trap; Escape is swallowed, since closing is only via "Not now".
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
      const active = document.activeElement;
      // The content swaps as the flow advances, which can leave focus on
      // <body> or on the programmatically focused code box; pull it back in.
      if (!container.contains(active) || active === container.querySelector('[tabindex="-1"]')) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
      } else if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [show]);

  if (!show || !status) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/60 px-4 py-6">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="recovery-modal-title"
        className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-lg dark:border-slate-800 dark:bg-slate-900"
      >
        <h2
          id="recovery-modal-title"
          className="text-lg font-semibold text-slate-900 dark:text-slate-50"
        >
          {t("rec.prompt.title")}
        </h2>
        <div className="mt-3">
          <RecoveryCodeFlow
            startLabel={t("rec.flow.start")}
            intro={
              <div className="space-y-2 text-sm muted">
                <p>{t("rec.prompt.body")}</p>
                <p>{t("rec.prompt.body2")}</p>
                {status.configured && !status.confirmed ? (
                  <p className="rounded-lg bg-amber-50 px-3 py-2 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                    {t("rec.prompt.unconfirmed")}
                  </p>
                ) : null}
              </div>
            }
            onConfirmed={(s) => setStatus(s)}
            onDismiss={() => setDismissed(true)}
            dismissWhileIdle
          />
        </div>
      </div>
    </div>
  );
}
