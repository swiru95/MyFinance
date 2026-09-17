import { useEffect, useState } from "react";
import { applyTheme, readTheme, resolveTheme, storeTheme, THEMES } from "@/lib/theme";
import type { Theme } from "@/lib/theme";
import { useI18n } from "@/lib/i18n";

const ICONS: Record<Theme, string> = {
  light: "☀️",
  dark: "🌙",
  system: "💻",
};

const LABEL_KEYS: Record<Theme, string> = {
  light: "set.themeLight",
  dark: "set.themeDark",
  system: "set.themeSystem",
};

export default function ThemeToggle() {
  const { t } = useI18n();
  const [theme, setTheme] = useState<Theme>("system");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setTheme(readTheme());
    setMounted(true);
  }, []);

  // While on "system", follow the OS as it changes without a reload.
  useEffect(() => {
    if (!mounted || theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme, mounted]);

  function choose(next: Theme) {
    setTheme(next);
    storeTheme(next);
    applyTheme(next);
  }

  return (
    <div>
      <div className="flex gap-2" role="group" aria-label={t("set.appearance")}>
        {THEMES.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => choose(option)}
            aria-pressed={mounted && theme === option}
            className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium transition ${
              mounted && theme === option
                ? "border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100"
                : "border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            {ICONS[option]} {t(LABEL_KEYS[option])}
          </button>
        ))}
      </div>
      <p className="mt-1 text-xs muted">
        {mounted && theme === "system"
          ? t("set.followingSystem", { mode: resolveTheme("system") })
          : t("set.savedInBrowser")}
      </p>
    </div>
  );
}
