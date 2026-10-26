// Checks the statement import (src/lib/import, compiled to .import-check by `npm run check:import`) on made-up
// statements shaped like real exports: names, accounts and amounts below are invented.
const assert = require("node:assert/strict");
const dir = process.cwd() + "/.import-check/lib/import";
const csv = require(dir + "/csv.js");
const { findDebits } = require(dir + "/statement.js");
const { matchByAmount, planMonths } = require(dir + "/match.js");
const { parseAmount, parseDate, decodeText } = require(dir + "/parse.js");

let n = 0;
const check = (name, fn) => {
  fn();
  n++;
  console.log("ok", name);
};

check("amounts", () => {
  assert.equal(parseAmount("-1 234,56"), -1234.56);
  assert.equal(parseAmount("1.234,56 PLN"), 1234.56);
  assert.equal(parseAmount("−45,00"), -45);
  assert.equal(parseAmount("45,00-"), -45);
  assert.equal(parseAmount("1,234.50"), 1234.5);
  assert.ok(isNaN(parseAmount("abc")));
});

check("dates", () => {
  assert.equal(parseDate("26.10.2026"), "2026-10-26");
  assert.equal(parseDate("2026-10-26"), "2026-10-26");
  assert.equal(parseDate("31.02.2026"), "");
});

// ING-like: metadata with the holder's accounts above the header, several "Currency" columns, a hold in its own
// column, a transfer to the holder's own savings account, Windows-1250 bytes.
const OWN = "12 1050 0000 1000 0000 0000 0001";
const SAVINGS = "34 1050 0000 1000 0000 0000 0002";
const ING = [
  '"Lista transakcji";;;;',
  '"Wybrane rachunki:";',
  `"Konto Testowe (PLN)";;"${OWN}";`,
  `"Konto Oszczędnościowe (PLN)";;"${SAVINGS}";`,
  "",
  '"Data transakcji";"Data księgowania";"Dane kontrahenta";"Tytuł";"Nr rachunku";"Szczegóły";"Kwota transakcji (waluta rachunku)";"Waluta";"Kwota blokady";"Waluta";"Saldo po transakcji";"Waluta"',
  '2026-10-02;2026-10-03;"SKLEP SPOŻYWCZY";"Płatność kartą";"";"TR.KART";-45,99;PLN;;;1 954,01;PLN',
  '2026-10-03;;"KAWIARNIA";"Płatność kartą";"";"";;;-12,50;PLN;1 954,01;PLN',
  `2026-10-04;2026-10-04;"JAN TESTOWY";"Oszczędności";"${SAVINGS.replace(/ /g, "")}";"PRZELEW";-500,00;PLN;;;1 454,01;PLN`,
  '2026-10-05;2026-10-05;"PRACODAWCA SP. Z O.O.";"Wynagrodzenie";"98 1140 0000 0000 0000 0000 0003";"PRZELEW";5 000,00;PLN;;;6 454,01;PLN',
  '2026-10-06;2026-10-06;"APTEKA";"Płatność kartą";"";"TR.KART";-1 234,56;PLN;;;5 219,45;PLN',
  "",
  '"Dokument ma charakter informacyjny."',
].join("\r\n");

// Windows-1250 bytes for the Polish letters used above (the rest is ASCII).
const CP1250 = { ą: 0xb9, ć: 0xe6, ę: 0xea, ł: 0xb3, ń: 0xf1, ó: 0xf3, ś: 0x9c, ź: 0x9f, ż: 0xbf, Ł: 0xa3, Ś: 0x8c, Ż: 0xaf };
const encode = (s) => Uint8Array.from([...s].map((c) => (c.charCodeAt(0) < 128 ? c.charCodeAt(0) : CP1250[c] ?? 0x3f)));

check("csv: ING-like export in Windows-1250", () => {
  const text = decodeText(encode(ING).buffer);
  assert.ok(text.includes("Oszczędności"));
  const table = csv.readCsv(text);
  assert.equal(table.data.length, 5);
  assert.equal(table.own.size, 2);
  const m = csv.guessHeuristic(table);
  assert.deepEqual([m.date, m.amount, m.currency], [0, 6, 7]);
  assert.ok(csv.mappingFits(m, table));
  const out = csv.applyMapping(m, table, "PLN");
  // The salary is incoming and the hold has no booked amount: both left out.
  assert.equal(out.skipped, 2);
  assert.deepEqual(
    out.rows.map((r) => [r.date, r.amount, r.transfer, r.checked]),
    [
      ["2026-10-02", 45.99, false, true],
      ["2026-10-04", 500, true, false],
      ["2026-10-06", 1234.56, false, true],
    ],
  );
  assert.match(out.rows[0].note, /SKLEP SPOŻYWCZY · Płatność kartą/);
});

// Debit/credit columns, money out printed positive, the statement's own account on every row (as some banks do).
const SPLIT = [
  "Data operacji;Opis operacji;Rachunek;Obciążenia;Uznania",
  `01.10.2026;Biedronka 123;${OWN};89,90;`,
  `02.10.2026;Przelew przychodzący;${OWN};;1 200,00`,
  `03.10.2026;Orlen;${OWN};250,00;`,
].join("\n");

check("csv: debit and credit columns, own account on every row", () => {
  const table = csv.readCsv("Rachunek: " + OWN + "\n" + SPLIT);
  const m = csv.guessHeuristic(table);
  assert.equal(m.amount, -1);
  assert.equal(m.debit, 3);
  assert.ok(csv.mappingFits(m, table));
  const out = csv.applyMapping(m, table, "PLN");
  // A model's mapping that also names the description column "amount" reads the same rows.
  const wrong = csv.applyMapping({ ...m, amount: 1 }, table, "PLN");
  assert.deepEqual(wrong.rows.map((r) => r.amount), [89.9, 250]);
  assert.deepEqual(
    out.rows.map((r) => [r.date, r.amount, r.transfer]),
    [
      ["2026-10-01", 89.9, false],
      ["2026-10-03", 250, false],
    ],
  );
});

// mBank-like: "#" before every header name, a period line ("01.10.2026;31.10.2026") above the header that has dates
// but no amount, a trailing ";" on every line.
const MBANK = [
  "mBank S.A.;",
  "#Za okres:;",
  "01.10.2026;31.10.2026;",
  "#dla rachunków:;",
  `eKonto - ${OWN.replace(/ /g, "")};`,
  "",
  "#Data operacji;#Opis operacji;#Rachunek;#Kategoria;#Kwota;",
  '2026-10-03;"ŻABKA Z1234 K.1 WARSZAWA  ZAKUP PRZY UŻYCIU KARTY";"eKonto 1234";"Żywność";-23,47 PLN;',
  '2026-10-04;"PRZELEW WŁASNY";"eKonto 1234";"Oszczędności";-300,00 PLN;',
  '2026-10-05;"WPŁATA";"eKonto 1234";"Wpływy";1 000,00 PLN;',
].join("\r\n");

check("csv: mBank-like, # headers and a period line", () => {
  const table = csv.readCsv(MBANK);
  assert.equal(table.header[0], "#Data operacji");
  assert.equal(table.data.length, 3);
  const out = csv.applyMapping(csv.guessHeuristic(table), table, "PLN");
  assert.deepEqual(out.rows.map((r) => [r.date, r.amount]), [["2026-10-03", 23.47], ["2026-10-04", 300]]);
  assert.match(out.rows[0].note, /^ŻABKA Z1234/);
});

// PKO-like: the merchant is in unnamed columns with labels; "Opis transakcji" is generic.
const PKO = [
  '"Data operacji","Data waluty","Typ transakcji","Kwota","Waluta","Saldo po transakcji","Opis transakcji","","","",""',
  '"2026-10-06","2026-10-07","Płatność kartą","-49.99","PLN","+7450.01","Tytuł:  000498849 74230786127190310660541 ","Lokalizacja: Adres: SKLEP TESTOWY 12 Miasto: TORUN Kraj: POLSKA","Data wykonania operacji: 2026-10-06","Oryginalna kwota operacji: 49.99","Numer karty: 425125******0000"',
  '"2026-10-08","2026-10-08","Przelew z rachunku","-120.00","PLN","+7330.01","Rachunek odbiorcy: 00 0000 0000 0000 0000 0000 0000","Nazwa odbiorcy: JAN TESTOWY","Tytuł: Zwrot za bilety","",""',
].join("\n");

check("csv: PKO-like, merchant from labelled columns", () => {
  const table = csv.readCsv(PKO);
  const out = csv.applyMapping(csv.guessHeuristic(table), table, "PLN");
  assert.deepEqual(
    out.rows.map((r) => [r.date, r.amount, r.note]),
    [
      ["2026-10-06", 49.99, "SKLEP TESTOWY 12 TORUN"],
      ["2026-10-08", 120, "JAN TESTOWY · Zwrot za bilety"],
    ],
  );
});

// A PDF's text lines (as lib/import/pdfText.ts gives them): a transaction over several lines, a balance after each.
const PDF = [
  "Lista transakcji",
  `Konto Testowe  ${OWN}`,
  `Konto Oszczędnościowe  ${SAVINGS}`,
  "Data  Kontrahent  Tytuł  Kwota  Saldo",
  "SKLEP SPOŻYWCZY  Konto Testowe",
  "02.10.2026  Płatność kartą  TR.KART",
  "-45,99 PLN",
  "03.10.2026  Nr tr.: 000000000000000001",
  "1 954,01 PLN",
  "PRACODAWCA SP. Z O.O.",
  "05.10.2026  Wynagrodzenie  5 000,00 PLN",
  "6 954,01 PLN",
  "JAN TESTOWY  Konto Testowe",
  "06.10.2026  Oszczędności  -500,00 PLN",
  SAVINGS.replace(/ /g, ""),
  "6 454,01 PLN",
  "Saldo końcowe: -0,00 PLN",
];

check("pdf: signed amounts, dates above, own-account transfer, totals ignored", () => {
  const out = findDebits(PDF, "PLN");
  assert.deepEqual(
    out.rows.map((r) => [r.date, r.amount, r.transfer, r.checked]),
    [
      ["2026-10-02", 45.99, false, true],
      ["2026-10-06", 500, true, false],
    ],
  );
  assert.match(out.rows[0].note, /SKLEP SPOŻYWCZY/);
  assert.ok(!/45,99|02\.10\.2026/.test(out.rows[0].note));
});

const row = (key, date, amount, note, extra = {}) => ({
  key, date, amount, currency: "PLN", note, commitment: null, checked: true, unverified: false, transfer: false, ...extra,
});
const commitment = (expense_id, name, amount) => ({ expense_id, name, category: "", amount, currency: "PLN", paid: true });

check("match: exact amounts, a shared word breaks ties, one payment per expense", () => {
  const rows = [
    row("a", "2026-10-02", 49.99, "SKLEP"),
    row("b", "2026-10-05", 49.99, "NETFLIX.COM"),
    row("c", "2026-10-10", 2500, "Czynsz październik"),
    row("d", "2026-11-10", 2500, "Czynsz listopad"),
    row("e", "2026-10-11", 2500, "unticked", { checked: false }),
  ];
  const byMonth = {
    "2026-10": [commitment(1, "Netflix", 49.99), commitment(2, "Czynsz", 2500), commitment(3, "Prąd", 180)],
    "2026-11": [commitment(2, "Czynsz", 2500)],
  };
  const out = matchByAmount(rows, byMonth);
  // Czynsz is paid in October and again in November: matched in both months.
  assert.deepEqual(out.map((r) => r.commitment), [null, 1, 2, 2, null]);
});

check("plan: paid per expense, other spending, partial months, other currencies left out", () => {
  const rows = [
    row("a", "2026-09-28", 10, "x"),
    row("b", "2026-10-01", 2500, "Czynsz", { commitment: 2 }),
    row("c", "2026-10-15", 30.5, "Sklep"),
    row("d", "2026-10-20", 19.5, "Kawa"),
    row("e", "2026-10-21", 12, "unticked", { checked: false }),
    row("f", "2026-10-22", 40, "EUR shop", { currency: "EUR" }),
    row("g", "2026-11-03", 5, "y"),
  ];
  const { months, foreign } = planMonths(rows, "PLN");
  assert.equal(foreign, 1);
  assert.deepEqual(
    months.map((m) => [m.month, m.partial, [...m.paid], m.other]),
    [
      ["2026-09", true, [], 10],
      ["2026-10", false, [[2, 2500]], 50],
      ["2026-11", true, [], 5],
    ],
  );
});

console.log(`check-import: ${n} checks passed`);
