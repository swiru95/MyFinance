import type { AppProps } from "next/app";
import Head from "next/head";
import "../styles/globals.css";
import Header from "@/components/Header";
import AuthProvider from "@/components/AuthProvider";
import I18nProvider from "@/components/I18nProvider";
import SettingsProvider from "@/components/SettingsProvider";
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
        <SettingsProvider>
          <Header />
          <main className="mx-auto max-w-6xl px-4 py-8">
            <Component {...pageProps} />
          </main>
        </SettingsProvider>
      </AuthProvider>
    </I18nProvider>
  );
}
