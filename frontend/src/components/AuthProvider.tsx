import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import {
  AuthContext,
  fetchAuthConfig,
  initMsal,
  signInRedirect,
  signOutRedirect,
  takeReturnPath,
  toUser,
} from "@/lib/auth";
import type { AuthUser } from "@/lib/auth";
import { setAuthErrorHandler, setTokenProvider } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

type Phase = "loading" | "anonymous" | "signed-in" | "disabled" | "error";

/** Gates the application on an Entra sign-in.
 *
 *  Nothing below this renders until we know whether authentication is even
 *  configured, because rendering the app first would fire a page's worth of
 *  API calls without a token and paint a screen of 401s.
 */
export default function AuthProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const { t } = useI18n();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const config = await fetchAuthConfig();
        if (cancelled) return;
        if (!config.enabled) {
          // The backend has no tenant configured, so it is not checking tokens
          // either. Asking the user to sign in would gate a door with no wall.
          setPhase("disabled");
          return;
        }
        // api.ts asks for a token per request; it has no access to MSAL itself.
        setTokenProvider(getAccessToken);
        setAuthErrorHandler((status) => {
          setError(status === 403 ? null : t("auth.expired"));
          setPhase("anonymous");
        });
        const account = await initMsal(config);
        if (cancelled) return;
        if (account) {
          setUser(toUser(account));
          setPhase("signed-in");
          const back = takeReturnPath();
          if (back) {
            void router.replace(back);
          }
        } else {
          setPhase("anonymous");
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setPhase("error");
      }
    })();
    return () => {
      cancelled = true;
    };
    // Runs once: the router identity is stable enough and re-running would
    // restart the redirect handler.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const signIn = useCallback(() => signInRedirect(), []);
  const signOut = useCallback(() => signOutRedirect(), []);

  const value = useMemo(
    () => ({
      enabled: phase !== "disabled",
      ready: phase === "signed-in" || phase === "disabled",
      user,
      error,
      signIn,
      signOut,
    }),
    [phase, user, error, signIn, signOut]
  );

  return (
    <AuthContext.Provider value={value}>
      {phase === "loading" ? (
        <Splash />
      ) : phase === "anonymous" || phase === "error" ? (
        <SignIn onSignIn={signIn} error={error} />
      ) : (
        children
      )}
    </AuthContext.Provider>
  );
}

function Splash() {
  return (
    <div className="grid min-h-screen place-items-center bg-slate-50 dark:bg-slate-950">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600 dark:border-slate-700 dark:border-t-brand-400" />
    </div>
  );
}

function SignIn({
  onSignIn,
  error,
}: {
  onSignIn: () => void;
  error: string | null;
}) {
  const { t } = useI18n();
  return (
    <div className="grid min-h-screen place-items-center bg-slate-50 px-4 dark:bg-slate-950">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <span className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-brand-600 text-2xl text-white">
          ₣
        </span>
        <h1 className="mt-5 text-xl font-semibold text-slate-900 dark:text-slate-50">
          {t("app.name")}
        </h1>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          {t("auth.prompt")}
        </p>
        {error ? (
          <p className="mt-4 rounded-lg bg-rose-50 px-3 py-2 text-left text-xs text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
            {error}
          </p>
        ) : null}
        <button
          onClick={onSignIn}
          className="mt-6 w-full rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 dark:focus:ring-offset-slate-900"
        >
          {t("auth.signIn")}
        </button>
      </div>
    </div>
  );
}
