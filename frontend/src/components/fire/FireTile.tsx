import Link from "next/link";
import { fmtNum } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { fireNeedsSetup } from "@/lib/fireTypes";
import type { FireResponse } from "@/lib/fireTypes";

interface Props {
  data: FireResponse | null;
}

/** Compact dashboard card: progress toward FI, or a prompt to set up the
 *  one input the whole /fire page needs before it can compute anything. */
export default function FireTile({ data }: Props) {
  const { t, locale } = useI18n();

  return (
    <Link
      href="/fire"
      className="card block transition hover:border-brand-300 dark:hover:border-brand-700"
    >
      <p className="text-sm muted">{t("fire.tile.title")}</p>
      {data == null ? (
        <p className="mt-1 text-2xl font-semibold subtle">—</p>
      ) : fireNeedsSetup(data) ? (
        <p className="mt-1 text-lg font-semibold">{t("fire.tile.setup")}</p>
      ) : (
        <>
          <p className="mt-1 text-3xl font-semibold tabular-nums">
            {data.result.progress != null
              ? `${fmtNum(data.result.progress * 100, 0, locale)}%`
              : "—"}
          </p>
          <p className="mt-1 text-xs subtle">
            {t("fire.tile.fiAt", {
              age: fmtNum(data.result.targets_age, 0, locale),
            })}
          </p>
        </>
      )}
    </Link>
  );
}
