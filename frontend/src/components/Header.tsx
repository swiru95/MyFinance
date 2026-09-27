import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { useFeatures } from "@/lib/features";
import AccountMenu from "./AccountMenu";

/** `feature` is which advanced-feature switch gates this link, or undefined
 *  for one of the always-on base pages. Order matches the product's own
 *  priority (Dashboard, then the pages a plain user touches most), not the
 *  order features were built in. */
const links = [
  { href: "/", key: "nav.dashboard", feature: undefined },
  { href: "/positions", key: "nav.positions", feature: "portfolio" as const },
  { href: "/income", key: "nav.income", feature: undefined },
  { href: "/expenses", key: "nav.expenses", feature: undefined },
  { href: "/fire", key: "nav.fire", feature: "fire" as const },
  { href: "/report", key: "nav.report", feature: "insights" as const },
  { href: "/tax", key: "nav.tax", feature: "tax" as const },
  { href: "/settings", key: "nav.settings", feature: undefined },
];

export default function Header() {
  const pathname = useRouter().pathname;
  const { t } = useI18n();
  const features = useFeatures();
  const visible = links.filter((l) => !l.feature || features[l.feature]);
  const [menuOpen, setMenuOpen] = useState(false);
  const headerRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  // A navigation should never leave a stale menu open behind it.
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    function onDocClick(e: MouseEvent) {
      if (!headerRef.current?.contains(e.target as Node)) setMenuOpen(false);
    }
    function onEscape(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEscape);
    };
  }, [menuOpen]);

  return (
    <header
      ref={headerRef}
      className="sticky top-0 z-10 border-b border-slate-200 dark:border-slate-800 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/80"
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
        <Link href="/" className="flex shrink-0 items-center gap-2 text-lg font-semibold text-slate-900 dark:text-slate-50">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-white">
            ₣
          </span>
          {t("app.name")}
        </Link>

        {/* Desktop: the full link strip, inline. Below md it is replaced by
            the ☰ panel rather than left to scroll off-screen sideways. */}
        <nav className="hidden min-w-0 flex-1 items-center justify-end gap-1 md:flex">
          {visible.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              aria-current={pathname === l.href ? "page" : undefined}
              className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                pathname === l.href
                  ? "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100"
                  : "text-slate-600 hover:bg-slate-100 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              {t(l.key)}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-1">
          <button
            ref={menuButtonRef}
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            aria-haspopup="true"
            aria-expanded={menuOpen}
            aria-controls="mobile-nav-panel"
            aria-label={t("nav.menu")}
            className="grid h-9 w-9 place-items-center rounded-lg text-lg leading-none text-slate-600 transition hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500/40 dark:text-slate-300 dark:hover:bg-slate-800 md:hidden"
          >
            ☰
          </button>
          <AccountMenu />
        </div>
      </div>

      {/* Mobile: a full-width dropdown instead of the old horizontally
          scrolling strip, which hid most links behind a faint scrollbar. */}
      {menuOpen && (
        <div
          id="mobile-nav-panel"
          className="border-t border-slate-200 bg-white px-4 py-2 dark:border-slate-800 dark:bg-slate-900 md:hidden"
        >
          <nav className="flex flex-col gap-0.5 py-1">
            {visible.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                aria-current={pathname === l.href ? "page" : undefined}
                onClick={() => setMenuOpen(false)}
                className={`rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                  pathname === l.href
                    ? "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                }`}
              >
                {t(l.key)}
              </Link>
            ))}
          </nav>
        </div>
      )}
    </header>
  );
}
