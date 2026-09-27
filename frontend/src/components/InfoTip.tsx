import { useEffect, useId, useRef, useState } from "react";

interface Props {
  /** The explanation shown in the popover - already translated. */
  text: string;
  /** Accessible name for the button, e.g. the term itself ("KUP"). Falls
   *  back to a generic "More information" label when omitted. */
  label?: string;
}

/** Small ⓘ button that opens a short plain-language explanation on click or
 *  tap - a touch-accessible replacement for a `title` attribute, which never
 *  fires on mobile. Closes on outside click, Escape (returning focus to the
 *  button) or a second click/tap, and clamps its width so it never runs off
 *  a 390px viewport regardless of which edge the button sits near. */
export default function InfoTip({ text, label }: Props) {
  const [open, setOpen] = useState(false);
  const [align, setAlign] = useState<"left" | "right">("left");
  const containerRef = useRef<HTMLSpanElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popoverId = useId();

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent | TouchEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function toggle() {
    if (!open && buttonRef.current) {
      // Anchor the popover to whichever side of the button has more room,
      // so it stays on screen instead of overflowing a narrow viewport.
      const rect = buttonRef.current.getBoundingClientRect();
      setAlign(rect.left > window.innerWidth / 2 ? "right" : "left");
    }
    setOpen((o) => !o);
  }

  return (
    <span ref={containerRef} className="relative inline-flex align-middle">
      <button
        ref={buttonRef}
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-describedby={open ? popoverId : undefined}
        aria-label={label ? `${label}` : undefined}
        className="ml-1 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold leading-none text-slate-500 ring-1 ring-inset ring-slate-300 transition hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-500/50 dark:text-slate-400 dark:ring-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
      >
        i
      </button>
      {open && (
        <span
          role="tooltip"
          id={popoverId}
          className={`absolute top-full z-30 mt-1.5 w-64 max-w-[calc(100vw-2rem)] rounded-lg border border-slate-200 bg-white p-2.5 text-xs font-normal leading-snug text-slate-700 shadow-lg dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          {text}
        </span>
      )}
    </span>
  );
}
