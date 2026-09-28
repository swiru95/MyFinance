import type { ReactNode } from "react";
import { useStoredBool } from "@/lib/useStoredBool";

interface Props {
  title: string;
  /** localStorage key backing the open/closed state - see useStoredBool. */
  storageKey: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

/** A collapsed-by-default section whose open/closed state is remembered per
 *  browser (round 2's progressive-disclosure pattern: Expenses' "Show
 *  analysis", FIRE's "Details" and "Advanced settings"). Same ▲/▼ toggle
 *  style as components/fire/SettingsCard's own open/close button, so the
 *  two disclosure patterns on FIRE read as one idiom rather than two. */
export default function Disclosure({ title, storageKey, defaultOpen = false, children }: Props) {
  const [open, setOpen] = useStoredBool(storageKey, defaultOpen);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center justify-between rounded-lg border border-slate-200 px-4 py-3 text-left transition hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/60"
      >
        <span className="text-sm font-semibold">{title}</span>
        <span className="subtle">{open ? "▲" : "▼"}</span>
      </button>
      {open && <div className="mt-4 space-y-6">{children}</div>}
    </div>
  );
}
