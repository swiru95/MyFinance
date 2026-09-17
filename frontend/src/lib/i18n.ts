import { createContext, useContext } from "react";

export type Language = "en" | "pl";

export const LANGUAGE_KEY = "myfinance-language";
export const LANGUAGES: Language[] = ["en", "pl"];

export const LANGUAGE_NAMES: Record<Language, string> = {
  en: "English",
  pl: "Polski",
};

/** Intl locale used for number, currency and date formatting. */
export const INTL_LOCALE: Record<Language, string> = {
  en: "en-US",
  pl: "pl-PL",
};

type Dict = Record<string, string>;

const en: Dict = {
  "app.name": "MyFinance",
  "nav.dashboard": "Dashboard",
  "nav.positions": "Positions",
  "nav.expenses": "Expenses",
  "nav.monthly": "Monthly",
  "nav.settings": "Settings",

  "common.add": "Add",
  "common.edit": "Edit",
  "common.delete": "Delete",
  "common.cancel": "Cancel",
  "common.save": "Save",
  "common.saving": "Saving…",
  "common.loading": "Loading…",
  "common.notes": "Notes (optional)",
  "common.currency": "Currency",
  "common.amount": "Amount",
  "common.failedLoad": "Failed to load",
  "common.failedSave": "Failed to save",
  "common.failedDelete": "Failed to delete",

  "dash.title": "Dashboard",
  "dash.baseCurrency": "Base currency",
  "dash.addPosition": "+ Add position",
  "dash.total": "Total portfolio",
  "dash.goldPerGram": "Gold (per gram)",
  "dash.btcSol": "BTC / SOL",
  "dash.valueOverTime": "Portfolio value over time",
  "dash.allocation": "Allocation",
  "dash.noHistory": "No history yet — update a position to start tracking.",
  "dash.nothingToAllocate": "Nothing to allocate yet.",

  "pos.title": "Positions",
  "pos.subtitle":
    "Update a position anytime — each change is timestamped and shown on the chart.",
  "pos.history": "History",
  "pos.hideHistory": "Hide history",
  "pos.update": "Update",
  "pos.addNamed": "+ Add {name}",
  "pos.confirmDelete": "Delete all history for this asset?",
  "pos.when": "When",
  "pos.value": "Value",
  "pos.updatedAt": "Updated {when}",
  "pos.amountLabel": "{name} amount ({unit})",
  "pos.grams": "grams (g)",
  "pos.units": "units",
  "pos.livePrice": "Live price",
  "pos.estimate": "≈ {value} in base currency",
  "pos.invalidAmount": "Enter a valid amount.",
  "pos.principal": "Principal",
  "pos.accruesFrom": "Accruing since",
  "pos.accrued": "Interest accrued",
  "pos.rateNow": "Current rate",
  "pos.interestNote":
    "Statutory interest is worked out on the server against the NBP reference rate, so it grows on its own.",
  "pos.needStartDate": "Give the date the interest starts running.",

  "exp.title": "Expenses",
  "exp.subtitle":
    "Standing commitments. These are tracked separately and never affect your portfolio total.",
  "exp.add": "+ Add expense",
  "exp.new": "New expense",
  "exp.editTitle": "Edit expense",
  "exp.monthlyCommitment": "Monthly commitment",
  "exp.activeOngoing": "{active} active · {ongoing} ongoing",
  "exp.endingSoon": "Ending within 90 days",
  "exp.nothingEnding": "Nothing ending soon.",
  "exp.upcoming": "Upcoming one-offs",
  "exp.noneScheduled": "None scheduled.",
  "exp.byCategory": "Monthly by category",
  "exp.filterActive": "Active & upcoming",
  "exp.filterAll": "Show all",
  "exp.everyMonth": "Every month",
  "exp.oneOffSection": "One-off",
  "exp.empty": "No expenses yet — add your first standing commitment.",
  "exp.name": "Name",
  "exp.namePlaceholder": "e.g. Rent, Netflix, Car loan",
  "exp.howOften": "How often?",
  "exp.everyMonthOption": "Every month",
  "exp.onceOption": "One-off",
  "exp.firstPayment": "First payment",
  "exp.dueDate": "Due date",
  "exp.hasEnd": "This one ends on a date",
  "exp.indefiniteHint": "Leave unticked and it runs indefinitely.",
  "exp.category": "Category (optional)",
  "exp.categoryPlaceholder": "e.g. Housing, Subscriptions",
  "exp.addButton": "Add expense",
  "exp.saveChanges": "Save changes",
  "exp.amountPositive": "Enter an amount greater than zero.",
  "exp.endAfterStart": "The end date must be on or after the start date.",
  "exp.confirmDelete": 'Delete "{name}"?',
  "exp.statusActive": "active",
  "exp.statusScheduled": "scheduled",
  "exp.statusEnded": "ended",
  "exp.badgeOngoing": "ongoing",
  "exp.badgeOneOff": "one-off",
  "exp.since": "Since {date} · runs indefinitely",
  "exp.until": "Until {date}",
  "exp.daysLeft": "{days}d left",
  "exp.due": "Due {date}",
  "exp.wasDue": "Was due {date}",
  "exp.dueToday": "today",
  "exp.dueInDays": "in {days}d",
  "exp.perMonth": "/mo",
  "exp.uncategorised": "Uncategorised",

  "mon.title": "Monthly",
  "mon.subtitle":
    "Record what you earned and spent each month. Committed spend is computed from your recurring expenses, so you never retype it.",
  "mon.month": "Month",
  "mon.notFilled": " — not filled in",
  "mon.income": "Income",
  "mon.actualSpent": "Actually spent",
  "mon.saveMonth": "Save {month}",
  "mon.saved": "Saved {month}.",
  "mon.committedThis": "Committed this month",
  "mon.fromRecurring": "From your recurring expenses",
  "mon.surplus": "Surplus",
  "mon.savedPct": "{rate}% of income saved",
  "mon.addIncomeHint": "Add income to see a rate",
  "mon.actualVsCommitted": "Actual vs committed",
  "mon.above": "Spent above your commitments",
  "mon.below": "Spent below your commitments",
  "mon.matches": "Matches commitments",
  "mon.avgSavings": "Average savings rate",
  "mon.acrossMonths": "Across {count} recorded months",
  "mon.acrossMonth": "Across {count} recorded month",
  "mon.chartTitle": "Committed, income and actual",
  "mon.chartSubtitle":
    "Bars are what you are committed to; lines are what you recorded. Future months show commitments only.",
  "mon.savingsTitle": "Savings rate",
  "mon.savingsSubtitle": "Share of income left over, per recorded month.",
  "mon.categoryTitle": "Committed by category",
  "mon.categorySubtitle": "How your commitments break down month to month.",
  "mon.recorded": "Recorded months",
  "mon.tblMonth": "Month",
  "mon.tblIncome": "Income",
  "mon.tblActual": "Actual",
  "mon.tblCommitted": "Committed",
  "mon.tblSurplus": "Surplus",
  "mon.tblSaved": "Saved",
  "mon.tblEmpty": "Nothing recorded yet — fill in this month above.",
  "mon.noMonths": "No months to chart yet.",
  "mon.needIncome": "Record income for a month to see your savings rate.",
  "mon.needCategories": "Add expense categories to see this breakdown.",
  "mon.legendCommitted": "Committed",
  "mon.legendIncome": "Income",
  "mon.legendActual": "Actual spent",
  "mon.now": "now",
  "mon.savedTooltip": "Saved",
  "mon.other": "Other",

  "set.title": "Settings",
  "set.subtitle": "Choose how the app looks and which currency it reports in.",
  "set.appearance": "Appearance",
  "set.themeLight": "Light",
  "set.themeDark": "Dark",
  "set.themeSystem": "System",
  "set.followingSystem": "Following your device, currently {mode}.",
  "set.savedInBrowser": "Saved in this browser.",
  "set.language": "Language",
  "set.languageHint": "Applies to labels throughout the app.",
  "set.baseCurrency": "Base currency",
  "set.baseCurrencyHint":
    "All assets are converted to this currency using live exchange rates.",
  "set.timezone": "Time zone",
  "set.timezoneHint":
    "Used to show timestamps and to decide when a month or a commitment rolls over.",
  "set.timezoneNow": "Local time now: {time}",
  "set.saveSettings": "Save settings",
  "set.savedMsg": "Saved. Values are recalculated in the new base currency.",
};

const pl: Dict = {
  "app.name": "MyFinance",
  "nav.dashboard": "Pulpit",
  "nav.positions": "Pozycje",
  "nav.expenses": "Wydatki",
  "nav.monthly": "Miesięcznie",
  "nav.settings": "Ustawienia",

  "common.add": "Dodaj",
  "common.edit": "Edytuj",
  "common.delete": "Usuń",
  "common.cancel": "Anuluj",
  "common.save": "Zapisz",
  "common.saving": "Zapisywanie…",
  "common.loading": "Ładowanie…",
  "common.notes": "Notatki (opcjonalnie)",
  "common.currency": "Waluta",
  "common.amount": "Kwota",
  "common.failedLoad": "Nie udało się wczytać",
  "common.failedSave": "Nie udało się zapisać",
  "common.failedDelete": "Nie udało się usunąć",

  "dash.title": "Pulpit",
  "dash.baseCurrency": "Waluta bazowa",
  "dash.addPosition": "+ Dodaj pozycję",
  "dash.total": "Wartość portfela",
  "dash.goldPerGram": "Złoto (za gram)",
  "dash.btcSol": "BTC / SOL",
  "dash.valueOverTime": "Wartość portfela w czasie",
  "dash.allocation": "Struktura portfela",
  "dash.noHistory":
    "Brak historii — zaktualizuj pozycję, aby rozpocząć śledzenie.",
  "dash.nothingToAllocate": "Brak danych do pokazania.",

  "pos.title": "Pozycje",
  "pos.subtitle":
    "Pozycję możesz zaktualizować w dowolnej chwili — każda zmiana ma znacznik czasu i trafia na wykres.",
  "pos.history": "Historia",
  "pos.hideHistory": "Ukryj historię",
  "pos.update": "Aktualizuj",
  "pos.addNamed": "+ Dodaj {name}",
  "pos.confirmDelete": "Usunąć całą historię tego aktywa?",
  "pos.when": "Kiedy",
  "pos.value": "Wartość",
  "pos.updatedAt": "Zaktualizowano {when}",
  "pos.amountLabel": "{name} — ilość ({unit})",
  "pos.grams": "gramy (g)",
  "pos.units": "jednostki",
  "pos.livePrice": "Cena bieżąca",
  "pos.estimate": "≈ {value} w walucie bazowej",
  "pos.invalidAmount": "Podaj poprawną kwotę.",
  "pos.principal": "Kapitał",
  "pos.accruesFrom": "Nalicza się od",
  "pos.accrued": "Naliczone odsetki",
  "pos.rateNow": "Bieżąca stopa",
  "pos.interestNote":
    "Odsetki ustawowe liczy serwer wg stopy referencyjnej NBP, więc rosną same.",
  "pos.needStartDate": "Podaj datę, od której biegną odsetki.",

  "exp.title": "Wydatki",
  "exp.subtitle":
    "Stałe zobowiązania. Są śledzone osobno i nigdy nie wpływają na wartość portfela.",
  "exp.add": "+ Dodaj wydatek",
  "exp.new": "Nowy wydatek",
  "exp.editTitle": "Edytuj wydatek",
  "exp.monthlyCommitment": "Zobowiązania miesięczne",
  "exp.activeOngoing": "{active} aktywnych · {ongoing} bezterminowych",
  "exp.endingSoon": "Kończy się w ciągu 90 dni",
  "exp.nothingEnding": "Nic się wkrótce nie kończy.",
  "exp.upcoming": "Nadchodzące jednorazowe",
  "exp.noneScheduled": "Brak zaplanowanych.",
  "exp.byCategory": "Miesięcznie wg kategorii",
  "exp.filterActive": "Aktywne i nadchodzące",
  "exp.filterAll": "Pokaż wszystkie",
  "exp.everyMonth": "Co miesiąc",
  "exp.oneOffSection": "Jednorazowe",
  "exp.empty": "Brak wydatków — dodaj pierwsze stałe zobowiązanie.",
  "exp.name": "Nazwa",
  "exp.namePlaceholder": "np. Czynsz, Netflix, Kredyt samochodowy",
  "exp.howOften": "Jak często?",
  "exp.everyMonthOption": "Co miesiąc",
  "exp.onceOption": "Jednorazowo",
  "exp.firstPayment": "Pierwsza płatność",
  "exp.dueDate": "Termin płatności",
  "exp.hasEnd": "Ten wydatek kończy się w określonym dniu",
  "exp.indefiniteHint": "Nie zaznaczaj, jeśli trwa bezterminowo.",
  "exp.category": "Kategoria (opcjonalnie)",
  "exp.categoryPlaceholder": "np. Mieszkanie, Subskrypcje",
  "exp.addButton": "Dodaj wydatek",
  "exp.saveChanges": "Zapisz zmiany",
  "exp.amountPositive": "Podaj kwotę większą od zera.",
  "exp.endAfterStart":
    "Data zakończenia musi być taka sama lub późniejsza niż data rozpoczęcia.",
  "exp.confirmDelete": "Usunąć „{name}”?",
  "exp.statusActive": "aktywny",
  "exp.statusScheduled": "zaplanowany",
  "exp.statusEnded": "zakończony",
  "exp.badgeOngoing": "bezterminowy",
  "exp.badgeOneOff": "jednorazowy",
  "exp.since": "Od {date} · bezterminowo",
  "exp.until": "Do {date}",
  "exp.daysLeft": "pozostało {days} dni",
  "exp.due": "Termin {date}",
  "exp.wasDue": "Termin minął {date}",
  "exp.dueToday": "dzisiaj",
  "exp.dueInDays": "za {days} dni",
  "exp.perMonth": "/mies.",
  "exp.uncategorised": "Bez kategorii",

  "mon.title": "Miesięcznie",
  "mon.subtitle":
    "Zapisuj, ile zarobiłeś i wydałeś w danym miesiącu. Zobowiązania są liczone automatycznie z wydatków cyklicznych.",
  "mon.month": "Miesiąc",
  "mon.notFilled": " — nieuzupełniony",
  "mon.income": "Przychód",
  "mon.actualSpent": "Faktycznie wydane",
  "mon.saveMonth": "Zapisz {month}",
  "mon.saved": "Zapisano {month}.",
  "mon.committedThis": "Zobowiązania w tym miesiącu",
  "mon.fromRecurring": "Z Twoich wydatków cyklicznych",
  "mon.surplus": "Nadwyżka",
  "mon.savedPct": "zaoszczędzone {rate}% przychodu",
  "mon.addIncomeHint": "Podaj przychód, aby zobaczyć wskaźnik",
  "mon.actualVsCommitted": "Faktyczne vs zobowiązania",
  "mon.above": "Wydane powyżej zobowiązań",
  "mon.below": "Wydane poniżej zobowiązań",
  "mon.matches": "Zgodne ze zobowiązaniami",
  "mon.avgSavings": "Średnia stopa oszczędzania",
  "mon.acrossMonths": "Z {count} zapisanych miesięcy",
  "mon.acrossMonth": "Z {count} zapisanego miesiąca",
  "mon.chartTitle": "Zobowiązania, przychód i wydatki",
  "mon.chartSubtitle":
    "Słupki to Twoje zobowiązania, linie to zapisane wartości. Przyszłe miesiące pokazują tylko zobowiązania.",
  "mon.savingsTitle": "Stopa oszczędzania",
  "mon.savingsSubtitle": "Część przychodu, która zostaje, w każdym miesiącu.",
  "mon.categoryTitle": "Zobowiązania wg kategorii",
  "mon.categorySubtitle": "Jak Twoje zobowiązania rozkładają się w czasie.",
  "mon.recorded": "Zapisane miesiące",
  "mon.tblMonth": "Miesiąc",
  "mon.tblIncome": "Przychód",
  "mon.tblActual": "Wydane",
  "mon.tblCommitted": "Zobowiązania",
  "mon.tblSurplus": "Nadwyżka",
  "mon.tblSaved": "Oszczędności",
  "mon.tblEmpty": "Nic jeszcze nie zapisano — uzupełnij bieżący miesiąc powyżej.",
  "mon.noMonths": "Brak miesięcy do pokazania.",
  "mon.needIncome":
    "Zapisz przychód za miesiąc, aby zobaczyć stopę oszczędzania.",
  "mon.needCategories": "Dodaj kategorie wydatków, aby zobaczyć ten podział.",
  "mon.legendCommitted": "Zobowiązania",
  "mon.legendIncome": "Przychód",
  "mon.legendActual": "Faktycznie wydane",
  "mon.now": "teraz",
  "mon.savedTooltip": "Zaoszczędzono",
  "mon.other": "Inne",

  "set.title": "Ustawienia",
  "set.subtitle": "Wybierz wygląd aplikacji i walutę raportowania.",
  "set.appearance": "Wygląd",
  "set.themeLight": "Jasny",
  "set.themeDark": "Ciemny",
  "set.themeSystem": "Systemowy",
  "set.followingSystem": "Zgodnie z ustawieniem urządzenia, obecnie {mode}.",
  "set.savedInBrowser": "Zapisane w tej przeglądarce.",
  "set.language": "Język",
  "set.languageHint": "Dotyczy etykiet w całej aplikacji.",
  "set.baseCurrency": "Waluta bazowa",
  "set.baseCurrencyHint":
    "Wszystkie aktywa są przeliczane na tę walutę po bieżącym kursie.",
  "set.timezone": "Strefa czasowa",
  "set.timezoneHint":
    "Używana do wyświetlania znaczników czasu oraz do ustalenia, kiedy kończy się miesiąc lub zobowiązanie.",
  "set.timezoneNow": "Czas lokalny: {time}",
  "set.saveSettings": "Zapisz ustawienia",
  "set.savedMsg": "Zapisano. Wartości przeliczono na nową walutę bazową.",
};

const DICTS: Record<Language, Dict> = { en, pl };

export function readLanguage(): Language {
  if (typeof window === "undefined") return "en";
  try {
    const stored = window.localStorage.getItem(LANGUAGE_KEY);
    if (stored === "en" || stored === "pl") return stored;
  } catch {
    // Blocked storage - fall back to the default.
  }
  return "en";
}

export function storeLanguage(lang: Language): void {
  try {
    window.localStorage.setItem(LANGUAGE_KEY, lang);
  } catch {
    // Not fatal - the choice still applies for this page view.
  }
}

export function translate(
  lang: Language,
  key: string,
  vars?: Record<string, string | number>
): string {
  // Fall back to English, then to the key itself, so a missing string is
  // visible rather than silently blank.
  const text = DICTS[lang][key] ?? DICTS.en[key] ?? key;
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (match, name) =>
    name in vars ? String(vars[name]) : match
  );
}

export interface I18nValue {
  lang: Language;
  locale: string;
  setLang: (lang: Language) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

export const I18nContext = createContext<I18nValue>({
  lang: "en",
  locale: "en-US",
  setLang: () => {},
  t: (key, vars) => translate("en", key, vars),
});

export function useI18n(): I18nValue {
  return useContext(I18nContext);
}
