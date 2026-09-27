import Link from "next/link";
import { useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { insightsApi } from "@/lib/insightsApi";
import type { LadderResponse } from "@/lib/insightsTypes";
import { RUNG_TITLE_KEY } from "./ladderCopy";

/** Compact dashboard card mirroring FireTile: the first todo rung of the
 *  ladder, or a spent/empty state, linking to the Next steps tab of
 *  /report. Fetches its own data so pages/index.tsx does not need to know
 *  anything about insights beyond rendering this tile. */
export default function NextStepTile() {
  const { t } = useI18n();
  const [ladder, setLadder] = useState<LadderResponse | null>(null);

  useEffect(() => {
    let alive = true;
    insightsApi
      .ladder()
      .then((d) => {
        if (alive) setLadder(d);
      })
      .catch(() => {
        // The tile just shows a dash when insights are unavailable - the
        // /report page itself surfaces the real error.
      });
    return () => {
      alive = false;
    };
  }, []);

  const next = ladder?.rungs
    .filter((r) => r.status === "todo")
    .sort((a, b) => a.order - b.order)[0];

  return (
    <Link
      href="/report"
      className="card block transition hover:border-brand-300 dark:hover:border-brand-700"
    >
      <p className="text-sm muted">{t("ins.tile.title")}</p>
      {ladder == null ? (
        <p className="mt-1 text-2xl font-semibold subtle">—</p>
      ) : next == null ? (
        <p className="mt-1 text-lg font-semibold">{t("ins.tile.allDone")}</p>
      ) : (
        <p className="mt-1 text-lg font-semibold">{t(RUNG_TITLE_KEY[next.key])}</p>
      )}
    </Link>
  );
}
