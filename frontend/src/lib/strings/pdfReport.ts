/** Wallet PDF report strings (PdfReportCard, on the Assets page), kept out
 *  of lib/i18n.ts so feature work does not collide there - same pattern as
 *  lib/strings/insights.ts. Reuses "ins.job.*" for the generate/poll
 *  progress copy (queued/running/translating/retry): the AI commentary here
 *  runs on the exact same LLM queue as the Insights tabs, so the wording
 *  should read the same. */
export const en: Record<string, string> = {
  "pdf.title": "PDF report",
  "pdf.subtitle":
    "Download your wallet, its allocation and its efficiency for a chosen period as a PDF.",
  "pdf.period": "Period",
  "pdf.period.1m": "Last month",
  "pdf.period.3m": "Last quarter",
  "pdf.period.ytd": "Year to date",
  "pdf.period.12m": "Last 12 months",
  "pdf.period.all": "All time",
  "pdf.includeAi": "Include AI commentary",
  "pdf.aiInfo":
    "A short written commentary, produced by the same local model as the Insights tabs, narrating the numbers already in this report. It never adds figures of its own - every number is checked against the report's own data, and anything that could not be checked is shown with a warning. Clearly labelled in the PDF as AI-generated, with the date it was written.",
  "pdf.aiUnavailable": "Turn on Insights in Settings to add AI commentary.",
  "pdf.aiNotConfigured": "No model is configured for AI commentary - the PDF will still download without it.",
  "pdf.download": "Download PDF",
  "pdf.preparing": "Preparing the PDF…",
  "pdf.groundingWarning":
    "Some figures in the AI commentary could not be matched to the report's own numbers and are flagged inside the PDF:",
  "pdf.downloadFailed": "Could not create the PDF",
};

export const pl: Record<string, string> = {
  "pdf.title": "Raport PDF",
  "pdf.subtitle":
    "Pobierz swój portfel, jego alokację i efektywność za wybrany okres jako plik PDF.",
  "pdf.period": "Okres",
  "pdf.period.1m": "Ostatni miesiąc",
  "pdf.period.3m": "Ostatni kwartał",
  "pdf.period.ytd": "Od początku roku",
  "pdf.period.12m": "Ostatnie 12 miesięcy",
  "pdf.period.all": "Cały okres",
  "pdf.includeAi": "Dołącz komentarz AI",
  "pdf.aiInfo":
    "Krótki komentarz pisemny, wygenerowany przez ten sam lokalny model co zakładki Analizy, komentujący liczby już zawarte w tym raporcie. Nie dodaje własnych liczb - każda liczba jest sprawdzana względem danych raportu, a te, których nie udało się zweryfikować, są oznaczone ostrzeżeniem. W PDF wyraźnie oznaczony jako wygenerowany przez AI, wraz z datą powstania.",
  "pdf.aiUnavailable": "Włącz Analizy w Ustawieniach, aby dodać komentarz AI.",
  "pdf.aiNotConfigured": "Nie skonfigurowano modelu dla komentarza AI - PDF pobierze się i tak, bez niego.",
  "pdf.download": "Pobierz PDF",
  "pdf.preparing": "Przygotowywanie PDF…",
  "pdf.groundingWarning":
    "Niektórych liczb w komentarzu AI nie udało się dopasować do liczb w raporcie - są oznaczone w PDF:",
  "pdf.downloadFailed": "Nie udało się utworzyć PDF",
};
