import type { AppProps } from "next/app";
import Head from "next/head";
import "../styles/globals.css";
import Header from "@/components/Header";
import I18nProvider from "@/components/I18nProvider";
import SettingsProvider from "@/components/SettingsProvider";

export default function App({ Component, pageProps }: AppProps) {
  return (
    <>
      <Head>
        <title>MyFinance — Budget & Portfolio Tracker</title>
        <meta
          name="description"
          content="Track cash, gold, stocks, funds, bonds, watches, crypto and savings."
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <I18nProvider>
        <SettingsProvider>
          <Header />
          <main className="mx-auto max-w-6xl px-4 py-8">
            <Component {...pageProps} />
          </main>
        </SettingsProvider>
      </I18nProvider>
    </>
  );
}
