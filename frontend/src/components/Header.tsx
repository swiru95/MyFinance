import Link from "next/link";
import { useRouter } from "next/router";
import { useI18n } from "@/lib/i18n";

const links = [
  { href: "/", key: "nav.dashboard" },
  { href: "/positions", key: "nav.positions" },
  { href: "/expenses", key: "nav.expenses" },
  { href: "/monthly", key: "nav.monthly" },
  { href: "/report", key: "nav.report" },
  { href: "/settings", key: "nav.settings" },
];

export default function Header() {
  const pathname = useRouter().pathname;
  const { t } = useI18n();
  return (
    <header className="sticky top-0 z-10 border-b border-slate-200 dark:border-slate-800 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" className="flex items-center gap-2 text-lg font-semibold text-slate-900 dark:text-slate-50">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-white">
            ₣
          </span>
          {t("app.name")}
        </Link>
        <nav className="flex items-center gap-1">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                pathname === l.href
                  ? "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100"
                  : "text-slate-600 hover:bg-slate-100 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              {t(l.key)}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
