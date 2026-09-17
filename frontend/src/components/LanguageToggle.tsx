import { LANGUAGES, LANGUAGE_NAMES, useI18n } from "@/lib/i18n";

export default function LanguageToggle() {
  const { lang, setLang, t } = useI18n();

  return (
    <div>
      <div className="flex gap-2" role="group" aria-label={t("set.language")}>
        {LANGUAGES.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setLang(option)}
            aria-pressed={lang === option}
            className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium transition ${
              lang === option
                ? "border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100"
                : "border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            {LANGUAGE_NAMES[option]}
          </button>
        ))}
      </div>
      <p className="mt-1 text-xs muted">{t("set.languageHint")}</p>
    </div>
  );
}
