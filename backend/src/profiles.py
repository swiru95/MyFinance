"""Risk-and-liquidity profile of an asset class.

A third level above `category`: several classes roll up into one band, and the
bands answer a different question than allocation does - not "what do I hold"
but "how exposed am I, and how fast could I get out".

Volatility and liquidity are deliberately not the same axis. Watches, a
vehicle and a loan in litigation are not volatile the way equities are; they
are simply hard to turn into cash. Folding them into "risky" overstates market
exposure - for the portfolio this was written against, by roughly 12 points.
"""

SAFE = "safe"
MODERATE = "moderate"
RISKY = "risky"
ILLIQUID = "illiquid"

BANDS = [SAFE, MODERATE, RISKY, ILLIQUID]

# Default band per asset class. A per-asset override lives on Asset.profile,
# so this only decides what a newly created asset starts as.
BY_CATEGORY = {
    "Cash": SAFE,
    "Savings": SAFE,
    "Bonds": SAFE,
    "Retirement": MODERATE,
    "TFI": MODERATE,
    "Gold": MODERATE,
    "Stocks": RISKY,
    "Crypto": RISKY,
    "Watches": ILLIQUID,
    "Fixed Assets": ILLIQUID,
    "Receivables": ILLIQUID,
}


def for_category(category: str) -> str:
    """Band a category belongs to; unknown classes start as moderate."""
    return BY_CATEGORY.get(category or "", MODERATE)
