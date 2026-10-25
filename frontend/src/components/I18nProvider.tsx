import { useCallback, useEffect, useMemo, useState } from "react";
import {
  I18nContext,
  INTL_LOCALE,
  readLanguage,
  storeLanguage,
  translate,
  translateData,
} from "@/lib/i18n";
import type { Language, LanguageSetting } from "@/lib/i18n";
import { resolveLanguage } from "@/lib/i18n";

export default function I18nProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  // Server-renders as English and switches on mount - the stored choice is only
  // readable in the browser.
  const [langSetting, setLangSettingState] = useState<LanguageSetting>("auto");

  useEffect(() => {
    setLangSettingState(readLanguage());
  }, []);

  const lang = useMemo(
    () => resolveLanguage(langSetting),
    [langSetting]
  );

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next: LanguageSetting) => {
    setLangSettingState(next);
    storeLanguage(next);
  }, []);

  const value = useMemo(
    () => ({
      lang,
      langSetting,
      locale: INTL_LOCALE[lang],
      setLang,
      t: (key: string, vars?: Record<string, string | number>) =>
        translate(lang, key, vars),
      td: (value: string) => translateData(lang, value),
    }),
    [lang, langSetting, setLang]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
