import Link from "next/link";
import { useRouter } from "next/router";
import { useI18n } from "@/lib/i18n";
import { useFeatures } from "@/lib/features";
import AccountMenu from "./AccountMenu";

/** `feature` is which advanced-feature switch gates this link, or undefined
 *  for one of the always-on base pages. */
const links = [
  { href: "/", key: "nav.dashboard", feature: undefined },
  { href: "/positions", key: "nav.positions", feature: "portfolio" as const },
  { href: "/expenses", key: "nav.expenses", feature: undefined },
  { href: "/income", key: "nav.income", feature: undefined },
  { href: "/fire", key: "nav.fire", feature: "fire" as const },
  { href: "/tax", key: "nav.tax", feature: "tax" as const },
  { href: "/report", key: "nav.report", feature: "insights" as const },
  { href: "/settings", key: "nav.settings", feature: undefined },
];

export default function Header() {
  const pathname = useRouter().pathname;
  const { t } = useI18n();
  const features = useFeatures();
  const visible = links.filter((l) => !l.feature || features[l.feature]);
  return (
    <header className="sticky top-0 z-10 border-b border-slate-200 dark:border-slate-800 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
        <Link href="/" className="flex shrink-0 items-center gap-2 text-lg font-semibold text-slate-900 dark:text-slate-50">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-white">
            ₣
          </span>
          {t("app.name")}
        </Link>
        <nav className="-mr-2 flex min-w-0 items-center gap-1 overflow-x-auto pr-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {visible.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                pathname === l.href
                  ? "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100"
                  : "text-slate-600 hover:bg-slate-100 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              {t(l.key)}
            </Link>
          ))}
          <AccountMenu />
        </nav>
      </div>
    </header>
  );
}
