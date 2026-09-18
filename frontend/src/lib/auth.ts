import {
  InteractionRequiredAuthError,
  PublicClientApplication,
} from "@azure/msal-browser";
import type {
  AccountInfo,
  Configuration,
  RedirectRequest,
} from "@azure/msal-browser";
import { createContext, useContext } from "react";

/** What GET /api/auth/config answers. */
export interface AuthConfig {
  enabled: boolean;
  tenant_id?: string;
  client_id?: string;
  authority?: string;
  scopes?: string[];
}

export interface AuthUser {
  name: string;
  username: string;
  initials: string;
}

export interface AuthValue {
  /** False when the backend has no tenant configured - the app runs open. */
  enabled: boolean;
  ready: boolean;
  user: AuthUser | null;
  error: string | null;
  signIn: () => void;
  signOut: () => void;
}

export const AuthContext = createContext<AuthValue>({
  enabled: false,
  ready: true,
  user: null,
  error: null,
  signIn: () => {},
  signOut: () => {},
});

export function useAuth(): AuthValue {
  return useContext(AuthContext);
}

/** Read the tenant and client id from the backend rather than from the bundle.
 *
 *  `next build` inlines NEXT_PUBLIC_* at build time, and these images are built
 *  once in CI and deployed by Helm, so baking them in would tie an app
 *  registration to an image tag. Neither value is a secret. */
export async function fetchAuthConfig(): Promise<AuthConfig> {
  const res = await fetch("/api/auth/config");
  if (!res.ok) {
    throw new Error(`auth config: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

let msal: PublicClientApplication | null = null;
let scopes: string[] = [];

function msalConfig(config: AuthConfig): Configuration {
  return {
    auth: {
      clientId: config.client_id!,
      authority: config.authority!,
      // The SPA is served from the same origin as the API, so the redirect URI
      // is simply wherever the app is running. Registering it in Entra under
      // the *Single-page application* platform is what enables PKCE without a
      // client secret; the "Web" platform would demand one.
      redirectUri: typeof window === "undefined" ? "/" : window.location.origin,
      postLogoutRedirectUri:
        typeof window === "undefined" ? "/" : window.location.origin,
    },
    cache: {
      // sessionStorage, not localStorage: closing the tab ends the session.
      // MSAL keeps a refresh token here, so `acquireTokenSilent` still renews
      // the access token without a redirect and without third-party cookies -
      // the usual reason people reach for localStorage does not apply.
      cacheLocation: "sessionStorage",
    },
  };
}

/** Build the MSAL client once and run the redirect handler.
 *
 *  Returns the signed-in account, or null when the user still has to sign in. */
export async function initMsal(config: AuthConfig): Promise<AccountInfo | null> {
  scopes = config.scopes ?? [];
  if (!msal) {
    msal = new PublicClientApplication(msalConfig(config));
    await msal.initialize();
  }
  // Consumes the code in the URL fragment when we have just come back from
  // Entra. Answers null on an ordinary page load.
  const result = await msal.handleRedirectPromise();
  if (result?.account) {
    msal.setActiveAccount(result.account);
    return result.account;
  }
  const existing = msal.getActiveAccount() ?? msal.getAllAccounts()[0] ?? null;
  if (existing) {
    msal.setActiveAccount(existing);
  }
  return existing;
}

/** Where the user was when they were bounced to Entra.
 *
 *  msal-browser v5 dropped `navigateToLoginRequestUrl`, so the return path is
 *  ours to remember: the redirect URI is the origin, and without this every
 *  sign-in would land on the dashboard regardless of where it started. */
const RETURN_KEY = "myfinance-auth-return";

function rememberReturnPath(): void {
  try {
    sessionStorage.setItem(
      RETURN_KEY,
      window.location.pathname + window.location.search
    );
  } catch {
    // Private mode with storage blocked. Losing the return path is survivable;
    // failing the sign-in over it is not.
  }
}

/** The remembered path, consumed. Null when there is nothing worth restoring. */
export function takeReturnPath(): string | null {
  try {
    const path = sessionStorage.getItem(RETURN_KEY);
    sessionStorage.removeItem(RETURN_KEY);
    return path && path !== "/" ? path : null;
  } catch {
    return null;
  }
}

function request(): RedirectRequest {
  return { scopes, account: msal?.getActiveAccount() ?? undefined };
}

export function signInRedirect(): void {
  rememberReturnPath();
  // No account yet, so no `account` hint - a bare scopes request.
  void msal?.loginRedirect({ scopes });
}

export function signOutRedirect(): void {
  void msal?.logoutRedirect({ account: msal.getActiveAccount() ?? undefined });
}

/** An access token for this app's own API, or null when auth is off.
 *
 *  Silent first; a redirect only when Entra says interaction is genuinely
 *  required, which is what happens once the refresh token has aged out. */
export async function getAccessToken(): Promise<string | null> {
  if (!msal || scopes.length === 0) {
    return null;
  }
  const account = msal.getActiveAccount();
  if (!account) {
    return null;
  }
  try {
    const result = await msal.acquireTokenSilent(request());
    return result.accessToken;
  } catch (err) {
    if (err instanceof InteractionRequiredAuthError) {
      rememberReturnPath();
      await msal.acquireTokenRedirect(request());
      return null;
    }
    throw err;
  }
}

/** True once a tenant is configured, so api.ts knows to attach a token. */
export function authIsEnabled(): boolean {
  return msal !== null;
}

export function toUser(account: AccountInfo): AuthUser {
  const name = account.name || account.username || "";
  const initials =
    name
      .split(/[\s@._-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]!.toUpperCase())
      .join("") || "?";
  return { name: account.name || account.username, username: account.username, initials };
}
