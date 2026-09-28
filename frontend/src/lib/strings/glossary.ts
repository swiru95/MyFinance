/** Plain-language glossary backing the shared <InfoTip> component
 *  (components/InfoTip.tsx). Kept out of lib/i18n.ts for the same reason as
 *  the other lib/strings/*.ts files - merged into the main dictionaries
 *  there. Every key is prefixed `gloss.` and holds a self-contained 1-2
 *  sentence explanation, since an InfoTip has no other copy around it to
 *  lean on. Where a longer *Hint/*Note string already covers the same
 *  ground (e.g. fire.settings.swrHint), these are deliberately shorter -
 *  the InfoTip is the quick answer, not a duplicate of the full hint. */
export const en: Record<string, string> = {
  "gloss.fixedMonthlyCosts": "Your recurring monthly expenses - rent, subscriptions, loan payments and the like. If you run a JDG, it also includes that month's ZUS and health contributions.",
  "gloss.kup": "KUP (tax-deductible costs) is a fixed monthly amount - or a share of pay for creative work - subtracted from your income before tax is calculated on it.",
  "gloss.pit2": "PIT-2 is filed with your employer so the tax-free amount is applied every month (a smaller PIT advance) instead of only once, in your annual return.",
  "gloss.taxForm": "Skala, liniowy and ryczałt are the three ways a business's income can be taxed: skala is the standard 12/32% scale, liniowy a flat 19% with no tax-free amount, and ryczałt a flat rate on revenue with no cost deductions.",
  "gloss.zusStage": "New businesses step through ZUS stages that grow over time: ulga na start (no social contributions for 6 months), a preferential base, then Mały ZUS Plus, before settling on full ZUS.",
  "gloss.ppk": "PPK is a workplace retirement scheme: you contribute a share of gross pay, your employer adds their own share on top, and the state chips in too.",
  "gloss.ike": "IKE is a personal retirement account: gains inside it are free of Belka tax if you withdraw after age 60.",
  "gloss.ikze": "IKZE is a personal retirement account with an upfront income-tax deduction on what you pay in; withdrawals after age 65 are taxed at a flat 10%.",
  "gloss.oipe": "OIPE is a pan-European personal pension product, with the same age-60 lock as IKE.",
  "gloss.oki": "OKI (Osobiste Konto Inwestycyjne) is a new account type available from 2027, with no age lock and no Belka tax on up to 100 000 PLN of assets.",
  "gloss.swr": "The safe withdrawal rate is the share of your portfolio you plan to spend each year without running it down - 3.5% here is more cautious than the often-cited US 4% rule.",
  "gloss.coastFire": "Coast FIRE means you already have enough invested that, left untouched, it will grow into your full retirement number by retirement age - so you could stop contributing and just cover today's spending.",
  "gloss.baristaFire": "Barista FIRE means part-time or lower-stress work covers part of your spending (and its own health insurance), while your portfolio covers the rest.",
  "gloss.leanFatFire": "Lean and Fat FIRE are the same retirement, just priced at less (lean) or more (fat) than your current monthly spending.",
  "gloss.effectiveSpend": "Income minus how your portfolio actually changed in value - a market drop counts the same as money spent, and a market gain offsets spending, even though neither is a purchase.",
  "gloss.cushion": "Your safe, easy-to-sell assets divided by your fixed monthly costs - how many months you could cover if income stopped today.",
  "gloss.savingsRate": "The share of income left over after spending - the main lever for reaching financial independence sooner.",
  "gloss.taxEnvelope": "VAT and tax/ZUS money that has already landed in your account but legally isn't yours yet - set it aside so a due date doesn't catch you short.",
  "gloss.realReturn": "Your investment growth after subtracting inflation - what your money actually gains in buying power, not just in złoty.",
  "gloss.belka": "Poland's flat 19% tax on investment gains - interest, dividends and capital gains outside a tax-advantaged account.",
  "gloss.fireAcronym": "FIRE stands for Financial Independence, Retire Early. This page prices out when your own portfolio could cover your spending indefinitely.",
  "gloss.statedTolerance": "How much investment risk you said, in the questionnaire, that you're willing to accept.",
  "gloss.capacityTolerance": "How much risk your finances could absorb without real hardship - based on your income stability, dependants and safety cushion, not on what you'd prefer.",
  "gloss.revealedTolerance": "How much risk your actual holdings show you taking, regardless of what you said or could afford.",

  // Same explanations as above, keyed for lib/wrappers.ts's
  // wrapperGlossaryKey() so the Positions wrapper badge (an InfoTip, not a
  // `title` attribute - see pages/positions.tsx) can look one up per wrapper.
  "gloss.wrapper.ike": "IKE is a personal retirement account: gains inside it are free of Belka tax if you withdraw after age 60.",
  "gloss.wrapper.ikze": "IKZE is a personal retirement account with an upfront income-tax deduction on what you pay in; withdrawals after age 65 are taxed at a flat 10%.",
  "gloss.wrapper.ppk": "PPK is a workplace retirement scheme: you contribute a share of gross pay, your employer adds their own share on top, and the state chips in too.",
  "gloss.wrapper.oipe": "OIPE is a pan-European personal pension product, with the same age-60 lock as IKE.",
  "gloss.wrapper.oki": "OKI (Osobiste Konto Inwestycyjne) is a new account type available from 2027, with no age lock and no Belka tax on up to 100 000 PLN of assets.",
};

export const pl: Record<string, string> = {
  "gloss.fixedMonthlyCosts": "Twoje cykliczne miesięczne wydatki - czynsz, subskrypcje, raty i podobne. Jeśli prowadzisz JDG, obejmuje to też tegomiesięczny ZUS i składkę zdrowotną.",
  "gloss.kup": "KUP (koszty uzyskania przychodu) to stała miesięczna kwota - albo część wynagrodzenia za pracę twórczą - odejmowana od dochodu, zanim naliczy się od niego podatek.",
  "gloss.pit2": "PIT-2 to oświadczenie złożone u pracodawcy, dzięki któremu kwota wolna od podatku jest stosowana co miesiąc (mniejsza zaliczka na PIT), a nie dopiero raz, w rocznym zeznaniu.",
  "gloss.taxForm": "Skala, liniowy i ryczałt to trzy sposoby opodatkowania dochodu z działalności: skala to standardowa skala 12/32%, liniowy to płaski podatek 19% bez kwoty wolnej, a ryczałt to stawka od przychodu bez odliczania kosztów.",
  "gloss.zusStage": "Nowe firmy przechodzą przez kolejne etapy ZUS, które rosną w czasie: ulga na start (brak składek społecznych przez 6 miesięcy), podstawa preferencyjna, potem Mały ZUS Plus, aż do pełnego ZUS.",
  "gloss.ppk": "PPK to pracowniczy program emerytalny: Ty wpłacasz część wynagrodzenia brutto, pracodawca dokłada swoją część, a państwo dopłaca dodatkowo.",
  "gloss.ike": "IKE to indywidualne konto emerytalne: zyski na nim są zwolnione z podatku Belki, jeśli wypłacisz środki po 60. roku życia.",
  "gloss.ikze": "IKZE to indywidualne konto zabezpieczenia emerytalnego z odliczeniem wpłat od dochodu już teraz; wypłaty po 65. roku życia są opodatkowane ryczałtowo stawką 10%.",
  "gloss.oipe": "OIPE to ogólnoeuropejski produkt emerytalny, z taką samą blokadą do 60. roku życia jak IKE.",
  "gloss.oki": "OKI (Osobiste Konto Inwestycyjne) to nowy rodzaj konta dostępny od 2027 roku, bez blokady wiekowej i bez podatku Belki od aktywów do 100 000 zł.",
  "gloss.swr": "Bezpieczna stopa wypłat to część portfela, którą planujesz wydawać rocznie bez jego uszczuplania - 3,5% jest tu ostrożniejsze niż często cytowana amerykańska reguła 4%.",
  "gloss.coastFire": "Coast FIRE oznacza, że masz już zainwestowaną kwotę, która sama, bez dalszych wpłat, dorośnie do docelowego kapitału emerytalnego - możesz więc przestać dopłacać i pokrywać tylko bieżące wydatki.",
  "gloss.baristaFire": "Barista FIRE oznacza, że praca na część etatu lub mniej stresująca pokrywa część wydatków (i własne ubezpieczenie zdrowotne), a resztę pokrywa portfel.",
  "gloss.leanFatFire": "Lean i Fat FIRE to ta sama niezależność finansowa, tylko wyceniona na mniej (lean) lub więcej (fat) niż obecne miesięczne wydatki.",
  "gloss.effectiveSpend": "Przychód minus rzeczywista zmiana wartości portfela - spadek na rynku liczy się tak samo jak wydane pieniądze, a wzrost obniża wynik, mimo że żadne z nich nie jest zakupem.",
  "gloss.cushion": "Twoje bezpieczne, łatwo dostępne aktywa podzielone przez stałe koszty miesięczne - ile miesięcy wydatków pokryjesz, gdyby dochód nagle ustał.",
  "gloss.savingsRate": "Część przychodu, która zostaje po wydatkach - główna dźwignia, żeby szybciej osiągnąć niezależność finansową.",
  "gloss.taxEnvelope": "Pieniądze z VAT oraz podatków/ZUS, które już wpłynęły na konto, ale formalnie jeszcze nie są Twoje - odkładaj je na bok, żeby termin płatności Cię nie zaskoczył.",
  "gloss.realReturn": "Wzrost inwestycji po odjęciu inflacji - ile Twoje pieniądze faktycznie zyskują siły nabywczej, a nie tylko złotówek.",
  "gloss.belka": "Polski płaski podatek 19% od zysków kapitałowych - odsetek, dywidend i zysków ze sprzedaży poza kontem z ulgą podatkową.",
  "gloss.fireAcronym": "FIRE (Financial Independence, Retire Early) oznacza niezależność finansową i możliwość wcześniejszego zakończenia pracy zarobkowej. Ta strona liczy, kiedy Twój portfel sam pokryje wydatki bez dalszej pracy.",
  "gloss.statedTolerance": "Ile ryzyka inwestycyjnego zadeklarowałeś/aś w ankiecie, że jesteś skłonny/a zaakceptować.",
  "gloss.capacityTolerance": "Ile ryzyka Twoje finanse realnie udźwigną bez poważnych konsekwencji — na podstawie stabilności dochodu, osób na utrzymaniu i poduszki bezpieczeństwa, a nie tego, co byś preferował/a.",
  "gloss.revealedTolerance": "Ile ryzyka pokazują Twoje faktyczne inwestycje, niezależnie od deklaracji czy możliwości.",

  "gloss.wrapper.ike": "IKE to indywidualne konto emerytalne: zyski na nim są zwolnione z podatku Belki, jeśli wypłacisz środki po 60. roku życia.",
  "gloss.wrapper.ikze": "IKZE to indywidualne konto zabezpieczenia emerytalnego z odliczeniem wpłat od dochodu już teraz; wypłaty po 65. roku życia są opodatkowane ryczałtowo stawką 10%.",
  "gloss.wrapper.ppk": "PPK to pracowniczy program emerytalny: Ty wpłacasz część wynagrodzenia brutto, pracodawca dokłada swoją część, a państwo dopłaca dodatkowo.",
  "gloss.wrapper.oipe": "OIPE to ogólnoeuropejski produkt emerytalny, z taką samą blokadą do 60. roku życia jak IKE.",
  "gloss.wrapper.oki": "OKI (Osobiste Konto Inwestycyjne) to nowy rodzaj konta dostępny od 2027 roku, bez blokady wiekowej i bez podatku Belki od aktywów do 100 000 zł.",
};
