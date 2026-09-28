import Link from "next/link";
import { useI18n } from "@/lib/i18n";

/** One-line, muted footer on every page: the "not advice" disclaimer plus a
 *  link to the full terms. Rendered from _app.tsx outside AuthProvider so it
 *  is visible on the sign-in screen too, not only once inside the app. */
export default function Footer() {
  const { t } = useI18n();
  return (
    <footer className="mx-auto max-w-6xl px-4 py-6 text-center text-xs subtle">
      {t("footer.disclaimer")}{" "}
      <Link href="/terms" className="underline hover:text-slate-600 dark:hover:text-slate-300">
        {t("footer.termsLink")}
      </Link>
    </footer>
  );
}
