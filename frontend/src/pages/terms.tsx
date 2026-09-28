import { useI18n } from "@/lib/i18n";
import { TERMS } from "@/lib/terms";

/** Full terms text (verbatim, see lib/terms.ts). Reachable without any
 *  feature toggle and not in the main nav - the footer and the acceptance
 *  modal both link here. Must stay readable even while the acceptance modal
 *  is pending elsewhere in the app (see TermsGate), so this page renders on
 *  its own with no dependency on acceptance state. */
export default function TermsPage() {
  const { lang } = useI18n();
  const doc = TERMS[lang];

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-50">
          {doc.title}
        </h1>
        <p className="mt-1 text-sm muted">{doc.versionLine}</p>
      </header>

      <div className="card space-y-6">
        {doc.sections.map((section) => (
          <section key={section.heading}>
            <h2 className="text-base font-semibold text-slate-900 dark:text-slate-50">
              {section.heading}
            </h2>
            {section.paragraphs.map((p) => (
              <p key={p} className="mt-2 text-sm leading-relaxed muted">
                {p}
              </p>
            ))}
            {section.list ? (
              <ul className="ml-5 mt-2 list-disc space-y-1.5">
                {section.list.map((item) => (
                  <li key={item} className="text-sm leading-relaxed muted">
                    {item}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
        ))}
      </div>
    </div>
  );
}
