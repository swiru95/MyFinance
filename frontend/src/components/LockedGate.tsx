import { useEffect, useState } from "react";
import { api, setLockedHandler } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import RestoreForm from "./RestoreForm";

type Phase = "loading" | "locked" | "open";

/** Replaces the whole app with a recovery screen when this sign-in cannot
 *  unlock the account's data (backend 423 / `locked: true`).
 *
 *  Mounted inside AuthProvider (it needs a token) but outside
 *  SettingsProvider, whose first call would 423 for a locked account.
 *  Children are held back until the status is known so nothing flashes or
 *  fires data requests that are guaranteed to fail.
 *
 *  Fails open: if the status call itself errors (old backend, network blip,
 *  expired session - AuthProvider handles that one) the app renders as
 *  before, and a later 423 from any data call still flips this screen via
 *  setLockedHandler. There is deliberately no way to dismiss it. */
export default function LockedGate({ children }: { children: React.ReactNode }) {
  const [phase, setPhase] = useState<Phase>("loading");

  useEffect(() => {
    let cancelled = false;
    setLockedHandler(() => setPhase("locked"));
    api
      .recoveryStatus()
      .then((status) => {
        if (!cancelled) setPhase((p) => (status.locked || p === "locked" ? "locked" : "open"));
      })
      .catch(() => {
        if (!cancelled) setPhase((p) => (p === "locked" ? p : "open"));
      });
    return () => {
      cancelled = true;
      setLockedHandler(null);
    };
  }, []);

  if (phase === "loading") {
    return (
      <div className="grid min-h-screen place-items-center bg-slate-50 dark:bg-slate-950">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600 dark:border-slate-700 dark:border-t-brand-400" />
      </div>
    );
  }
  if (phase === "locked") return <LockedScreen />;
  return <>{children}</>;
}

function LockedScreen() {
  const { t } = useI18n();
  const { enabled, signOut } = useAuth();
  return (
    <div className="grid min-h-screen place-items-center bg-slate-50 px-4 py-8 dark:bg-slate-950">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <span
          aria-hidden="true"
          className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600 text-2xl text-white"
        >
          ₣
        </span>
        <h1 className="mt-5 text-xl font-semibold text-slate-900 dark:text-slate-50">
          {t("rec.locked.title")}
        </h1>
        <p className="mt-2 text-sm muted">{t("rec.locked.body")}</p>
        <div className="mt-6">
          <RestoreForm inputId="locked-recovery-code" />
        </div>
        {enabled ? (
          <button type="button" onClick={signOut} className="btn-ghost mt-4">
            {t("rec.locked.signOut")}
          </button>
        ) : null}
      </div>
    </div>
  );
}
