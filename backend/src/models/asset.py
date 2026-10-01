"""Asset type model."""
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .user import Owned


class Asset(Owned, Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="currency")
    # kind: currency | gold | metal | crypto | interest - how the position is
    # *valued*, not what the user calls it. `category` is the user-facing
    # class (Cash, Stocks, Retirement, ...) that several differently-named
    # assets can share.
    #
    # "gold" is the pre-existing metal kind, kept exactly as before (always
    # priced as XAU, regardless of `units`). "metal" is its generalisation to
    # the other three precious metals: `units` must be XAU/XAG/XPT/XPD and
    # `amount` is grams, same as gold. See services/price_service.py for the
    # symbol catalogue and routes/helpers.compute_value for the pricing.
    category: Mapped[str] = mapped_column(String(60), nullable=False, default="", index=True)
    # Only for kind="interest": which statutory basis accrues on the principal.
    # "late" = art. 481 par. 2 KC (+5.5 pp), "capital" = art. 359 par. 2 KC
    # (+3.5 pp). Empty for every other kind.
    interest_basis: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    # Risk-and-liquidity band: safe | moderate | risky | illiquid. Defaults
    # from the category (see services-free helper in profiles.py) but kept per
    # asset so one holding can be reclassified without moving its class.
    profile: Mapped[str] = mapped_column(String(12), nullable=False, default="", index=True)
    icon: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    units: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    # units: e.g. "BTC", "SOL", "g"
    # Polish tax-advantaged wrapper this holding sits in, if any:
    # "" | ike | ikze | ppk | oipe | oki. Four of the five are penalised
    # before a different age (see fire.ACCESS_AGE); oki has no age lock at
    # all (see tax/pl/wrappers.py). Which is why FIRE math needs to know
    # about it and allocation does not otherwise care.
    wrapper: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    # When this asset was archived (soft delete - see routes/assets.py). NULL
    # while active. Archiving writes a closing snapshot (amount/value 0) so
    # the asset drops out of "currently held" everywhere without rewriting
    # its history on the portfolio-over-time chart.
    archived_at: Mapped["datetime | None"] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Asset {self.name} ({self.kind})>"
