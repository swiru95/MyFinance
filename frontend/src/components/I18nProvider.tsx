import { useCallback, useEffect, useMemo, useState } from "react";
import {
  I18nContext,
  INTL_LOCALE,
  readLanguage,
  storeLanguage,
  translate,
} from "@/lib/i18n";
import type { Language } from "@/lib/i18n";

export default function I18nProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  // Server-renders as "en" and switches on mount - the stored choice is only
  // readable in the browser.
  const [lang, setLangState] = useState<Language>("en");

  useEffect(() => {
    setLangState(readLanguage());
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next: Language) => {
    setLangState(next);
    storeLanguage(next);
  }, []);

  const value = useMemo(
    () => ({
      lang,
      locale: INTL_LOCALE[lang],
      setLang,
      t: (key: string, vars?: Record<string, string | number>) =>
        translate(lang, key, vars),
    }),
    [lang, setLang]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
