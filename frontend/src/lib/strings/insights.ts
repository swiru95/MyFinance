/** LLM-insights strings, kept out of lib/i18n.ts so feature work does not
 *  collide in one long file. Merged into the main dictionaries there the
 *  same way lib/strings/income.ts and lib/strings/fire.ts are.
 *
 *  "nav.report" is deliberately redefined here (the /report page becomes
 *  Insights / Analizy while keeping its route and nav key) - the merge
 *  order in i18n.ts ({...en, ...incomeStrings.en, ...fireStrings.en,
 *  ...insightsStrings.en}) makes this file win on that shared key, the same
 *  trick lib/strings/income.ts documents for "mon.income".
 *
 *  The `ins.ladder.<rungKey>.<status>` keys are this UI's own copy for each
 *  ladder rung, not a translation of the backend's `why_key` - see
 *  components/insights/ladderCopy.ts for why. */
export const en: Record<string, string> = {
  "nav.report": "Insights",

  "ins.title": "Insights",
  "ins.subtitle":
    "A ranked next step, a monthly digest, and how your stated risk tolerance compares with how your wallet is actually invested — all written locally by a model from your own figures.",

  "ins.tab.nextSteps": "Next steps",
  "ins.tab.digest": "Monthly digest",
  "ins.tab.profile": "Profile",
  "ins.tab.assessment": "Wallet assessment",

  "ins.job.queued": "Queued — waiting for the model.",
  "ins.job.running":
    "The model is working. This can take a few minutes — it may still be loading.",
  "ins.job.translating": "Translating into Polish with Bielik…",
  "ins.job.failed": "Generation failed",
  "ins.job.retry": "Try again",

  "ins.next.checklistTitle": "Your ladder",
  "ins.next.checklistSubtitle":
    "Deterministic checks against your own data, in the order worth tackling them.",
  "ins.next.checklistEmpty": "Nothing to check yet — add some data first.",
  "ins.next.rankedTitle": "Ranked by the model",
  "ins.next.rankedEmpty":
    "No ranking yet — refresh to have the model pick the top few.",
  "ins.next.refresh": "Refresh suggestions",
  "ins.next.feedback.done": "Done",
  "ins.next.feedback.dismissed": "Not for me",
  "ins.next.feedback.later": "Later",

  "ins.ladder.status.done": "Done",
  "ins.ladder.status.in_progress": "In progress",
  "ins.ladder.status.todo": "To do",
  "ins.ladder.status.not_applicable": "Not applicable",
  "ins.ladder.status.unknown": "Unknown",

  "ins.ladder.starter_buffer.title": "Starter buffer",
  "ins.ladder.starter_buffer.done":
    "Safe assets cover at least one month of committed spending.",
  "ins.ladder.starter_buffer.in_progress":
    "Safe assets are building up toward one month of committed spending.",
  "ins.ladder.starter_buffer.todo":
    "Safe assets don't yet cover one month of committed spending.",
  "ins.ladder.starter_buffer.not_applicable": "Not applicable.",
  "ins.ladder.starter_buffer.unknown": "Not enough data to tell yet.",

  "ins.ladder.envelope_covered.title": "Tax envelope covered",
  "ins.ladder.envelope_covered.done":
    "Safe or cash assets cover the tax envelope you're currently holding.",
  "ins.ladder.envelope_covered.in_progress":
    "Safe or cash assets partly cover the tax envelope you're holding.",
  "ins.ladder.envelope_covered.todo":
    "Safe or cash assets don't cover the tax envelope you're currently holding.",
  "ins.ladder.envelope_covered.not_applicable":
    "No B2B income, so there's no tax envelope to cover.",
  "ins.ladder.envelope_covered.unknown": "Not enough data to tell yet.",

  "ins.ladder.emergency_fund.title": "Emergency fund",
  "ins.ladder.emergency_fund.done":
    "Your emergency fund meets its target number of months.",
  "ins.ladder.emergency_fund.in_progress":
    "Your emergency fund is partway to its target.",
  "ins.ladder.emergency_fund.todo":
    "Your emergency fund is well below its target.",
  "ins.ladder.emergency_fund.not_applicable": "Not applicable.",
  "ins.ladder.emergency_fund.unknown": "Add committed expenses to see this.",

  "ins.ladder.ppk_on.title": "PPK contributions",
  "ins.ladder.ppk_on.done":
    "You're contributing to PPK and getting the employer's match.",
  "ins.ladder.ppk_on.in_progress": "PPK contributions are partly set up.",
  "ins.ladder.ppk_on.todo":
    "PPK is off — you're giving up the employer's 1.5% match and the state's payments.",
  "ins.ladder.ppk_on.not_applicable":
    "No active UoP source, so PPK doesn't apply.",
  "ins.ladder.ppk_on.unknown": "Not enough data to tell yet.",

  "ins.ladder.ikze_used.title": "IKZE allowance",
  "ins.ladder.ikze_used.done": "You've used this year's IKZE limit.",
  "ins.ladder.ikze_used.in_progress":
    "You've started this year's IKZE allowance, with room left.",
  "ins.ladder.ikze_used.todo":
    "You haven't used any of this year's IKZE allowance yet.",
  "ins.ladder.ikze_used.not_applicable": "Not applicable.",
  "ins.ladder.ikze_used.unknown": "Not enough data to tell yet.",

  "ins.ladder.ike_used.title": "IKE allowance",
  "ins.ladder.ike_used.done": "You've used this year's IKE limit.",
  "ins.ladder.ike_used.in_progress":
    "You've started this year's IKE allowance, with room left.",
  "ins.ladder.ike_used.todo":
    "You haven't used any of this year's IKE allowance yet.",
  "ins.ladder.ike_used.not_applicable": "Not applicable.",
  "ins.ladder.ike_used.unknown": "Not enough data to tell yet.",

  "ins.ladder.fire_configured.title": "FIRE plan set up",
  "ins.ladder.fire_configured.done": "Your FIRE settings are filled in.",
  "ins.ladder.fire_configured.in_progress":
    "Your FIRE settings are partly filled in.",
  "ins.ladder.fire_configured.todo":
    "Set your birth year and target FI age to unlock FIRE planning.",
  "ins.ladder.fire_configured.not_applicable": "Not applicable.",
  "ins.ladder.fire_configured.unknown": "Not enough data to tell yet.",

  "ins.ladder.savings_rate_on_track.title": "Savings rate on track",
  "ins.ladder.savings_rate_on_track.done":
    "Your savings rate meets what your FIRE plan needs.",
  "ins.ladder.savings_rate_on_track.in_progress":
    "Your savings rate is close to what your FIRE plan needs.",
  "ins.ladder.savings_rate_on_track.todo":
    "Your savings rate is below what your FIRE plan needs.",
  "ins.ladder.savings_rate_on_track.not_applicable": "Not applicable.",
  "ins.ladder.savings_rate_on_track.unknown":
    "Set up FIRE planning to see whether your savings rate is on track.",

  "ins.ladder.data_fresh.title": "Data up to date",
  "ins.ladder.data_fresh.done":
    "Your positions and recent spending are up to date.",
  "ins.ladder.data_fresh.in_progress":
    "Some of your positions or recent spending could use an update.",
  "ins.ladder.data_fresh.todo":
    "Update your positions and recent months' spending for accurate numbers.",
  "ins.ladder.data_fresh.not_applicable": "Not applicable.",
  "ins.ladder.data_fresh.unknown": "Not enough data to tell yet.",

  "ins.digest.month": "Month",
  "ins.digest.generate": "Generate",
  "ins.digest.generating": "Generating…",
  "ins.digest.empty": "No digest yet — pick a month and generate one.",
  "ins.digest.snapshot": "Snapshot figures",
  "ins.digest.groundingWarning":
    "Some numbers in this text could not be matched to your data — treat them with caution.",
  "ins.digest.history": "Earlier digests",
  "ins.digest.noHistory": "Nothing generated yet.",
  "ins.digest.confirmDelete": "Delete this digest?",

  "ins.profile.goals": "Goals",
  "ins.profile.goal.retire_early": "Retire early",
  "ins.profile.goal.buy_home": "Buy a home",
  "ins.profile.goal.kids_education": "Kids' education",
  "ins.profile.goal.financial_safety": "Financial safety",
  "ins.profile.goal.travel": "Travel",
  "ins.profile.goal.business": "Start or grow a business",
  "ins.profile.horizon": "Time horizon (years)",
  "ins.profile.dependents": "Dependents",
  "ins.profile.household": "Household",
  "ins.profile.household.single": "Single",
  "ins.profile.household.couple": "Couple",
  "ins.profile.household.family": "Family",
  "ins.profile.incomeStability": "How stable does your income feel?",
  "ins.profile.level.low": "Low",
  "ins.profile.level.medium": "Medium",
  "ins.profile.level.high": "High",
  "ins.profile.drawdown": "If your portfolio dropped 20% tomorrow, you would…",
  "ins.profile.drawdown.sell_all": "Sell everything",
  "ins.profile.drawdown.sell_some": "Sell some",
  "ins.profile.drawdown.hold": "Hold",
  "ins.profile.drawdown.buy_more": "Buy more",
  "ins.profile.lossTolerance": "Maximum loss you could tolerate",
  "ins.profile.fireInterest": "Interest in FIRE",
  "ins.profile.fire.none": "None",
  "ins.profile.fire.curious": "Curious",
  "ins.profile.fire.planning": "Planning",
  "ins.profile.fire.committed": "Committed",
  "ins.profile.experience": "Investing experience",
  "ins.profile.exp.none": "None",
  "ins.profile.exp.basic": "Basic",
  "ins.profile.exp.intermediate": "Intermediate",
  "ins.profile.exp.advanced": "Advanced",
  "ins.profile.save": "Save and analyse",
  "ins.profile.saving": "Analysing…",
  "ins.profile.stated": "Stated tolerance",
  "ins.profile.capacity": "Capacity",
  "ins.profile.revealed": "Revealed",
  "ins.profile.summary": "Summary",
  "ins.profile.mismatches": "Mismatches",
  "ins.profile.noMismatches":
    "No mismatches found — what you say and what you hold line up.",
  "ins.profile.priorities": "Priorities",
  "ins.profile.useStyle": "Use the suggested style ({style}) for the wallet assessment",
  "ins.profile.useStyleDone": "Style set for the wallet assessment.",
  "ins.profile.empty":
    "Answer the questionnaire and analyse to see your profile.",

  "ins.tile.title": "Next step",
  "ins.tile.allDone": "All caught up",

  "ins.data.translationUnavailable":
    "Translation unavailable — showing the English original.",
};

export const pl: Record<string, string> = {
  "nav.report": "Analizy",

  "ins.title": "Analizy",
  "ins.subtitle":
    "Uszeregowany kolejny krok, comiesięczne podsumowanie i porównanie deklarowanej tolerancji ryzyka z tym, jak naprawdę inwestujesz — wszystko napisane lokalnie przez model na podstawie Twoich danych.",

  "ins.tab.nextSteps": "Kolejne kroki",
  "ins.tab.digest": "Podsumowanie miesiąca",
  "ins.tab.profile": "Profil",
  "ins.tab.assessment": "Ocena portfela",

  "ins.job.queued": "W kolejce — czekam na model.",
  "ins.job.running":
    "Model pracuje. To może potrwać kilka minut — być może wciąż się wczytuje.",
  "ins.job.translating": "Tłumaczenie na polski przez Bielika…",
  "ins.job.failed": "Generowanie nie powiodło się",
  "ins.job.retry": "Spróbuj ponownie",

  "ins.next.checklistTitle": "Twoja drabinka",
  "ins.next.checklistSubtitle":
    "Deterministyczne sprawdzenia na Twoich danych, w kolejności, w jakiej warto się nimi zająć.",
  "ins.next.checklistEmpty": "Jeszcze nic do sprawdzenia — dodaj najpierw dane.",
  "ins.next.rankedTitle": "Uszeregowane przez model",
  "ins.next.rankedEmpty":
    "Brak rankingu — odśwież, aby model wybrał kilka najważniejszych.",
  "ins.next.refresh": "Odśwież sugestie",
  "ins.next.feedback.done": "Zrobione",
  "ins.next.feedback.dismissed": "Nie dla mnie",
  "ins.next.feedback.later": "Później",

  "ins.ladder.status.done": "Zrobione",
  "ins.ladder.status.in_progress": "W trakcie",
  "ins.ladder.status.todo": "Do zrobienia",
  "ins.ladder.status.not_applicable": "Nie dotyczy",
  "ins.ladder.status.unknown": "Nieznane",

  "ins.ladder.starter_buffer.title": "Bufor startowy",
  "ins.ladder.starter_buffer.done":
    "Aktywa bezpieczne pokrywają co najmniej miesiąc zobowiązań.",
  "ins.ladder.starter_buffer.in_progress":
    "Aktywa bezpieczne rosną w stronę pokrycia miesiąca zobowiązań.",
  "ins.ladder.starter_buffer.todo":
    "Aktywa bezpieczne nie pokrywają jeszcze miesiąca zobowiązań.",
  "ins.ladder.starter_buffer.not_applicable": "Nie dotyczy.",
  "ins.ladder.starter_buffer.unknown": "Za mało danych, aby ocenić.",

  "ins.ladder.envelope_covered.title": "Pokryta rezerwa podatkowa",
  "ins.ladder.envelope_covered.done":
    "Aktywa bezpieczne lub gotówka pokrywają aktualną rezerwę podatkową.",
  "ins.ladder.envelope_covered.in_progress":
    "Aktywa bezpieczne lub gotówka częściowo pokrywają rezerwę podatkową.",
  "ins.ladder.envelope_covered.todo":
    "Aktywa bezpieczne lub gotówka nie pokrywają aktualnej rezerwy podatkowej.",
  "ins.ladder.envelope_covered.not_applicable":
    "Brak dochodu z B2B, więc nie ma rezerwy podatkowej do pokrycia.",
  "ins.ladder.envelope_covered.unknown": "Za mało danych, aby ocenić.",

  "ins.ladder.emergency_fund.title": "Fundusz awaryjny",
  "ins.ladder.emergency_fund.done":
    "Fundusz awaryjny osiąga docelową liczbę miesięcy.",
  "ins.ladder.emergency_fund.in_progress":
    "Fundusz awaryjny jest w drodze do celu.",
  "ins.ladder.emergency_fund.todo":
    "Fundusz awaryjny jest wyraźnie poniżej celu.",
  "ins.ladder.emergency_fund.not_applicable": "Nie dotyczy.",
  "ins.ladder.emergency_fund.unknown": "Dodaj wydatki cykliczne, aby to zobaczyć.",

  "ins.ladder.ppk_on.title": "Wpłaty na PPK",
  "ins.ladder.ppk_on.done":
    "Wpłacasz na PPK i otrzymujesz dopłatę pracodawcy.",
  "ins.ladder.ppk_on.in_progress": "PPK jest częściowo skonfigurowane.",
  "ins.ladder.ppk_on.todo":
    "PPK jest wyłączone — tracisz dopłatę pracodawcy (1,5%) i wpłaty państwa.",
  "ins.ladder.ppk_on.not_applicable":
    "Brak aktywnego źródła UoP, więc PPK nie dotyczy.",
  "ins.ladder.ppk_on.unknown": "Za mało danych, aby ocenić.",

  "ins.ladder.ikze_used.title": "Limit IKZE",
  "ins.ladder.ikze_used.done": "Wykorzystano tegoroczny limit IKZE.",
  "ins.ladder.ikze_used.in_progress":
    "Zacząłeś/-aś korzystać z tegorocznego limitu IKZE, zostało jeszcze miejsce.",
  "ins.ladder.ikze_used.todo":
    "Nie wykorzystano jeszcze tegorocznego limitu IKZE.",
  "ins.ladder.ikze_used.not_applicable": "Nie dotyczy.",
  "ins.ladder.ikze_used.unknown": "Za mało danych, aby ocenić.",

  "ins.ladder.ike_used.title": "Limit IKE",
  "ins.ladder.ike_used.done": "Wykorzystano tegoroczny limit IKE.",
  "ins.ladder.ike_used.in_progress":
    "Zacząłeś/-aś korzystać z tegorocznego limitu IKE, zostało jeszcze miejsce.",
  "ins.ladder.ike_used.todo":
    "Nie wykorzystano jeszcze tegorocznego limitu IKE.",
  "ins.ladder.ike_used.not_applicable": "Nie dotyczy.",
  "ins.ladder.ike_used.unknown": "Za mało danych, aby ocenić.",

  "ins.ladder.fire_configured.title": "Skonfigurowany plan FIRE",
  "ins.ladder.fire_configured.done": "Ustawienia FIRE są uzupełnione.",
  "ins.ladder.fire_configured.in_progress":
    "Ustawienia FIRE są częściowo uzupełnione.",
  "ins.ladder.fire_configured.todo":
    "Podaj rok urodzenia i docelowy wiek FI, aby odblokować planowanie FIRE.",
  "ins.ladder.fire_configured.not_applicable": "Nie dotyczy.",
  "ins.ladder.fire_configured.unknown": "Za mało danych, aby ocenić.",

  "ins.ladder.savings_rate_on_track.title": "Stopa oszczędzania na dobrej drodze",
  "ins.ladder.savings_rate_on_track.done":
    "Twoja stopa oszczędzania spełnia wymóg planu FIRE.",
  "ins.ladder.savings_rate_on_track.in_progress":
    "Twoja stopa oszczędzania jest blisko wymogu planu FIRE.",
  "ins.ladder.savings_rate_on_track.todo":
    "Twoja stopa oszczędzania jest poniżej wymogu planu FIRE.",
  "ins.ladder.savings_rate_on_track.not_applicable": "Nie dotyczy.",
  "ins.ladder.savings_rate_on_track.unknown":
    "Skonfiguruj planowanie FIRE, aby to sprawdzić.",

  "ins.ladder.data_fresh.title": "Aktualne dane",
  "ins.ladder.data_fresh.done": "Pozycje i ostatnie wydatki są aktualne.",
  "ins.ladder.data_fresh.in_progress":
    "Część pozycji lub ostatnich wydatków warto zaktualizować.",
  "ins.ladder.data_fresh.todo":
    "Zaktualizuj pozycje i wydatki z ostatnich miesięcy, aby liczby były trafne.",
  "ins.ladder.data_fresh.not_applicable": "Nie dotyczy.",
  "ins.ladder.data_fresh.unknown": "Za mało danych, aby ocenić.",

  "ins.digest.month": "Miesiąc",
  "ins.digest.generate": "Generuj",
  "ins.digest.generating": "Generowanie…",
  "ins.digest.empty": "Brak podsumowania — wybierz miesiąc i wygeneruj.",
  "ins.digest.snapshot": "Dane źródłowe",
  "ins.digest.groundingWarning":
    "Niektórych liczb w tym tekście nie udało się dopasować do Twoich danych — zachowaj ostrożność.",
  "ins.digest.history": "Wcześniejsze podsumowania",
  "ins.digest.noHistory": "Nic jeszcze nie wygenerowano.",
  "ins.digest.confirmDelete": "Usunąć to podsumowanie?",

  "ins.profile.goals": "Cele",
  "ins.profile.goal.retire_early": "Wcześniejsza emerytura",
  "ins.profile.goal.buy_home": "Zakup mieszkania lub domu",
  "ins.profile.goal.kids_education": "Edukacja dzieci",
  "ins.profile.goal.financial_safety": "Bezpieczeństwo finansowe",
  "ins.profile.goal.travel": "Podróże",
  "ins.profile.goal.business": "Założenie lub rozwój firmy",
  "ins.profile.horizon": "Horyzont czasowy (lata)",
  "ins.profile.dependents": "Osoby na utrzymaniu",
  "ins.profile.household": "Gospodarstwo domowe",
  "ins.profile.household.single": "Singiel / singielka",
  "ins.profile.household.couple": "Para",
  "ins.profile.household.family": "Rodzina",
  "ins.profile.incomeStability": "Jak stabilny wydaje Ci się Twój dochód?",
  "ins.profile.level.low": "Niska",
  "ins.profile.level.medium": "Średnia",
  "ins.profile.level.high": "Wysoka",
  "ins.profile.drawdown": "Gdyby portfel spadł o 20%, Twoja reakcja to:",
  "ins.profile.drawdown.sell_all": "Sprzedaż całości",
  "ins.profile.drawdown.sell_some": "Sprzedaż części",
  "ins.profile.drawdown.hold": "Pozostawienie bez zmian",
  "ins.profile.drawdown.buy_more": "Dokupienie więcej",
  "ins.profile.lossTolerance": "Maksymalna akceptowalna strata",
  "ins.profile.fireInterest": "Zainteresowanie FIRE",
  "ins.profile.fire.none": "Brak",
  "ins.profile.fire.curious": "Ciekawość",
  "ins.profile.fire.planning": "Planowanie",
  "ins.profile.fire.committed": "Zaangażowanie",
  "ins.profile.experience": "Doświadczenie inwestycyjne",
  "ins.profile.exp.none": "Brak",
  "ins.profile.exp.basic": "Podstawowe",
  "ins.profile.exp.intermediate": "Średnie",
  "ins.profile.exp.advanced": "Zaawansowane",
  "ins.profile.save": "Zapisz i przeanalizuj",
  "ins.profile.saving": "Analizowanie…",
  "ins.profile.stated": "Deklarowana",
  "ins.profile.capacity": "Zdolność",
  "ins.profile.revealed": "Rzeczywista",
  "ins.profile.summary": "Podsumowanie",
  "ins.profile.mismatches": "Rozbieżności",
  "ins.profile.noMismatches":
    "Brak rozbieżności — to, co deklarujesz, zgadza się z tym, co posiadasz.",
  "ins.profile.priorities": "Priorytety",
  "ins.profile.useStyle": "Użyj sugerowanego stylu ({style}) w ocenie portfela",
  "ins.profile.useStyleDone": "Ustawiono styl dla oceny portfela.",
  "ins.profile.empty":
    "Wypełnij ankietę i przeanalizuj, aby zobaczyć swój profil.",

  "ins.tile.title": "Kolejny krok",
  "ins.tile.allDone": "Wszystko zrobione",

  "ins.data.translationUnavailable":
    "Tłumaczenie niedostępne — pokazujemy oryginał po angielsku.",
};
