import Link from "next/link";
import { useI18n } from "@/lib/i18n";

interface Props {
  /** i18n key for the one-line description of what this page needs. */
  descriptionKey: string;
}

/** Shown instead of a page's own content when the feature it belongs to is
 *  switched off - reached by URL (a stale bookmark, a typed address) since
 *  Header already hides the nav link. Callers must not fetch any data before
 *  checking the flag and rendering this - see pages/positions.tsx etc. */
export default function FeatureOffCard({ descriptionKey }: Props) {
  const { t } = useI18n();
  return (
    <div className="mx-auto mt-12 max-w-md space-y-3 card text-center">
      <p className="text-lg font-semibold">{t("feat.off.title")}</p>
      <p className="text-sm muted">{t(descriptionKey)}</p>
      <Link href="/settings" className="btn-primary inline-block">
        {t("feat.off.goSettings")}
      </Link>
    </div>
  );
}
