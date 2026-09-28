/** Terms-of-use text (/terms), verbatim from the architect's terms-v1.md -
 *  do not rephrase, shorten or "improve" any sentence here. Structured
 *  rather than one Markdown blob so the page renders with the app's own
 *  typography (see pages/terms.tsx) instead of through components/Markdown,
 *  whose flushPara joins lines with a single space - fine for a generated
 *  report, but this text's paragraphs are already one sentence-run each, so
 *  plain data is simpler than round-tripping through Markdown syntax.
 *
 *  Bumping the version: change config.TERMS_VERSION on the backend (single
 *  source of truth for what "current" means) and update this text plus
 *  versionLine/effectiveDate below to match. See README "Terms of use". */
import type { Language } from "./i18n";

export interface TermsSection {
  heading: string;
  paragraphs: string[];
  list?: string[];
}

export interface TermsDoc {
  title: string;
  /** The verbatim "Wersja N · obowiązuje od ..." / "Version N · effective ..." line. */
  versionLine: string;
  sections: TermsSection[];
}

export const TERMS: Record<Language, TermsDoc> = {
  pl: {
    title: "Zasady korzystania z MyFinance",
    versionLine: "Wersja 1 · obowiązuje od 28 września 2026 r.",
    sections: [
      {
        heading: "1. Czym jest MyFinance",
        paragraphs: [
          "MyFinance to narzędzie do samodzielnego śledzenia własnych finansów: przychodów, wydatków, majątku i postępów w oszczędzaniu. Wszystkie dane wprowadzasz Ty, a wyniki są obliczeniami wykonanymi na ich podstawie.",
        ],
      },
      {
        heading: "2. To nie jest doradztwo",
        paragraphs: [
          "MyFinance nie świadczy usług doradztwa inwestycyjnego, podatkowego, prawnego ani finansowego i nie zastępuje takich usług. Żadna treść w aplikacji — w tym obliczenia, wykresy, „następne kroki”, podsumowania i oceny portfela — nie stanowi rekomendacji inwestycyjnej, porady podatkowej ani porady prawnej, w szczególności w rozumieniu przepisów o obrocie instrumentami finansowymi.",
        ],
      },
      {
        heading: "3. Decyzje podejmujesz Ty",
        paragraphs: [
          "Wszelkie decyzje finansowe, inwestycyjne i podatkowe podejmujesz samodzielnie, na własną odpowiedzialność i na podstawie własnej wiedzy. Przed ważną decyzją skonsultuj się z uprawnionym specjalistą, np.:",
        ],
        list: [
          "doradcą inwestycyjnym posiadającym licencję Komisji Nadzoru Finansowego (KNF),",
          "doradcą podatkowym wpisanym na listę Krajowej Izby Doradców Podatkowych (KIDP),",
          "radcą prawnym lub adwokatem.",
        ],
      },
      {
        heading: "4. Obliczenia podatkowe i składkowe to szacunki",
        paragraphs: [
          "Wyliczenia PIT, ZUS, składki zdrowotnej, VAT oraz limitów (IKE, IKZE, OKI, PPK) opierają się na przepisach obowiązujących w danym roku, w uproszczonej postaci, i mogą różnić się od rzeczywistych rozliczeń. Przepisy często się zmieniają. Zawsze weryfikuj wyniki z księgowym, pracodawcą, ZUS lub urzędem skarbowym.",
        ],
      },
      {
        heading: "5. Prognozy nie są gwarancją",
        paragraphs: [
          "Prognozy (m.in. emerytalne, FIRE i projekcje portfela) opierają się na założeniach dotyczących stóp zwrotu i inflacji. Rzeczywiste wyniki będą inne. Inwestowanie wiąże się z ryzykiem utraty części lub całości kapitału.",
        ],
      },
      {
        heading: "6. Treści generowane przez sztuczną inteligencję",
        paragraphs: [
          "Część tekstów w zakładce Analizy tworzy model językowy na podstawie Twoich liczb. Mogą one zawierać błędy; liczby, których nie udało się zweryfikować w Twoich danych, są oznaczane. Traktuj te treści jako materiał do przemyślenia, nie jako poradę.",
        ],
      },
      {
        heading: "7. Ceny i kursy",
        paragraphs: [
          "Ceny metali szlachetnych i kryptowalut oraz kursy walut pochodzą z publicznych serwisów i mogą być opóźnione lub chwilowo niedostępne — wtedy aplikacja używa wartości zapasowych. Nie służą one do zawierania transakcji.",
        ],
      },
      {
        heading: "8. Twoje dane",
        paragraphs: [
          "Twoje dane są przechowywane w bazie tej instalacji MyFinance. Do serwisów z cenami wysyłane są wyłącznie symbole (np. „XAU”, „bitcoin”), bez Twoich danych. Teksty w zakładce Analizy generuje model językowy skonfigurowany przez administratora tej instalacji.",
        ],
      },
      {
        heading: "9. Odpowiedzialność",
        paragraphs: [
          "Aplikacja jest udostępniana w obecnej postaci („tak jak jest”), bez gwarancji poprawności, kompletności ani przydatności do określonego celu. W najszerszym zakresie dopuszczalnym przez prawo twórcy i administrator aplikacji nie ponoszą odpowiedzialności za decyzje podjęte na podstawie treści z aplikacji ani za ich skutki.",
        ],
      },
      {
        heading: "10. Zmiany zasad",
        paragraphs: [
          "Zasady mogą się zmieniać. O nowej wersji poinformujemy przy kolejnym wejściu do aplikacji i poprosimy o jej ponowną akceptację.",
        ],
      },
    ],
  },
  en: {
    title: "MyFinance terms of use",
    versionLine: "Version 1 · effective 28 September 2026",
    sections: [
      {
        heading: "1. What MyFinance is",
        paragraphs: [
          "MyFinance is a tool for tracking your own finances yourself: income, spending, assets and progress in saving. You enter all the data, and the results are calculations made from it.",
        ],
      },
      {
        heading: "2. This is not advice",
        paragraphs: [
          "MyFinance does not provide investment, tax, legal or financial advisory services and does not replace them. Nothing in the app — including calculations, charts, \"next steps\", summaries and portfolio assessments — is an investment recommendation, tax advice or legal advice, in particular within the meaning of the laws on trading in financial instruments.",
        ],
      },
      {
        heading: "3. You make the decisions",
        paragraphs: [
          "You make every financial, investment and tax decision yourself, at your own responsibility and based on your own knowledge. Before an important decision, consult a qualified professional, for example:",
        ],
        list: [
          "an investment adviser licensed by the Polish Financial Supervision Authority (KNF),",
          "a tax adviser registered with the National Chamber of Tax Advisers (KIDP),",
          "a legal counsel (radca prawny) or attorney (adwokat).",
        ],
      },
      {
        heading: "4. Tax and contribution figures are estimates",
        paragraphs: [
          "Figures for PIT, ZUS, the health contribution, VAT and limits (IKE, IKZE, OKI, PPK) are based on the rules of the given year in simplified form and may differ from actual settlements. The rules change often. Always check the results with your accountant, employer, ZUS or tax office.",
        ],
      },
      {
        heading: "5. Projections are not guarantees",
        paragraphs: [
          "Projections (including retirement, FIRE and portfolio projections) rest on assumptions about returns and inflation. Actual results will differ. Investing carries the risk of losing part or all of the capital.",
        ],
      },
      {
        heading: "6. AI-generated content",
        paragraphs: [
          "Some texts in the Insights tab are written by a language model from your numbers. They may contain errors; numbers that could not be checked against your data are marked. Treat them as material to think about, not as advice.",
        ],
      },
      {
        heading: "7. Prices and exchange rates",
        paragraphs: [
          "Precious-metal and cryptocurrency prices and exchange rates come from public services and may be delayed or temporarily unavailable — the app then uses fallback values. They are not meant for trading.",
        ],
      },
      {
        heading: "8. Your data",
        paragraphs: [
          "Your data is stored in the database of this MyFinance installation. Price services receive only symbols (e.g. \"XAU\", \"bitcoin\"), never your data. Texts in the Insights tab are generated by a language model configured by the administrator of this installation.",
        ],
      },
      {
        heading: "9. Liability",
        paragraphs: [
          "The app is provided \"as is\", without any warranty of correctness, completeness or fitness for a particular purpose. To the fullest extent permitted by law, its authors and administrator are not liable for decisions made on the basis of the app's content or for their consequences.",
        ],
      },
      {
        heading: "10. Changes",
        paragraphs: [
          "These terms may change. We will tell you about a new version the next time you open the app and ask you to accept it again.",
        ],
      },
    ],
  },
};
