/** Recovery code, locked-data screen, notification opt-in and birth-year
 *  strings (LockedGate, RecoveryPrompt, RecoveryCodeFlow, RestoreForm and the
 *  matching Settings cards), kept out of lib/i18n.ts so feature work does not
 *  collide there - same pattern as lib/strings/pdfReport.ts. */
export const en: Record<string, string> = {
  // ---- shared flow (create -> show once -> confirm)
  "rec.flow.start": "Create my recovery code",
  "rec.flow.starting": "Creating…",
  "rec.flow.notNow": "Not now",
  "rec.flow.codeLabel": "Your recovery code",
  "rec.flow.warnTitle": "This is the only time you will see this code.",
  "rec.flow.warnBody":
    "It cannot be shown again. If you lose both this code and your sign-in identity, your data is lost permanently - nobody, including us, can recover it. Store the code offline: in a password manager or printed on paper. Do not keep it in this browser.",
  "rec.flow.copy": "Copy",
  "rec.flow.copied": "Copied",
  "rec.flow.copyFailed": "Could not copy - select the code and copy it by hand.",
  "rec.flow.download": "Download .txt",
  "rec.flow.saved": "I have saved it.",
  "rec.flow.typeBack": "Type the code back to confirm",
  "rec.flow.typeBackHint":
    "This proves you stored a readable copy. Paste from your password manager if you saved it there.",
  "rec.flow.mismatch": "That does not match the code shown above yet.",
  "rec.flow.confirm": "Confirm",
  "rec.flow.confirming": "Confirming…",
  "rec.flow.discardConfirm":
    "Leave without confirming? The code shown here will be lost and cannot be shown again. You can create a new one afterwards.",
  "rec.flow.fileHeader": "MyFinance recovery code",
  "rec.flow.fileCreated": "Created: {date}",
  "rec.flow.fileBody":
    "Keep this file offline (password manager or printed). Anyone with this code can re-attach your data to a new sign-in; if you lose it together with your sign-in identity, the data cannot be recovered.",
  "rec.err.generic": "Something went wrong. Please try again.",
  "rec.err.network": "Could not reach the server. Check your connection and try again.",
  "rec.err.exists":
    "A confirmed recovery code already exists. Reload the page and use \"Create a new code\" in Settings to replace it.",
  "rec.err.mismatch": "The server says that does not match the code it issued. Check it and try again.",

  // ---- the blocking prompt
  "rec.prompt.title": "Save a recovery code",
  "rec.prompt.body":
    "Your financial data is encrypted with a key tied to your sign-in. If your sign-in identity ever changes, your next sign-in would open a new, empty account and the old data could not be unlocked. A one-time recovery code lets you re-attach it.",
  "rec.prompt.body2":
    "You will see the code once. Write it down or save it in a password manager - not in this browser.",
  "rec.prompt.unconfirmed":
    "A recovery code was created earlier but never confirmed, so it may not have been saved. Creating a new one replaces it.",

  // ---- locked screen
  "rec.locked.title": "Your data is locked",
  "rec.locked.body":
    "This sign-in is not the one your data was protected with, so it cannot be opened right now. Nothing has been deleted. Enter the recovery code you saved to re-attach your data to this sign-in, or sign out and use the original account.",
  "rec.locked.signOut": "Sign out",

  // ---- restore form (locked screen and Settings)
  "rec.restore.label": "Recovery code",
  "rec.restore.placeholder": "MF1-XXXXX-XXXXX-…",
  "rec.restore.button": "Restore",
  "rec.restore.working": "Restoring…",
  "rec.restore.invalid":
    "That code was not accepted. Check it for typing mistakes and try again.",
  "rec.restore.exists":
    "This account already holds data of its own, so it cannot be overwritten by a restore. Sign in with the account you want to keep.",
  "rec.restore.rateLimited":
    "Too many attempts. Try again in {time}.",
  "rec.restore.rateLimitedNoTime":
    "Too many attempts. Wait a while before trying again.",
  "rec.restore.done": "Restored. Reloading…",

  // ---- Settings: recovery card
  "rec.set.title": "Recovery code",
  "rec.set.subtitle":
    "A one-time code that re-attaches your encrypted data if your sign-in identity ever changes.",
  "rec.set.loading": "Checking status…",
  "rec.set.statusNone": "No recovery code has been created yet.",
  "rec.set.statusUnconfirmed":
    "A code was created on {date} but never confirmed. Create a new one to replace it.",
  "rec.set.statusConfirmed": "A recovery code was confirmed on {date}.",
  "rec.set.statusConfirmedNoDate": "A recovery code is confirmed.",
  "rec.set.create": "Create a code",
  "rec.set.createNew": "Create a new code",
  "rec.set.replaceConfirm":
    "Create a new recovery code? Your current code will stop working as soon as the new one is created. Make sure you can store the new one safely.",
  "rec.set.confirmedMsg": "Recovery code confirmed.",
  "rec.set.restoreTitle": "Restore from a recovery code",
  "rec.set.restoreBody":
    "Use this if you just signed in with a new identity and your wallet looks empty. The code re-attaches your old data to this sign-in. It only works on an account that holds no data of its own.",

  // ---- Settings: notifications card
  "rec.contact.title": "Notifications",
  "rec.contact.subtitle":
    "Opt in to hear from MyFinance by e-mail later.",
  "rec.contact.body":
    "Opting in only records your preference for the future - no e-mail is sent yet. The address is read by the server from your sign-in; this page never sees or sends it. Notifications will never contain any of your financial data.",
  "rec.contact.on": "You are opted in.",
  "rec.contact.off": "You are not opted in.",
  "rec.contact.optIn": "Opt in",
  "rec.contact.optOut": "Opt out",
  "rec.contact.noEmail":
    "Your sign-in has no verified e-mail address, so you cannot opt in.",
  "rec.contact.loadFailed": "Could not load notification settings.",

  // ---- Settings: birth year card
  "rec.birth.title": "Birth year (optional)",
  "rec.birth.subtitle":
    "Stored encrypted. Only used for age-based analysis later.",
  "rec.birth.label": "Birth year",
  "rec.birth.clear": "Clear",
  "rec.birth.invalid": "Enter a year between 1900 and {max}.",
  "rec.birth.saved": "Saved.",
  "rec.birth.cleared": "Cleared.",
};

export const pl: Record<string, string> = {
  // ---- shared flow (create -> show once -> confirm)
  "rec.flow.start": "Utwórz mój kod odzyskiwania",
  "rec.flow.starting": "Tworzenie…",
  "rec.flow.notNow": "Nie teraz",
  "rec.flow.codeLabel": "Twój kod odzyskiwania",
  "rec.flow.warnTitle": "To jedyny raz, kiedy widzisz ten kod.",
  "rec.flow.warnBody":
    "Nie da się go wyświetlić ponownie. Jeśli stracisz zarówno ten kod, jak i swoją tożsamość logowania, dane przepadną bezpowrotnie - nikt, także my, nie jest w stanie ich odzyskać. Przechowuj kod offline: w menedżerze haseł lub wydrukowany na papierze. Nie zapisuj go w tej przeglądarce.",
  "rec.flow.copy": "Kopiuj",
  "rec.flow.copied": "Skopiowano",
  "rec.flow.copyFailed": "Nie udało się skopiować - zaznacz kod i skopiuj go ręcznie.",
  "rec.flow.download": "Pobierz .txt",
  "rec.flow.saved": "Zapisałem(-am) go.",
  "rec.flow.typeBack": "Przepisz kod, aby potwierdzić",
  "rec.flow.typeBackHint":
    "To potwierdza, że masz czytelną kopię. Jeśli zapisałeś(-aś) kod w menedżerze haseł, możesz go stamtąd wkleić.",
  "rec.flow.mismatch": "To jeszcze nie zgadza się z kodem pokazanym powyżej.",
  "rec.flow.confirm": "Potwierdź",
  "rec.flow.confirming": "Potwierdzanie…",
  "rec.flow.discardConfirm":
    "Wyjść bez potwierdzenia? Kod pokazany tutaj zostanie utracony i nie da się go wyświetlić ponownie. Później możesz utworzyć nowy.",
  "rec.flow.fileHeader": "Kod odzyskiwania MyFinance",
  "rec.flow.fileCreated": "Utworzono: {date}",
  "rec.flow.fileBody":
    "Przechowuj ten plik offline (menedżer haseł lub wydruk). Każdy, kto ma ten kod, może przypisać Twoje dane do nowego logowania; jeśli stracisz go razem z tożsamością logowania, danych nie da się odzyskać.",
  "rec.err.generic": "Coś poszło nie tak. Spróbuj ponownie.",
  "rec.err.network": "Nie udało się połączyć z serwerem. Sprawdź połączenie i spróbuj ponownie.",
  "rec.err.exists":
    "Potwierdzony kod odzyskiwania już istnieje. Odśwież stronę i użyj w Ustawieniach opcji „Utwórz nowy kod”, aby go zastąpić.",
  "rec.err.mismatch": "Serwer twierdzi, że to nie zgadza się z wydanym kodem. Sprawdź go i spróbuj ponownie.",

  // ---- the blocking prompt
  "rec.prompt.title": "Zapisz kod odzyskiwania",
  "rec.prompt.body":
    "Twoje dane finansowe są szyfrowane kluczem powiązanym z Twoim logowaniem. Jeśli Twoja tożsamość logowania kiedykolwiek się zmieni, następne logowanie otworzy nowe, puste konto, a starych danych nie da się odblokować. Jednorazowy kod odzyskiwania pozwala je ponownie przypisać.",
  "rec.prompt.body2":
    "Kod zobaczysz tylko raz. Zapisz go na papierze lub w menedżerze haseł - nie w tej przeglądarce.",
  "rec.prompt.unconfirmed":
    "Kod odzyskiwania został utworzony wcześniej, ale nigdy nie został potwierdzony, więc mógł nie zostać zapisany. Utworzenie nowego zastąpi go.",

  // ---- locked screen
  "rec.locked.title": "Twoje dane są zablokowane",
  "rec.locked.body":
    "To logowanie nie jest tym, którym zabezpieczono Twoje dane, więc nie można ich teraz otworzyć. Nic nie zostało usunięte. Wpisz zapisany kod odzyskiwania, aby ponownie przypisać dane do tego logowania, albo wyloguj się i użyj pierwotnego konta.",
  "rec.locked.signOut": "Wyloguj",

  // ---- restore form (locked screen and Settings)
  "rec.restore.label": "Kod odzyskiwania",
  "rec.restore.placeholder": "MF1-XXXXX-XXXXX-…",
  "rec.restore.button": "Przywróć",
  "rec.restore.working": "Przywracanie…",
  "rec.restore.invalid":
    "Ten kod nie został zaakceptowany. Sprawdź, czy nie ma w nim literówek, i spróbuj ponownie.",
  "rec.restore.exists":
    "To konto ma już własne dane, więc przywracanie nie może ich nadpisać. Zaloguj się na konto, które chcesz zachować.",
  "rec.restore.rateLimited":
    "Zbyt wiele prób. Spróbuj ponownie za {time}.",
  "rec.restore.rateLimitedNoTime":
    "Zbyt wiele prób. Odczekaj chwilę przed kolejną próbą.",
  "rec.restore.done": "Przywrócono. Ponowne ładowanie…",

  // ---- Settings: recovery card
  "rec.set.title": "Kod odzyskiwania",
  "rec.set.subtitle":
    "Jednorazowy kod, który ponownie przypisuje Twoje zaszyfrowane dane, jeśli Twoja tożsamość logowania kiedykolwiek się zmieni.",
  "rec.set.loading": "Sprawdzanie stanu…",
  "rec.set.statusNone": "Nie utworzono jeszcze kodu odzyskiwania.",
  "rec.set.statusUnconfirmed":
    "Kod został utworzony {date}, ale nigdy nie został potwierdzony. Utwórz nowy, aby go zastąpić.",
  "rec.set.statusConfirmed": "Kod odzyskiwania został potwierdzony {date}.",
  "rec.set.statusConfirmedNoDate": "Kod odzyskiwania jest potwierdzony.",
  "rec.set.create": "Utwórz kod",
  "rec.set.createNew": "Utwórz nowy kod",
  "rec.set.replaceConfirm":
    "Utworzyć nowy kod odzyskiwania? Obecny kod przestanie działać, gdy tylko powstanie nowy. Upewnij się, że możesz bezpiecznie go zachować.",
  "rec.set.confirmedMsg": "Kod odzyskiwania potwierdzony.",
  "rec.set.restoreTitle": "Przywróć za pomocą kodu odzyskiwania",
  "rec.set.restoreBody":
    "Użyj tego, jeśli właśnie zalogowałeś(-aś) się nową tożsamością, a portfel wygląda na pusty. Kod ponownie przypisuje Twoje stare dane do tego logowania. Działa tylko na koncie, które nie ma własnych danych.",

  // ---- Settings: notifications card
  "rec.contact.title": "Powiadomienia",
  "rec.contact.subtitle":
    "Zgódź się, aby w przyszłości otrzymywać wiadomości od MyFinance e-mailem.",
  "rec.contact.body":
    "Zgoda zapisuje jedynie Twoją preferencję na przyszłość - na razie nie wysyłamy żadnych e-maili. Adres odczytuje serwer z Twojego logowania; ta strona nigdy go nie widzi ani nie wysyła. Powiadomienia nigdy nie będą zawierać Twoich danych finansowych.",
  "rec.contact.on": "Wyrażono zgodę.",
  "rec.contact.off": "Nie wyrażono zgody.",
  "rec.contact.optIn": "Wyrażam zgodę",
  "rec.contact.optOut": "Wycofaj zgodę",
  "rec.contact.noEmail":
    "Twoje logowanie nie ma zweryfikowanego adresu e-mail, więc nie można wyrazić zgody.",
  "rec.contact.loadFailed": "Nie udało się wczytać ustawień powiadomień.",

  // ---- Settings: birth year card
  "rec.birth.title": "Rok urodzenia (opcjonalnie)",
  "rec.birth.subtitle":
    "Przechowywany w formie zaszyfrowanej. Używany tylko do analiz opartych na wieku w przyszłości.",
  "rec.birth.label": "Rok urodzenia",
  "rec.birth.clear": "Wyczyść",
  "rec.birth.invalid": "Podaj rok z zakresu 1900–{max}.",
  "rec.birth.saved": "Zapisano.",
  "rec.birth.cleared": "Wyczyszczono.",
};
