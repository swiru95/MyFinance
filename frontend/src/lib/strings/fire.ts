/** FIRE strings, kept out of lib/i18n.ts so feature work does not collide
 *  in one 700-line file. Merged into the main dictionaries there. Every key
 *  is prefixed `fire.` (including the position-flow and asset-editing keys
 *  used on /positions) so nothing here can collide with a key another work
 *  package adds to its own strings file. */
export const en: Record<string, string> = {
  "fire.title": "Retirement",
  "fire.subtitle":
    "Financial independence, priced from your own portfolio, spending and income.",
  "fire.disclaimer":
    "A model, not a forecast: real returns, inflation and your spending will differ. It is here to show which levers matter.",
  "fire.needBirthYear":
    "Add your birth year below to see your FIRE numbers.",
  "fire.howComputed": "How this is computed",
  "fire.perMonth": "/mo",

  "fire.settings.title": "Settings",
  "fire.settings.birthYear": "Birth year",
  "fire.settings.targetFiAge": "Target FI age",
  "fire.settings.targetFiAgeHint":
    "Optional — leave blank to just see when you'd get there at your current rate.",
  "fire.settings.retirementAge": "Retirement age",
  "fire.settings.retirementAgeHint":
    "Statutory ZUS pension age: 65 for men, 60 for women. Use your own if it differs.",
  "fire.settings.swr": "Safe withdrawal rate",
  "fire.settings.swrHint":
    "3.5% rather than the US 4% rule: this is one portfolio, not a whole-market index, and Polish inflation history has been rougher, so a lower rate leaves more margin.",
  "fire.settings.inflation": "Inflation",
  "fire.settings.realReturnOverride": "Real return override",
  "fire.settings.realReturnOverrideHint":
    "Blank = derived from your current allocation's blended return, minus inflation.",
  "fire.settings.monthlySpendOverride": "Monthly spend override",
  "fire.settings.monthlySpendOverrideHint":
    "Blank = derived from your recorded spending, or your recurring expenses if you have too little history.",
  "fire.settings.baristaIncome": "Barista part-time net income",
  "fire.settings.zusPension": "Expected ZUS pension",
  "fire.settings.zusPensionHint":
    "From your PUE ZUS statement, in today's money.",
  "fire.settings.includeHealthCost":
    "Include voluntary NFZ health cost while not working",
  "fire.settings.gainShare": "Gain share of withdrawals",
  "fire.settings.gainShareHint":
    "Share of each withdrawal that is investment gain rather than return of principal — used to gross up for Belka tax.",
  "fire.settings.emergencyMonths": "Emergency months",
  "fire.settings.save": "Save",
  "fire.settings.advanced": "Advanced settings",

  "fire.details.show": "Details",

  "fire.stat.fiNumber": "FI number",
  "fire.stat.fiNumberAt": "priced at age {age}",
  "fire.stat.progress": "Progress",
  "fire.stat.yearsToFi": "Years to FI",
  "fire.stat.yearsValue": "{years}y (age {age})",
  "fire.stat.notReachable": "Not reachable within 60 years at this rate",
  "fire.stat.coastReached": "Reached ✓",
  "fire.stat.coastNotYet": "Not yet",

  "fire.q1.title": "How much should I save?",
  "fire.q1.rateVsCurrent": "{required} of income needed, vs {current} saved now",
  "fire.q1.needTarget": "Set a target FI age above to see this.",
  "fire.q1.formula":
    "Level monthly contribution that grows your FI assets to the regular FI target by your target age, at your real return.",
  "fire.contributionSource.flows":
    "Based on money actually deposited into or withdrawn from your positions over the last year.",
  "fire.contributionSource.recorded":
    "Based on recorded income minus recorded spending.",
  "fire.contributionSource.none":
    "No contribution data yet — treated as 0.",

  "fire.q2.title": "How much do I need to earn?",
  "fire.q2.form": "Form",
  "fire.q2.monthly": "Monthly",
  "fire.q2.uop": "UoP (gross)",
  "fire.q2.b2bSkala": "B2B — skala (revenue)",
  "fire.q2.b2bLiniowy": "B2B — liniowy (revenue)",
  "fire.q2.b2bRyczalt": "B2B — ryczałt (revenue)",
  "fire.q2.linkTax": "Compare in full on the Tax page →",

  "fire.variants.title": "Variants",
  "fire.variant.lean.name": "Lean",
  "fire.variant.lean.hint": "{pct}% of your current spending.",
  "fire.variant.regular.name": "Regular",
  "fire.variant.regular.hint": "Your current lifestyle, indefinitely.",
  "fire.variant.fat.name": "Fat",
  "fire.variant.fat.hint": "{pct}% of your current spending.",
  "fire.variant.barista.name": "Barista",
  "fire.variant.barista.hint":
    "Part-time work covers part of spending and carries its own NFZ health cover.",
  "fire.variant.coast.name": "Coast",
  "fire.variant.coast.hint":
    "Stop contributing now — this pot still grows into your regular number by retirement age.",

  "fire.projection.title": "Projection",
  "fire.projection.portfolio": "Portfolio",
  "fire.projection.target": "FI target",
  "fire.projection.fiAge": "FI age",
  "fire.projection.ageLabel": "Age {age}",
  "fire.projection.empty": "Not enough data to project yet.",

  "fire.curve.title": "Savings rate → years to FI",
  "fire.curve.caption":
    "Your savings rate, not your returns, is the main lever.",
  "fire.curve.empty": "Add income and spending data to see this.",
  "fire.curve.you": "You",
  "fire.curve.unreachableBelow": "Below {rate}% FI is not reached within 60 years.",
  "fire.curve.years": "Years to FI",
  "fire.curve.yearsValue": "{years}y",

  "fire.levers.title": "Levers",
  "fire.levers.spendCut": "−1000/month spending",
  "fire.levers.incomeRaise": "+1000/month income",
  "fire.levers.yearsValue": "{years}y to FI",
  "fire.levers.baseline": "Baseline: {years}y to FI",
  "fire.levers.explanation":
    "Cutting spend does double duty — the freed money becomes saving too — while a raise of the same size only fills the contribution side. That is why the cut usually gets you there sooner.",

  "fire.bridge.title": "Bridge check",
  "fire.bridge.needed": "Needed until 60",
  "fire.bridge.projected": "Projected accessible",
  "fire.bridge.ok": "Covered ✓",
  "fire.bridge.notOk": "Shortfall before 60",
  "fire.bridge.wrapperHint":
    "IKE, PPK and OIPE money is penalised before age 60, and IKZE before 65 — none of it counts as accessible until then. OKI has no age lock, so it counts as accessible immediately.",
  "fire.bridge.unavailable":
    "Set a target FI age, or reach FI, to see this.",

  "fire.inputs.title": "Inputs",
  "fire.inputs.fiAssets": "FI assets",
  "fire.inputs.accessible": "Accessible",
  "fire.inputs.wrapped": "Wrapped (IKE/IKZE/PPK/OIPE)",
  "fire.inputs.excludedIlliquid": "Excluded (illiquid)",
  "fire.inputs.reserve": "Reserve",
  "fire.inputs.blendedNominal": "Blended nominal return",
  "fire.inputs.realReturn": "Real return used",
  "fire.inputs.inflation": "Inflation",
  "fire.inputs.monthlySpend": "Monthly spend",
  "fire.inputs.monthlyContribution": "Monthly contribution",
  "fire.inputs.sources": "Where these numbers come from",
  "fire.inputs.spendSource": "Spend: {source}",
  "fire.inputs.contributionSource": "Contribution: {source}",
  "fire.inputs.paramsYear": "Tax/ZUS parameters: {year}",
  "fire.source.override": "your override",
  "fire.source.recorded": "your recorded actuals",
  "fire.source.committed": "your recurring expenses",
  "fire.source.flows": "deposits/withdrawals on your positions",
  "fire.source.none": "no data yet",

  "fire.tile.title": "Retirement",
  "fire.tile.setup": "Set your birth year",
  "fire.tile.fiAt": "FI at {age}",

  "fire.pos.flowLabel": "Of which deposited (+) / withdrawn (−) ({unit})",
  "fire.pos.flowHint": "So market moves are not counted as saving or spending.",
  "fire.pos.flowHintQuantity":
    "Derived from the change in quantity unless entered — then in base currency. So market moves are not counted as saving or spending.",
  "fire.pos.invalidFlow": "Enter a valid amount, or leave it blank.",
  "fire.pos.flowRecorded": "Deposited / withdrawn: {value}",
  "fire.pos.historyFlow": "Deposited / withdrawn",

  // "Your money vs. growth" (see backend/src/services/growth.py). Kept
  // under its own `growth.` prefix, not `fire.pos.`, since it is shown on
  // /positions independently of the flow-entry form.
  "growth.yourMoney": "Your money",
  "growth.growth": "Growth",
  "growth.valueNow": "Value now",
  "growth.infoTip":
    "Your money = opening balance + deposits − withdrawals. Everything else counts as growth — interest, price changes, exchange rates.",
  "growth.lastUpdate": "Last update",
  "growth.lastUpdateLine": "{change} = paid in {flow} + growth {growth}",
  "growth.lastUpdateLineNoFlow": "{change} = nothing paid in entered + growth {growth}",
  "growth.historyColumn": "Growth",
  "growth.flowLabelWithPrevious":
    "How much did you pay in since the last update? (optional, {unit})",
  "growth.flowHintWithPrevious":
    "Leave empty if you added nothing — the whole change then counts as growth. A withdrawal is a negative number.",
  "growth.saveUpdate": "Save update",
  "growth.previewLine": "Change since last update {change} = paid in {paid} + growth {growth}",

  "fire.asset.addNew": "+ Add asset",
  "fire.asset.addTitle": "Add asset",
  "fire.asset.editTitle": "Edit asset",
  "fire.asset.editButton": "Edit",
  "fire.asset.archiveButton": "Archive",
  "fire.asset.archiveConfirm":
    "Archive “{name}”? It disappears from your assets; its history stays on the charts. Use this when you sold it or closed the account.",
  "fire.asset.deleteButton": "Delete permanently",
  "fire.asset.deleteConfirm":
    "Delete “{name}” permanently, with its whole history? The charts will look as if you never had it. Use this only for something added by mistake. This cannot be undone.",
  "fire.asset.archivedSection": "Archived ({n})",
  "fire.asset.archivedDate": "archived {date}",
  "fire.asset.restore": "Restore",
  "fire.asset.name": "Name",
  "fire.asset.kind": "Type",
  "fire.asset.kind.currency": "Cash / savings / investment",
  "fire.asset.kind.gold": "Gold",
  "fire.asset.kind.metal": "Precious metal",
  "fire.asset.kind.crypto": "Cryptocurrency",
  "fire.asset.catalogueMetal": "Which metal?",
  "fire.asset.catalogueCrypto": "Which coin?",
  "fire.asset.catalogueManual": "Other (enter manually)",
  "fire.asset.catalogueHint":
    "Fills in name, icon, category and risk profile — you can still rename it below.",
  "fire.asset.category": "Category",
  "fire.asset.categoryPlaceholder": "e.g. Stocks, Retirement",
  "fire.asset.icon": "Icon",
  "fire.asset.units": "Units",
  "fire.asset.unitsPlaceholder": "e.g. XAG, ETH",
  "fire.asset.unitsHint":
    "Metals: XAU, XAG, XPT or XPD (grams). Crypto: BTC, ETH, SOL, XRP or BNB.",
  "fire.asset.profile": "Risk profile",
  "fire.asset.profileAuto": "Auto (from category)",
  "fire.asset.wrapper": "Tax-advantaged account",
  "fire.asset.wrapperHint":
    "Tax-advantaged retirement account — penalised before 60 (IKZE: 65).",
  "fire.wrapper.none": "None",
  "fire.wrapper.ike": "IKE",
  "fire.wrapper.ikze": "IKZE",
  "fire.wrapper.ppk": "PPK",
  "fire.wrapper.oipe": "OIPE",
  "fire.wrapper.oki": "OKI",
  "fire.wrapper.oki.hint":
    "Osobiste Konto Inwestycyjne — from 2027; no Belka tax on up to 100 000 PLN of assets; withdraw any time.",
  "fire.wrapper.access.60": "Locked until 60",
  "fire.wrapper.access.65": "Locked until 65",
  "fire.wrapper.access.any": "Withdraw any time",

  "fire.inputs.accessibleHint": "Includes OKI — tax-advantaged, but not locked.",

  "fire.taxAdvantaged.title": "Tax-advantaged",
  "fire.taxAdvantaged.ofPortfolio": "of portfolio",
  "fire.taxAdvantaged.locked": "locked",
  "fire.taxAdvantaged.accessible": "accessible",
  "fire.taxAdvantaged.okiLimit": "{value} of the {limit} exemption limit",
  "fire.taxAdvantaged.okiFrom2027": "from 2027",
  "fire.taxAdvantaged.empty": "Nothing tax-advantaged yet — wrap a position on",
};

export const pl: Record<string, string> = {
  "fire.title": "Emerytura",
  "fire.subtitle":
    "Niezależność finansowa wyceniona na podstawie Twojego portfela, wydatków i dochodów.",
  "fire.disclaimer":
    "To model, nie prognoza: realne stopy zwrotu, inflacja i Twoje wydatki będą inne. Ma pokazać, które dźwignie mają znaczenie.",
  "fire.needBirthYear":
    "Podaj rok urodzenia poniżej, aby zobaczyć swoje liczby FIRE.",
  "fire.howComputed": "Jak to policzono",
  "fire.perMonth": "/mies.",

  "fire.settings.title": "Ustawienia",
  "fire.settings.birthYear": "Rok urodzenia",
  "fire.settings.targetFiAge": "Docelowy wiek FI",
  "fire.settings.targetFiAgeHint":
    "Opcjonalnie — zostaw puste, aby zobaczyć, kiedy osiągniesz FI przy obecnym tempie.",
  "fire.settings.retirementAge": "Wiek emerytalny",
  "fire.settings.retirementAgeHint":
    "Ustawowy wiek emerytalny ZUS: 65 lat dla mężczyzn, 60 dla kobiet. Podaj własny, jeśli się różni.",
  "fire.settings.swr": "Bezpieczna stopa wypłat",
  "fire.settings.swrHint":
    "3,5% zamiast amerykańskiej reguły 4%: to jeden portfel, nie cały indeks rynku, a polska historia inflacji bywała ostrzejsza, więc niższa stopa zostawia więcej marginesu.",
  "fire.settings.inflation": "Inflacja",
  "fire.settings.realReturnOverride": "Realna stopa zwrotu (nadpisanie)",
  "fire.settings.realReturnOverrideHint":
    "Puste = wyliczona z realnej stopy zwrotu Twojej obecnej alokacji.",
  "fire.settings.monthlySpendOverride": "Miesięczne wydatki (nadpisanie)",
  "fire.settings.monthlySpendOverrideHint":
    "Puste = wyliczone z zapisanych wydatków, a przy zbyt krótkiej historii — z wydatków cyklicznych.",
  "fire.settings.baristaIncome": "Dochód netto z pracy dorywczej (barista)",
  "fire.settings.zusPension": "Oczekiwana emerytura ZUS",
  "fire.settings.zusPensionHint":
    "Z Twojego zestawienia PUE ZUS, w dzisiejszych złotówkach.",
  "fire.settings.includeHealthCost":
    "Uwzględnij dobrowolną składkę zdrowotną NFZ w czasie niepracowania",
  "fire.settings.gainShare": "Udział zysku w wypłatach",
  "fire.settings.gainShareHint":
    "Część każdej wypłaty będąca zyskiem inwestycyjnym, a nie zwrotem kapitału — używana do przeliczenia podatku Belki.",
  "fire.settings.emergencyMonths": "Miesiące rezerwy",
  "fire.settings.save": "Zapisz",
  "fire.settings.advanced": "Ustawienia zaawansowane",

  "fire.details.show": "Szczegóły",

  "fire.stat.fiNumber": "Kwota FI",
  "fire.stat.fiNumberAt": "wyceniona w wieku {age} lat",
  "fire.stat.progress": "Postęp",
  "fire.stat.yearsToFi": "Lata do FI",
  "fire.stat.yearsValue": "{years} lat (wiek {age})",
  "fire.stat.notReachable": "Nieosiągalne w ciągu 60 lat przy tym tempie",
  "fire.stat.coastReached": "Osiągnięto ✓",
  "fire.stat.coastNotYet": "Jeszcze nie",

  "fire.q1.title": "Ile powinienem oszczędzać?",
  "fire.q1.rateVsCurrent":
    "Potrzeba {required} przychodu, a obecnie oszczędzasz {current}",
  "fire.q1.needTarget": "Ustaw docelowy wiek FI powyżej, aby to zobaczyć.",
  "fire.q1.formula":
    "Stała miesięczna wpłata, która przy Twojej realnej stopie zwrotu doprowadzi aktywa FI do celu regularnego do docelowego wieku.",
  "fire.contributionSource.flows":
    "Na podstawie kwot faktycznie wpłaconych lub wypłaconych z Twoich pozycji w ostatnim roku.",
  "fire.contributionSource.recorded":
    "Na podstawie zapisanego przychodu minus zapisane wydatki.",
  "fire.contributionSource.none":
    "Brak jeszcze danych o wpłatach — przyjęto 0.",

  "fire.q2.title": "Ile muszę zarabiać?",
  "fire.q2.form": "Forma",
  "fire.q2.monthly": "Miesięcznie",
  "fire.q2.uop": "UoP (brutto)",
  "fire.q2.b2bSkala": "B2B — skala (przychód)",
  "fire.q2.b2bLiniowy": "B2B — liniowy (przychód)",
  "fire.q2.b2bRyczalt": "B2B — ryczałt (przychód)",
  "fire.q2.linkTax": "Pełne porównanie na stronie Podatki →",

  "fire.variants.title": "Warianty",
  "fire.variant.lean.name": "Skromny",
  "fire.variant.lean.hint": "{pct}% Twoich obecnych wydatków.",
  "fire.variant.regular.name": "Regularny",
  "fire.variant.regular.hint": "Twój obecny styl życia, bezterminowo.",
  "fire.variant.fat.name": "Komfortowy",
  "fire.variant.fat.hint": "{pct}% Twoich obecnych wydatków.",
  "fire.variant.barista.name": "Barista",
  "fire.variant.barista.hint":
    "Praca dorywcza pokrywa część wydatków i niesie własne ubezpieczenie NFZ.",
  "fire.variant.coast.name": "Coast FIRE (rozpęd)",
  "fire.variant.coast.hint":
    "Przestań teraz dopłacać — ta kwota i tak dorośnie do celu regularnego do wieku emerytalnego.",

  "fire.projection.title": "Projekcja",
  "fire.projection.portfolio": "Portfel",
  "fire.projection.target": "Cel FI",
  "fire.projection.fiAge": "Wiek FI",
  "fire.projection.ageLabel": "Wiek {age}",
  "fire.projection.empty": "Za mało danych, aby to zaprojektować.",

  "fire.curve.title": "Stopa oszczędzania → lata do FI",
  "fire.curve.caption":
    "To stopa oszczędzania, nie stopa zwrotu, jest główną dźwignią.",
  "fire.curve.empty": "Dodaj dane o przychodach i wydatkach, aby to zobaczyć.",
  "fire.curve.you": "Ty",
  "fire.curve.unreachableBelow": "Przy stopie oszczędzania poniżej {rate}% niezależności finansowej nie osiąga się w ciągu 60 lat.",
  "fire.curve.years": "Lata do FI",
  "fire.curve.yearsValue": "{years} lat",

  "fire.levers.title": "Dźwignie",
  "fire.levers.spendCut": "−1000/mies. wydatków",
  "fire.levers.incomeRaise": "+1000/mies. przychodu",
  "fire.levers.yearsValue": "{years} lat do FI",
  "fire.levers.baseline": "Punkt odniesienia: {years} lat do FI",
  "fire.levers.explanation":
    "Cięcie wydatków działa podwójnie — zwolnione pieniądze stają się też oszczędnością — podczas gdy taka sama podwyżka zasila tylko wpłatę. Dlatego cięcie zwykle przybliża FI szybciej.",

  "fire.bridge.title": "Sprawdzenie mostu",
  "fire.bridge.needed": "Potrzebne do 60. roku życia",
  "fire.bridge.projected": "Prognozowane dostępne",
  "fire.bridge.ok": "Pokryte ✓",
  "fire.bridge.notOk": "Brak pokrycia przed 60. rokiem życia",
  "fire.bridge.wrapperHint":
    "Środki na IKE, PPK i OIPE są karane przed 60. rokiem życia, a na IKZE przed 65. — do tego czasu nie liczą się jako dostępne. OKI nie ma blokady wiekowej, więc liczy się jako dostępne od razu.",
  "fire.bridge.unavailable":
    "Ustaw docelowy wiek FI albo osiągnij FI, aby to zobaczyć.",

  "fire.inputs.title": "Dane wejściowe",
  "fire.inputs.fiAssets": "Aktywa FI",
  "fire.inputs.accessible": "Dostępne",
  "fire.inputs.wrapped": "W opakowaniu (IKE/IKZE/PPK/OIPE)",
  "fire.inputs.excludedIlliquid": "Wyłączone (niepłynne)",
  "fire.inputs.reserve": "Rezerwa",
  "fire.inputs.blendedNominal": "Nominalna stopa zwrotu portfela",
  "fire.inputs.realReturn": "Użyta realna stopa zwrotu",
  "fire.inputs.inflation": "Inflacja",
  "fire.inputs.monthlySpend": "Miesięczne wydatki",
  "fire.inputs.monthlyContribution": "Miesięczna wpłata",
  "fire.inputs.sources": "Skąd biorą się te liczby",
  "fire.inputs.spendSource": "Wydatki: {source}",
  "fire.inputs.contributionSource": "Wpłata: {source}",
  "fire.inputs.paramsYear": "Parametry podatkowe/ZUS: {year}",
  "fire.source.override": "Twoje nadpisanie",
  "fire.source.recorded": "Twoje zapisane dane",
  "fire.source.committed": "Twoje wydatki cykliczne",
  "fire.source.flows": "wpłaty/wypłaty na Twoich pozycjach",
  "fire.source.none": "brak jeszcze danych",

  "fire.tile.title": "Emerytura",
  "fire.tile.setup": "Podaj rok urodzenia",
  "fire.tile.fiAt": "FI w wieku {age} lat",

  "fire.pos.flowLabel": "W tym wpłacono (+) / wypłacono (−) ({unit})",
  "fire.pos.flowHint":
    "Dzięki temu ruchy rynku nie liczą się jako oszczędzanie ani wydawanie.",
  "fire.pos.flowHintQuantity":
    "Wyliczane ze zmiany ilości, chyba że podane — wtedy w walucie bazowej. Dzięki temu ruchy rynku nie liczą się jako oszczędzanie ani wydawanie.",
  "fire.pos.invalidFlow": "Podaj poprawną kwotę albo zostaw puste.",
  "fire.pos.flowRecorded": "Wpłata / wypłata: {value}",
  "fire.pos.historyFlow": "Wpłata / wypłata",

  "growth.yourMoney": "Twoje wpłaty",
  "growth.growth": "Wzrost",
  "growth.valueNow": "Wartość teraz",
  "growth.infoTip":
    "Twoje wpłaty = saldo początkowe + wpłaty − wypłaty. Wszystko inne liczy się jako wzrost — odsetki, zmiany cen, kursy walut.",
  "growth.lastUpdate": "Ostatnia aktualizacja",
  "growth.lastUpdateLine": "{change} = wpłacono {flow} + wzrost {growth}",
  "growth.lastUpdateLineNoFlow": "{change} = nic nie wpłacono + wzrost {growth}",
  "growth.historyColumn": "Wzrost",
  "growth.flowLabelWithPrevious":
    "Ile wpłaciłeś(-aś) od ostatniej aktualizacji? (opcjonalnie, {unit})",
  "growth.flowHintWithPrevious":
    "Zostaw puste, jeśli nic nie dopłacałeś(-aś) — wtedy cała zmiana liczy się jako wzrost. Wypłata to liczba ujemna.",
  "growth.saveUpdate": "Zapisz aktualizację",
  "growth.previewLine": "Zmiana od ostatniej aktualizacji {change} = wpłacono {paid} + wzrost {growth}",

  "fire.asset.addNew": "+ Dodaj aktywo",
  "fire.asset.addTitle": "Dodaj aktywo",
  "fire.asset.editTitle": "Edytuj aktywo",
  "fire.asset.editButton": "Edytuj",
  "fire.asset.archiveButton": "Archiwizuj",
  "fire.asset.archiveConfirm":
    "Zarchiwizować „{name}”? Zniknie z listy aktywów, a jego historia zostanie na wykresach. Użyj tego, gdy aktywo sprzedałeś(-aś) albo zamknąłeś(-aś) konto.",
  "fire.asset.deleteButton": "Usuń na stałe",
  "fire.asset.deleteConfirm":
    "Usunąć „{name}” na stałe, razem z całą historią? Wykresy będą wyglądać, jakbyś nigdy go nie miał(-a). Używaj tylko dla czegoś dodanego przez pomyłkę. Tego nie da się cofnąć.",
  "fire.asset.archivedSection": "Zarchiwizowane ({n})",
  "fire.asset.archivedDate": "zarchiwizowane {date}",
  "fire.asset.restore": "Przywróć",
  "fire.asset.name": "Nazwa",
  "fire.asset.kind": "Rodzaj",
  "fire.asset.kind.currency": "Gotówka / oszczędności / inwestycja",
  "fire.asset.kind.gold": "Złoto",
  "fire.asset.kind.metal": "Metal szlachetny",
  "fire.asset.kind.crypto": "Kryptowaluta",
  "fire.asset.catalogueMetal": "Który metal?",
  "fire.asset.catalogueCrypto": "Która kryptowaluta?",
  "fire.asset.catalogueManual": "Inne (wpisz ręcznie)",
  "fire.asset.catalogueHint":
    "Uzupełnia nazwę, ikonę, kategorię i profil ryzyka — nazwę można potem zmienić.",
  "fire.asset.category": "Kategoria",
  "fire.asset.categoryPlaceholder": "np. Akcje, Emerytura",
  "fire.asset.icon": "Ikona",
  "fire.asset.units": "Jednostki",
  "fire.asset.unitsPlaceholder": "np. XAG, ETH",
  "fire.asset.unitsHint":
    "Metale: XAU, XAG, XPT lub XPD (gramy). Krypto: BTC, ETH, SOL, XRP lub BNB.",
  "fire.asset.profile": "Profil ryzyka",
  "fire.asset.profileAuto": "Automatycznie (wg kategorii)",
  "fire.asset.wrapper": "Konto z ulgą podatkową",
  "fire.asset.wrapperHint":
    "Konto emerytalne z ulgą podatkową — karane przed 60. rokiem życia (IKZE: 65.).",
  "fire.wrapper.none": "Brak",
  "fire.wrapper.ike": "IKE",
  "fire.wrapper.ikze": "IKZE",
  "fire.wrapper.ppk": "PPK",
  "fire.wrapper.oipe": "OIPE",
  "fire.wrapper.oki": "OKI",
  "fire.wrapper.oki.hint":
    "Osobiste Konto Inwestycyjne — dostępne od 2027; bez podatku Belki od aktywów do 100 000 PLN; wypłata w każdej chwili.",
  "fire.wrapper.access.60": "Zablokowane do 60. roku życia",
  "fire.wrapper.access.65": "Zablokowane do 65. roku życia",
  "fire.wrapper.access.any": "Wypłata w każdej chwili",

  "fire.inputs.accessibleHint": "W tym OKI — z ulgą podatkową, ale bez blokady.",

  "fire.taxAdvantaged.title": "Na optymalizacji podatkowej",
  "fire.taxAdvantaged.ofPortfolio": "portfela",
  "fire.taxAdvantaged.locked": "zablokowane",
  "fire.taxAdvantaged.accessible": "dostępne",
  "fire.taxAdvantaged.okiLimit": "{value} z limitu zwolnienia {limit}",
  "fire.taxAdvantaged.okiFrom2027": "od 2027",
  "fire.taxAdvantaged.empty": "Nic jeszcze nie jest na optymalizacji podatkowej — oznacz pozycję opakowaniem na",
};
