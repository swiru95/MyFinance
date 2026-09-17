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
  "dash.profile": "Risk profile",
  "dash.breakdown": "Breakdown",
  "chart.by": "Split by",
  "chart.total": "Total",
  "chart.asset": "Assets",
  "chart.category": "Classes",
  "chart.profile": "Risk",
  "chart.other": "Other",
  "chart.singleDay":
    "One day of history so far - the line appears once positions have been updated on a later date.",
  "dash.otherSlices": "Other ({count})",
  "dash.otherDetail": "Other covers: {names}",
  "profile.safe": "Safe",
  "profile.moderate": "Moderate",
  "profile.risky": "Risky",
  "profile.illiquid": "Illiquid",
  "profile.hint":
    "Volatility and liquidity are separate axes: the illiquid band is not more risky, it is harder to sell.",

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

  "app.tagline": "Budget & Portfolio Tracker",
  "app.description":
    "Track cash, gold, stocks, funds, bonds, watches, crypto and savings.",

  "nav.report": "Report",

  "mon.effective": "Effective spend",
  "mon.effectiveHint": "Income minus the change in your portfolio",
  "mon.walletChange": "Portfolio change: {value}",
  "mon.effectiveUnavailable": "Needs income and portfolio history for this month",
  "mon.effectiveNote":
    "Effective spend is income minus what the portfolio actually gained, so a market drawdown counts towards it just as real spending does.",
  "mon.tblEffective": "Effective",
  "mon.legendEffective": "Effective spend",

  "rep.title": "Assessment",
  "rep.subtitle":
    "A written review of your portfolio, produced locally by the Thinker model on your own hardware.",
  "rep.style": "Target style",
  "rep.styleHint": "The report judges your holdings against the style you pick.",
  "rep.style.safe": "Safe",
  "rep.style.safeHint": "Capital preservation first; volatility is a cost, not an opportunity.",
  "rep.style.balanced": "Balanced",
  "rep.style.balancedHint": "Growth with a real cash buffer and a cap on any single class.",
  "rep.style.risky": "Risky",
  "rep.style.riskyHint": "Accepts drawdowns for upside; concentration is allowed on conviction.",
  "rep.style.longTerm": "Long-term",
  "rep.style.longTermHint": "A decade-plus horizon; liquidity matters less than compounding.",
  "rep.generate": "Generate assessment",
  "rep.generating": "Generating…",
  "rep.queued": "Queued — waiting for the model.",
  "rep.running": "The model is writing. This takes a few minutes.",
  "rep.translating": "Translating into Polish with Bielik…",
  "rep.langNote":
    "Polish reports are written by Thinker in English, then translated by Bielik.",
  "rep.failed": "Generation failed",
  "rep.retry": "Try again",
  "rep.empty": "No assessment yet — pick a style and generate one.",
  "rep.history": "Earlier assessments",
  "rep.noHistory": "Nothing generated yet.",
  "rep.generatedAt": "Generated {when}",
  "rep.modelLine": "Written by {model}",
  "rep.translatedLine": "Written by {model}, translated by {translator}",
  "rep.disclaimer":
    "Generated by a language model from your own figures. It is not financial advice — check anything you act on.",
  "rep.confirmDelete": "Delete this assessment?",
  "rep.unavailable":
    "No model is configured. Set MYFINANCE_LLM_BASE_URL and MYFINANCE_LLM_API_KEY on the backend.",
  "rep.snapshot": "Based on {total} across {positions} positions",
  "rep.mtls": "Authenticated to {model} with this pod's own certificate.",
  "rep.tlsPlain": "Connection to {model} is not certificate-verified.",
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
  "dash.profile": "Profil ryzyka",
  "dash.breakdown": "Struktura portfela",
  "chart.by": "Podział",
  "chart.total": "Razem",
  "chart.asset": "Aktywa",
  "chart.category": "Klasy",
  "chart.profile": "Ryzyko",
  "chart.other": "Pozostałe",
  "chart.singleDay":
    "Na razie jeden dzień historii - linia pojawi się, gdy zaktualizujesz pozycje w kolejnym dniu.",
  "dash.otherSlices": "Pozostałe ({count})",
  "dash.otherDetail": "Pozostałe obejmuje: {names}",
  "profile.safe": "Bezpieczne",
  "profile.moderate": "Umiarkowane",
  "profile.risky": "Ryzykowne",
  "profile.illiquid": "Niepłynne",
  "profile.hint":
    "Zmienność i płynność to osobne osie: pasmo niepłynne nie jest bardziej ryzykowne, tylko trudniejsze do sprzedania.",

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

  "app.tagline": "Budżet i portfel",
  "app.description":
    "Śledź gotówkę, złoto, akcje, fundusze, obligacje, zegarki, kryptowaluty i oszczędności.",

  "nav.report": "Raport",

  "mon.effective": "Wydatki efektywne",
  "mon.effectiveHint": "Przychód minus zmiana wartości portfela",
  "mon.walletChange": "Zmiana portfela: {value}",
  "mon.effectiveUnavailable":
    "Wymaga przychodu i historii portfela za ten miesiąc",
  "mon.effectiveNote":
    "Wydatki efektywne to przychód minus faktyczny przyrost portfela, więc spadek na rynku liczy się tak samo jak realny wydatek.",
  "mon.tblEffective": "Efektywne",
  "mon.legendEffective": "Wydatki efektywne",

  "rep.title": "Ocena portfela",
  "rep.subtitle":
    "Pisemna ocena Twojego portfela, tworzona lokalnie przez model Thinker na Twoim sprzęcie.",
  "rep.style": "Docelowy styl",
  "rep.styleHint": "Raport ocenia Twoje aktywa względem wybranego stylu.",
  "rep.style.safe": "Bezpieczny",
  "rep.style.safeHint":
    "Najpierw ochrona kapitału; zmienność to koszt, nie okazja.",
  "rep.style.balanced": "Zrównoważony",
  "rep.style.balancedHint":
    "Wzrost przy realnej poduszce gotówkowej i limicie na pojedynczą klasę.",
  "rep.style.risky": "Ryzykowny",
  "rep.style.riskyHint":
    "Akceptuje obsunięcia w zamian za potencjał; koncentracja jest dopuszczalna.",
  "rep.style.longTerm": "Długoterminowy",
  "rep.style.longTermHint":
    "Horyzont ponad dekady; płynność znaczy mniej niż procent składany.",
  "rep.generate": "Wygeneruj ocenę",
  "rep.generating": "Generowanie…",
  "rep.queued": "W kolejce — czekam na model.",
  "rep.running": "Model pisze raport. To potrwa kilka minut.",
  "rep.translating": "Tłumaczenie na polski przez Bielika…",
  "rep.langNote":
    "Raporty po polsku pisze Thinker po angielsku, a tłumaczy je Bielik.",
  "rep.failed": "Generowanie nie powiodło się",
  "rep.retry": "Spróbuj ponownie",
  "rep.empty": "Brak oceny — wybierz styl i wygeneruj raport.",
  "rep.history": "Wcześniejsze oceny",
  "rep.noHistory": "Nic jeszcze nie wygenerowano.",
  "rep.generatedAt": "Wygenerowano {when}",
  "rep.modelLine": "Napisane przez {model}",
  "rep.translatedLine": "Napisane przez {model}, przetłumaczone przez {translator}",
  "rep.disclaimer":
    "Wygenerowane przez model językowy na podstawie Twoich danych. To nie jest porada inwestycyjna — zweryfikuj wszystko, na co się zdecydujesz.",
  "rep.confirmDelete": "Usunąć tę ocenę?",
  "rep.unavailable":
    "Nie skonfigurowano modelu. Ustaw MYFINANCE_LLM_BASE_URL i MYFINANCE_LLM_API_KEY w backendzie.",
  "rep.snapshot": "Na podstawie {total} w {positions} pozycjach",
  "rep.mtls": "Uwierzytelniono w {model} własnym certyfikatem tego poda.",
  "rep.tlsPlain": "Połączenie z {model} nie jest weryfikowane certyfikatem.",
};

const DICTS: Record<Language, Dict> = { en, pl };

/**
 * Asset names, classes and the backend's "Uncategorised" bucket are stored in
 * the database, not in this file, so `t()` never sees them - they arrive from
 * the API already spelled in English and used to render untranslated.
 *
 * These map the values the backend seeds (schema.py) and computes
 * (profiles.py, budget.py) onto their Polish equivalents. A name the user
 * typed themselves is not in the table and falls through unchanged, which is
 * the point: their own wording is never rewritten.
 */
const DATA_PL: Dict = {
  // Seeded asset names.
  Cash: "Gotówka",
  Gold: "Złoto",
  Stocks: "Akcje",
  "TFI Funds": "Fundusze TFI",
  "National Bonds": "Obligacje skarbowe",
  Watches: "Zegarki",
  Bitcoin: "Bitcoin",
  Solana: "Solana",
  Savings: "Oszczędności",
  // Asset classes (Asset.category), including the ones only profiles.py names.
  TFI: "TFI",
  Bonds: "Obligacje",
  Crypto: "Kryptowaluty",
  Retirement: "Emerytura",
  "Fixed Assets": "Środki trwałe",
  Receivables: "Należności",
  // Fallback bucket emitted by the expense/budget endpoints.
  Uncategorised: "Bez kategorii",
};

const DATA_DICTS: Partial<Record<Language, Dict>> = { pl: DATA_PL };

/** Translate a label that came from the database; leave anything unknown as
 *  typed. Blank in, blank out - callers pass straight through. */
export function translateData(lang: Language, value: string): string {
  if (!value) return value;
  return DATA_DICTS[lang]?.[value] ?? value;
}

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
  /** Translate a label that came from the API rather than from a dictionary
   *  key - an asset name or class. Unknown values pass through unchanged. */
  td: (value: string) => string;
}

export const I18nContext = createContext<I18nValue>({
  lang: "en",
  locale: "en-US",
  setLang: () => {},
  t: (key, vars) => translate("en", key, vars),
  td: (value) => value,
});

export function useI18n(): I18nValue {
  return useContext(I18nContext);
}
