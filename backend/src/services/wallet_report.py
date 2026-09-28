"""The wallet PDF report: current holdings, allocation, a value-over-time
chart, and "your money vs growth" efficiency for a chosen period - the same
figures the Assets and Dashboard pages already show, assembled into one
downloadable PDF (see routes/report_pdf.py).

build_snapshot() is the single source of numbers for both the PDF's own
tables and the optional AI commentary (services/insights.py's "wallet_pdf"
kind): the model is only ever shown what render_snapshot() below prints, and
services/grounding.py checks its text against this same dict afterwards, so
nothing that ends up on the page can be a figure the model invented.

fpdf2 (pure Python; Pillow/fonttools are its only real dependencies, both
ship manylinux wheels) renders the PDF, with DejaVu Sans embedded from
assets/fonts/ - Polish diacritics (ą ć ę ł ń ó ś ź ż) must render correctly
regardless of what fonts happen to be installed in the container, so this
never falls back to a "system" font.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from sqlalchemy.orm import Session

from .efficiency import PERIOD_LABELS, period_efficiency

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Ported from frontend/src/lib/i18n.ts's DATA_PL so the PDF's category names
# read the same in Polish as the rest of the app - kept in sync by hand, the
# same way glossary/category strings elsewhere in the backend prompts are
# (see services/insights.py's _RUNG_LABELS for the same pattern).
_CATEGORY_PL = {
    "Cash": "Gotówka",
    "Gold": "Złoto",
    "Stocks": "Akcje",
    "TFI Funds": "Fundusze TFI",
    "National Bonds": "Obligacje skarbowe",
    "Watches": "Zegarki",
    "Bitcoin": "Bitcoin",
    "Solana": "Solana",
    "Savings": "Oszczędności",
    "Silver": "Srebro",
    "Ethereum": "Ethereum",
    "TFI": "TFI",
    "Bonds": "Obligacje",
    "Metals": "Metale",
    "Crypto": "Kryptowaluty",
    "Retirement": "Emerytura",
    "Fixed Assets": "Środki trwałe",
    "Receivables": "Należności",
    "Uncategorised": "Bez kategorii",
}

_PERIOD_LABELS_PL = {
    "1m": "Ostatni miesiąc",
    "3m": "Ostatni kwartał",
    "ytd": "Od początku roku",
    "12m": "Ostatnie 12 miesięcy",
    "all": "Cały okres",
}

_L = {
    "en": {
        "title": "Wallet report",
        "generatedOn": "Generated on {date}",
        "dataAsOf": "Data as of {time}",
        "period": "Period: {period}",
        "walletSection": "Wallet",
        "totalValue": "Total value",
        "byCategory": "Allocation by asset class",
        "byWrapper": "Tax-advantaged wrappers (IKE / IKZE / PPK / OKI)",
        "taxAdvantaged": "Total in tax-advantaged wrappers",
        "valueOverTime": "Value over time",
        "noHistory": "No history yet.",
        "noHoldings": "No holdings recorded.",
        "efficiencySection": "Efficiency",
        "colAsset": "Asset",
        "colCategory": "Class",
        "colDeposits": "Your deposits",
        "colGrowth": "Growth",
        "colGrowthPct": "Return",
        "colValue": "Value now",
        "total": "Total",
        "reconciliation": (
            "{opening} at the start of the period, {deposits} in deposits "
            "and withdrawals, {growth} in growth = {value} now."
        ),
        "annualizedReturn": "Annualised return (XIRR)",
        "annualizedNote": (
            "Money-weighted, accounting for when each deposit or "
            "withdrawal happened - not comparable to a plain return % "
            "over a period other than exactly one year."
        ),
        "annualizedUnavailable": "Not available for this period (needs at least one deposit or withdrawal and a positive value).",
        "aiSection": "AI-generated commentary",
        "aiGeneratedOn": "Generated on {date} - narrates the figures above only.",
        "aiWarning": (
            "The following figure(s) in this text could not be matched to "
            "the numbers above and may be inaccurate:"
        ),
        "disclaimer": (
            "MyFinance is a tool for tracking your own finances. It is not "
            "investment, tax or legal advice. See the terms of use "
            "(version {version})."
        ),
        "page": "Page {n} of {total}",
    },
    "pl": {
        "title": "Raport portfela",
        "generatedOn": "Wygenerowano {date}",
        "dataAsOf": "Dane na {time}",
        "period": "Okres: {period}",
        "walletSection": "Portfel",
        "totalValue": "Wartość całkowita",
        "byCategory": "Alokacja według klasy aktywów",
        "byWrapper": "Konta z ulgą podatkową (IKE / IKZE / PPK / OKI)",
        "taxAdvantaged": "Suma na kontach z ulgą podatkową",
        "valueOverTime": "Wartość w czasie",
        "noHistory": "Brak jeszcze historii.",
        "noHoldings": "Brak zarejestrowanych aktywów.",
        "efficiencySection": "Efektywność",
        "colAsset": "Aktywo",
        "colCategory": "Klasa",
        "colDeposits": "Twoje wpłaty",
        "colGrowth": "Wzrost",
        "colGrowthPct": "Zwrot",
        "colValue": "Wartość teraz",
        "total": "Razem",
        "reconciliation": (
            "{opening} na początku okresu, {deposits} wpłat i wypłat, "
            "{growth} wzrostu = {value} teraz."
        ),
        "annualizedReturn": "Zwrot roczny (XIRR)",
        "annualizedNote": (
            "Zwrot ważony przepływami pieniężnymi, uwzględniający moment "
            "każdej wpłaty i wypłaty - nieporównywalny wprost ze zwykłym "
            "procentem zwrotu za okres inny niż dokładnie rok."
        ),
        "annualizedUnavailable": "Niedostępne dla tego okresu (potrzebna co najmniej jedna wpłata lub wypłata oraz dodatnia wartość).",
        "aiSection": "Komentarz wygenerowany przez AI",
        "aiGeneratedOn": "Wygenerowano {date} - komentuje wyłącznie powyższe liczby.",
        "aiWarning": (
            "Poniższych liczb w tym tekście nie udało się dopasować do "
            "liczb powyżej - mogą być niedokładne:"
        ),
        "disclaimer": (
            "MyFinance to narzędzie do samodzielnego śledzenia własnych "
            "finansów. Nie stanowi doradztwa inwestycyjnego, podatkowego "
            "ani prawnego. Zobacz zasady korzystania (wersja {version})."
        ),
        "page": "Strona {n} z {total}",
    },
}


def _translate_category(name: str, language: str) -> str:
    if language != "pl":
        return name
    return _CATEGORY_PL.get(name, name)


def _period_label(period: str, language: str) -> str:
    if language == "pl":
        return _PERIOD_LABELS_PL.get(period, period)
    return PERIOD_LABELS.get(period, period)


def _fmt_num(value: float, language: str, digits: int = 2) -> str:
    """"12,345.67" in English punctuation, "12 345,67" in Polish - the same
    grouping/decimal convention Intl.NumberFormat("pl-PL") uses on the
    frontend (see frontend/src/lib/api.ts::fmtMoney)."""
    sign = "-" if value < 0 else ""
    text = f"{abs(value):,.{digits}f}"
    if language == "pl":
        text = text.replace(",", "\x00").replace(".", ",").replace("\x00", " ")
    return sign + text


def _fmt_money(value: float, currency: str, language: str) -> str:
    return f"{_fmt_num(value, language)} {currency}"


def _fmt_signed_money(value: float, currency: str, language: str) -> str:
    sign = "+" if value > 0 else ("-" if value < 0 else "")
    return f"{sign}{_fmt_num(abs(value), language)} {currency}"


def _fmt_pct(value: float | None, language: str) -> str:
    if value is None:
        return "-"
    sign = "+" if value > 0 else ("-" if value < 0 else "")
    return f"{sign}{_fmt_num(abs(value) * 100, language, digits=1)}%"


# --- Snapshot (numbers only - shared by the PDF and the AI prompt) --------

def build_snapshot(db: Session, period: str) -> dict:
    """Everything the PDF (and the optional AI commentary) is allowed to
    show, assembled from the same endpoints the Assets/Dashboard pages read
    - so the report can never disagree with what is on screen.

    Frozen at the moment this is called: routes/report_pdf.py calls this
    fresh for an immediate (no-AI) download, but reuses an already-stored
    "wallet_pdf" Insight's own `snapshot` dict unchanged when one is given -
    see that module for why (crypto/metal prices move between generating
    the AI commentary and downloading the PDF, and the two must describe
    the same numbers).
    """
    from ..routes.helpers import now_in
    from ..routes.statistics import allocation as allocation_route
    from ..routes.statistics import value_over_time as value_over_time_route

    now = now_in(db)
    today = now.date()
    alloc = allocation_route(db=db)
    efficiency = period_efficiency(db, period, today)

    return {
        "generated_on": today.isoformat(),
        # Full local timestamp, not just the date - the PDF's "data as of"
        # line (see build_pdf) needs the time too, especially once this
        # snapshot is read back from a stored Insight rather than built
        # fresh.
        "generated_at": now.isoformat(),
        "period": period,
        "period_label": PERIOD_LABELS.get(period, period),
        "base_currency": alloc["base_currency"],
        "total_value": alloc["total"],
        "holdings": [
            {
                "name": i["name"],
                "category": i["category"],
                "value": i["value"],
                "percent": i["percent"],
                "wrapper": i.get("wrapper", ""),
            }
            for i in sorted(alloc["items"], key=lambda i: i["value"], reverse=True)
        ],
        "by_category": alloc["by_category"],
        "by_wrapper": alloc["by_wrapper"],
        "tax_advantaged_total": alloc["tax_advantaged_total"],
        "tax_advantaged_percent": alloc["tax_advantaged_percent"],
        "value_over_time": _chart_points(db, efficiency["since"], today, alloc["total"]),
        "efficiency": efficiency,
    }


def _chart_points(db: Session, since_iso: str | None, today, live_total: float) -> list[dict]:
    """The value-over-time chart's points, scoped to the report's own
    period and ending on today's live total.

    /api/statistics/value-over-time walks *stored* snapshot values (a
    crypto/metal holding's value as of the day it was last touched, carried
    forward - see that endpoint's own docstring), which is the right thing
    for a chart of history but disagrees with the live-repriced headline
    total the moment a held crypto/metal price has moved since the last
    snapshot - exactly what made the chart end on a different number than
    "Total value" above it. This scopes the series to the report's own
    `since` (None = whole history, same as the efficiency table) and
    replaces (or adds) today's point with `live_total`, so the chart's last
    point is always the same number as the headline total.
    """
    from ..routes.statistics import value_over_time as value_over_time_route

    rows = value_over_time_route(by="total", db=db)["rows"]
    if since_iso is not None:
        rows = [r for r in rows if r["date"] >= since_iso]
    points = [{"date": r["date"], "total": r["total"]} for r in rows]

    today_iso = today.isoformat()
    if points and points[-1]["date"] == today_iso:
        points[-1] = {"date": today_iso, "total": live_total}
    else:
        # No snapshot was ever recorded today - append today's live total as
        # its own point so the chart still ends on the headline number
        # rather than stopping at the last day something was touched.
        points.append({"date": today_iso, "total": live_total})
    return points


def render_snapshot(snap: dict) -> str:
    """The snapshot as text for the AI prompt - prose-shaped tables, same
    reasoning as services/assessment.render_snapshot: a model reads figures
    laid out this way more reliably than the same numbers as raw JSON."""
    cur = snap["base_currency"]

    def money(v):
        return f"{v:,.2f} {cur}"

    out: list[str] = []
    out.append(f"# Wallet as of {snap['generated_on']}\n")
    out.append(f"Total value: {money(snap['total_value'])}\n")

    out.append("## By asset class")
    for c in snap["by_category"]:
        out.append(f"- {c['category']}: {money(c['value'])}, {c['percent']:.1f}%")
    out.append("")

    if snap["by_wrapper"]:
        out.append("## Tax-advantaged wrappers")
        for w in snap["by_wrapper"]:
            out.append(f"- {w['wrapper'].upper()}: {money(w['value'])}, {w['percent']:.1f}%")
        out.append("")

    eff = snap["efficiency"]
    out.append(f"## Efficiency - {eff['period_label']} ({eff['since'] or 'inception'} to {eff['until']})")
    out.append(
        "\"Deposits\" is money you put in or took out over the period; "
        "\"growth\" is everything else the value did - market movement, "
        "interest, price changes.\n"
    )
    out.append("| Asset | Class | Deposits | Growth | Return |")
    out.append("|---|---|---|---|---|")
    for a in eff["assets"]:
        pct = f"{a['growth_pct'] * 100:.1f}%" if a["growth_pct"] is not None else "n/a"
        out.append(
            f"| {a['name']} | {a['category']} | {money(a['contributed'])} "
            f"| {money(a['growth'])} | {pct} |"
        )
    t = eff["total"]
    total_pct = f"{t['growth_pct'] * 100:.1f}%" if t["growth_pct"] is not None else "n/a"
    out.append(f"| **Total** | | {money(t['contributed'])} | {money(t['growth'])} | {total_pct} |")
    out.append("")
    if eff["annualized_return"] is not None:
        out.append(f"Annualised return (XIRR) for this period: {eff['annualized_return'] * 100:.2f}%")
    else:
        out.append("Annualised return (XIRR): not available for this period.")
    return "\n".join(out)


# --- PDF rendering ----------------------------------------------------

def _format_local_dt(value: "str | datetime") -> str:
    """`value` is either an ISO-format string (a snapshot's own
    `generated_at`, read back from a stored Insight) or a datetime already
    converted to the zone it should display in (routes/report_pdf.py
    converts an Insight's `created_at` before handing it here) - both
    format the same way, with no further zone conversion: both are already
    the wall-clock time to print."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime("%Y-%m-%d %H:%M")


class _ReportPDF(FPDF):
    """FPDF subclass only to own the disclaimer footer - everything else is
    built with plain calls against a plain FPDF instance elsewhere."""

    def __init__(self, language: str, terms_version: int):
        super().__init__(format="A4")
        self._language = language
        self._terms_version = terms_version
        self.set_auto_page_break(auto=True, margin=22)

    def footer(self) -> None:
        labels = _L[self._language]
        self.set_y(-18)
        self.set_font("DejaV", "", 8)
        self.set_text_color(110, 110, 110)
        self.set_draw_color(210, 210, 210)
        self.line(15, self.get_y(), self.w - 15, self.get_y())
        self.ln(1.5)
        self.multi_cell(
            0, 4, labels["disclaimer"].format(version=self._terms_version), align="L"
        )
        self.set_xy(-40, -12)
        self.cell(25, 4, labels["page"].format(n=self.page_no(), total="{nb}"), align="R")


def _register_fonts(pdf: FPDF) -> None:
    pdf.add_font("DejaV", "", str(FONT_DIR / "DejaVuSans.ttf"))
    pdf.add_font("DejaV", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))


def _heading(pdf: FPDF, text: str, size: int = 13) -> None:
    pdf.set_font("DejaV", "B", size)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 9, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)


def _table(pdf: FPDF, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
    pdf.set_font("DejaV", "B", 9)
    pdf.set_fill_color(235, 237, 242)
    for h, w in zip(headers, widths):
        pdf.cell(w, 7, h, border=0, fill=True)
    pdf.ln(7)
    pdf.set_font("DejaV", "", 9)
    for i, row in enumerate(rows):
        pdf.set_fill_color(249, 250, 252) if i % 2 else pdf.set_fill_color(255, 255, 255)
        for cell, w in zip(row, widths):
            pdf.cell(w, 6.5, cell, border=0, fill=True)
        pdf.ln(6.5)


def _value_over_time_chart(pdf: FPDF, points: list[dict], currency: str, language: str) -> None:
    labels = _L[language]
    if len(points) < 2:
        pdf.set_font("DejaV", "", 9)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 6, labels["noHistory"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(20, 20, 20)
        return

    x0, y0 = pdf.get_x(), pdf.get_y()
    w, h = 170, 55
    values = [p["total"] for p in points]
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0

    pdf.set_draw_color(200, 200, 200)
    pdf.rect(x0, y0, w, h)
    # Two horizontal gridlines (25%/75%) so the chart reads without a full
    # numeric axis - the min/max labels below carry the real numbers.
    for frac in (0.25, 0.5, 0.75):
        gy = y0 + h - frac * h
        pdf.set_draw_color(230, 230, 230)
        pdf.line(x0, gy, x0 + w, gy)

    def scale(i: int, v: float) -> tuple[float, float]:
        px = x0 + (i / (len(points) - 1)) * w
        py = y0 + h - ((v - lo) / span) * h
        return px, py

    pdf.set_draw_color(59, 91, 219)
    prev = None
    for i, p in enumerate(points):
        pt = scale(i, p["total"])
        if prev is not None:
            pdf.line(prev[0], prev[1], pt[0], pt[1])
        prev = pt

    # Y-axis min/max labels, drawn just inside the plot's top-left and
    # bottom-left corners - the series' actual highest/lowest value, which
    # need not be the first or last point (a wallet can dip mid-period and
    # recover). Small font + a plain fill behind it so the line underneath
    # never runs through the text.
    pdf.set_font("DejaV", "", 7)
    pdf.set_text_color(90, 90, 90)
    pdf.set_fill_color(255, 255, 255)
    pdf.set_xy(x0 + 1, y0 + 0.8)
    pdf.cell(w - 2, 3.4, _fmt_money(hi, currency, language), fill=True)
    pdf.set_xy(x0 + 1, y0 + h - 4.2)
    pdf.cell(w - 2, 3.4, _fmt_money(lo, currency, language), fill=True)

    # X-axis: just the date range below the plot - the values themselves
    # are on the y-axis now, and pairing them with the first/last date used
    # to wrongly imply the min/max happened exactly there.
    pdf.set_xy(x0, y0 + h + 2)
    pdf.set_font("DejaV", "", 8)
    pdf.cell(w / 2, 4, points[0]["date"])
    pdf.set_xy(x0 + w / 2, y0 + h + 2)
    pdf.cell(w / 2, 4, points[-1]["date"], align="R")
    pdf.set_text_color(20, 20, 20)
    pdf.set_xy(x0, y0 + h + 8)


def build_pdf(
    snap: dict,
    language: str,
    terms_version: int,
    ai_content: str | None = None,
    ai_created_at: datetime | None = None,
    ai_ungrounded: list[str] | None = None,
) -> bytes:
    """Render the wallet report PDF. `ai_content` (already the finished,
    grounded text of a "wallet_pdf" Insight - see services/insights.py) is
    embedded only when given; without it the report is exactly the
    deterministic wallet + efficiency sections, generated with nothing to
    wait for."""
    language = language if language in _L else "en"
    labels = _L[language]
    cur = snap["base_currency"]

    pdf = _ReportPDF(language, terms_version)
    _register_fonts(pdf)
    pdf.alias_nb_pages()
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    # "Data as of" - the snapshot's own `generated_at`, not the moment this
    # PDF happens to be rendered: with ai_insight_id given (see
    # routes/report_pdf.py), that can be noticeably earlier than "now", and
    # the reader needs to know which it is, not just assume today.
    data_as_of = _format_local_dt(snap.get("generated_at") or snap["generated_on"])
    pdf.set_font("DejaV", "B", 20)
    pdf.cell(0, 12, labels["title"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("DejaV", "", 10)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(
        0, 6,
        labels["dataAsOf"].format(time=data_as_of)
        + "   ·   "
        + labels["period"].format(period=_period_label(snap["period"], language)),
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.set_text_color(20, 20, 20)
    pdf.ln(4)

    # --- Wallet -------------------------------------------------------
    _heading(pdf, labels["walletSection"])
    pdf.set_font("DejaV", "B", 15)
    pdf.cell(0, 8, f"{labels['totalValue']}: {_fmt_money(snap['total_value'], cur, language)}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    pdf.set_font("DejaV", "B", 11)
    pdf.cell(0, 7, labels["byCategory"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if snap["by_category"]:
        _table(
            pdf,
            [labels["colCategory"], labels["colValue"], "%"],
            [
                [
                    _translate_category(c["category"], language),
                    _fmt_money(c["value"], cur, language),
                    _fmt_num(c["percent"], language, digits=1) + "%",
                ]
                for c in snap["by_category"]
            ],
            [90, 55, 25],
        )
    else:
        pdf.set_font("DejaV", "", 9)
        pdf.cell(0, 6, labels["noHoldings"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    if snap["by_wrapper"]:
        pdf.set_font("DejaV", "B", 11)
        pdf.cell(0, 7, labels["byWrapper"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        _table(
            pdf,
            [labels["colCategory"], labels["colValue"], "%"],
            [
                [w["wrapper"].upper(), _fmt_money(w["value"], cur, language),
                 _fmt_num(w["percent"], language, digits=1) + "%"]
                for w in snap["by_wrapper"]
            ],
            [90, 55, 25],
        )
        pdf.set_font("DejaV", "", 9)
        pdf.cell(
            0, 6,
            f"{labels['taxAdvantaged']}: "
            f"{_fmt_money(snap['tax_advantaged_total'], cur, language)} "
            f"({_fmt_num(snap['tax_advantaged_percent'], language, digits=1)}%)",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )
        pdf.ln(3)

    pdf.set_font("DejaV", "B", 11)
    pdf.cell(0, 7, labels["valueOverTime"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    _value_over_time_chart(pdf, snap["value_over_time"], cur, language)
    pdf.ln(4)

    # --- Efficiency -----------------------------------------------------
    eff = snap["efficiency"]
    pdf.add_page()
    _heading(
        pdf,
        f"{labels['efficiencySection']} — {_period_label(snap['period'], language)}",
    )
    t = eff["total"]
    if eff["assets"]:
        rows = [
            [
                a["name"],
                _translate_category(a["category"], language),
                _fmt_signed_money(a["contributed"], cur, language),
                _fmt_signed_money(a["growth"], cur, language),
                _fmt_pct(a["growth_pct"], language),
            ]
            for a in eff["assets"]
        ]
        rows.append([
            labels["total"], "",
            _fmt_signed_money(t["contributed"], cur, language),
            _fmt_signed_money(t["growth"], cur, language),
            _fmt_pct(t["growth_pct"], language),
        ])
        pdf.set_font("DejaV", "B", 9)
        widths = [50, 35, 35, 35, 25]
        for h, w in zip(
            [labels["colAsset"], labels["colCategory"], labels["colDeposits"],
             labels["colGrowth"], labels["colGrowthPct"]],
            widths,
        ):
            pdf.cell(w, 7, h, fill=True)
        pdf.ln(7)
        pdf.set_fill_color(235, 237, 242)
        pdf.set_font("DejaV", "", 9)
        for i, row in enumerate(rows):
            is_total = row[0] == labels["total"]
            pdf.set_font("DejaV", "B" if is_total else "", 9)
            pdf.set_fill_color(235, 237, 242) if is_total else (
                pdf.set_fill_color(249, 250, 252) if i % 2 else pdf.set_fill_color(255, 255, 255)
            )
            for cell, w in zip(row, widths):
                pdf.cell(w, 6.5, cell, fill=True)
            pdf.ln(6.5)
    else:
        pdf.set_font("DejaV", "", 9)
        pdf.cell(0, 6, labels["noHoldings"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Reconciliation: value at the start of the period plus net deposits
    # plus growth must equal value now, and value now must equal the
    # headline total on page 1 - both hold exactly by construction (see
    # services/growth.py::_totals), spelled out here so the reader (and a
    # test on the demo database, not just this code) can check it directly
    # rather than take it on faith.
    pdf.ln(2)
    pdf.set_font("DejaV", "", 8)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(
        0, 4,
        labels["reconciliation"].format(
            opening=_fmt_money(t["opening_value"], cur, language),
            deposits=_fmt_signed_money(t["contributed"], cur, language),
            growth=_fmt_signed_money(t["growth"], cur, language),
            value=_fmt_money(t["value"], cur, language),
        ),
        align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.set_text_color(20, 20, 20)

    pdf.ln(4)
    pdf.set_font("DejaV", "B", 11)
    pdf.cell(0, 7, labels["annualizedReturn"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("DejaV", "", 11)
    if eff["annualized_return"] is not None:
        pdf.cell(0, 7, _fmt_pct(eff["annualized_return"], language), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("DejaV", "", 8)
        pdf.set_text_color(120, 120, 120)
        pdf.multi_cell(0, 4, labels["annualizedNote"], align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(20, 20, 20)
    else:
        pdf.set_font("DejaV", "", 9)
        pdf.set_text_color(120, 120, 120)
        pdf.multi_cell(0, 5, labels["annualizedUnavailable"], align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(20, 20, 20)

    # --- AI commentary (optional) ----------------------------------------
    if ai_content:
        pdf.add_page()
        _heading(pdf, labels["aiSection"])
        pdf.set_font("DejaV", "", 9)
        pdf.set_text_color(120, 120, 120)
        when = _format_local_dt(ai_created_at) if ai_created_at else "?"
        pdf.multi_cell(0, 5, labels["aiGeneratedOn"].format(date=when), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(20, 20, 20)
        pdf.ln(2)

        if ai_ungrounded:
            pdf.set_fill_color(253, 235, 235)
            pdf.set_text_color(150, 30, 30)
            pdf.set_font("DejaV", "B", 9)
            pdf.multi_cell(0, 5, labels["aiWarning"], fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("DejaV", "", 9)
            pdf.multi_cell(0, 5, ", ".join(ai_ungrounded), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(20, 20, 20)
            pdf.ln(2)

        _write_markdown(pdf, ai_content)

    return bytes(pdf.output())


def _write_markdown(pdf: FPDF, text: str) -> None:
    """Just enough of the model's Markdown for a PDF paragraph: headings
    (##), bullets (-) and **bold** (handed to fpdf2's own markdown=True,
    which understands **bold**/__italic__ already) - mirrors
    components/Markdown.tsx's scope, not a general Markdown renderer."""
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            pdf.ln(2)
            continue
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            pdf.set_font("DejaV", "B", 11)
            pdf.multi_cell(0, 6, heading, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("DejaV", "", 10)
            continue
        if line.startswith(("- ", "* ")):
            pdf.set_font("DejaV", "", 10)
            pdf.multi_cell(0, 5.5, f"  •  {line[2:]}", markdown=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            continue
        pdf.set_font("DejaV", "", 10)
        pdf.multi_cell(0, 5.5, line, markdown=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
