/** Strings for the Dashboard first-run start card
 *  (components/dashboard/StartCard.tsx, round 2 spec item 6). Kept in its
 *  own file rather than lib/i18n.ts for the same reason as the other
 *  lib/strings/*.ts modules - a self-contained feature's copy does not need
 *  to live in that one long file, and a new file cannot collide with lines
 *  another agent is editing there concurrently. Merged into the main
 *  dictionaries in i18n.ts. */
export const en: Record<string, string> = {
  "start.title": "How do you earn?",
  "start.subtitle":
    "Pick the closest match — you can add more detail, or more sources, any time from Income.",
  "start.dismiss": "Skip for now",

  "start.uop.title": "Employment contract (UoP)",
  "start.uop.desc": "You get a monthly payslip from an employer.",
  "start.uop.grossLabel": "Gross monthly salary",
  "start.uop.defaultName": "Employment contract",

  "start.b2b.title": "My own business (B2B)",
  "start.b2b.desc": "You invoice clients as a sole trader (JDG).",
  "start.b2b.invoiceLabel": "Monthly invoice (net)",
  "start.b2b.defaultName": "Business",

  "start.spending.title": "I only want to track spending",
  "start.spending.desc": "Skip income for now and go straight to Expenses.",

  "start.create": "Create",
  "start.done": "Done — your income source is set up with sensible defaults. You can fine-tune it any time on Income under \"More options\".",
  "start.addFirstExpense": "Now add your first fixed cost →",
};

export const pl: Record<string, string> = {
  "start.title": "Jak zarabiasz?",
  "start.subtitle":
    "Wybierz najbliższą opcję — więcej szczegółów lub kolejne źródła możesz dodać w każdej chwili w Przychodach.",
  "start.dismiss": "Pomiń na razie",

  "start.uop.title": "Umowa o pracę (UoP)",
  "start.uop.desc": "Dostajesz miesięczny pasek wypłaty od pracodawcy.",
  "start.uop.grossLabel": "Wynagrodzenie brutto miesięcznie",
  "start.uop.defaultName": "Umowa o pracę",

  "start.b2b.title": "Własna działalność (B2B)",
  "start.b2b.desc": "Wystawiasz faktury klientom jako JDG.",
  "start.b2b.invoiceLabel": "Miesięczna kwota faktury (netto)",
  "start.b2b.defaultName": "Działalność",

  "start.spending.title": "Chcę tylko śledzić wydatki",
  "start.spending.desc": "Pomiń przychody na razie i przejdź od razu do Wydatków.",

  "start.create": "Utwórz",
  "start.done": "Gotowe — źródło przychodu jest skonfigurowane z rozsądnymi wartościami domyślnymi. Możesz je doprecyzować w każdej chwili w Przychodach, pod „Więcej opcji”.",
  "start.addFirstExpense": "Dodaj teraz pierwszy stały koszt →",
};
