import type { AppProps } from "next/app";
import Head from "next/head";
import "../styles/globals.css";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import AuthProvider from "@/components/AuthProvider";
import I18nProvider from "@/components/I18nProvider";
import SettingsProvider from "@/components/SettingsProvider";
import TermsGate from "@/components/TermsGate";
import LockedGate from "@/components/LockedGate";
import RecoveryPrompt from "@/components/RecoveryPrompt";
import { useI18n } from "@/lib/i18n";

/** Title and description live in their own component because they need the
 *  active language, which only exists inside the provider. */
function DocumentHead() {
  const { t } = useI18n();
  return (
    <Head>
      <title>{`${t("app.name")} — ${t("app.tagline")}`}</title>
      <meta name="description" content={t("app.description")} />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
    </Head>
  );
}

export default function App({ Component, pageProps }: AppProps) {
  return (
    <I18nProvider>
      <DocumentHead />
      {/* Outside SettingsProvider on purpose: that provider calls /api/settings
          on mount, which is a guarded endpoint. Gating first means it never
          fires without a token. */}
      <AuthProvider>
        {/* LockedGate sits outside SettingsProvider on purpose: a locked
            account answers every data call (including /api/settings) with
            423, so settings must not even start loading until the recovery
            status says the data can be opened. */}
        <LockedGate>
          <SettingsProvider>
            {/* TermsGate blocks everything below it behind an acceptance modal
                until the current terms version is accepted; being inside
                AuthProvider means it never shows on the sign-in screen.
                RecoveryPrompt waits for accepted terms itself, so the two
                modals never stack. */}
            <TermsGate>
              <Header />
              <main className="mx-auto max-w-6xl px-4 py-8">
                <Component {...pageProps} />
              </main>
              <RecoveryPrompt />
            </TermsGate>
          </SettingsProvider>
        </LockedGate>
      </AuthProvider>
      {/* Outside AuthProvider so it is visible on the sign-in screen too. */}
      <Footer />
    </I18nProvider>
  );
}
