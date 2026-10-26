"""Statement import assistant schemas (routes/statement.py).

The limits keep one request to one small job: a CSV header plus a few sample
rows, one chunk of PDF text, one month's expenses and candidate payments.
"""
from typing import Annotated

from pydantic import BaseModel, Field

Text = Annotated[str, Field(max_length=300)]


class ColumnsIn(BaseModel):
    header: list[Annotated[str, Field(max_length=80)]] = Field(..., max_length=40)
    sample: list[Annotated[list[Annotated[str, Field(max_length=80)]], Field(max_length=40)]] = Field(
        ..., min_length=1, max_length=8
    )


class ExtractIn(BaseModel):
    lines: list[Text] = Field(..., min_length=1, max_length=40)
    first_line: int = Field(1, ge=1)


class CommitmentBrief(BaseModel):
    id: int
    name: str = Field(..., max_length=120)
    category: str = Field("", max_length=60)
    amount: float = Field(..., ge=0)
    currency: str = Field("PLN", pattern="^(PLN|EUR|USD|CHF)$")


class PaymentBrief(BaseModel):
    id: int
    date: str = Field(..., max_length=10)
    amount: float = Field(..., ge=0)
    note: str = Field("", max_length=200)


class MatchIn(BaseModel):
    commitments: list[CommitmentBrief] = Field(..., min_length=1, max_length=40)
    payments: list[PaymentBrief] = Field(..., min_length=1, max_length=60)


class StatementAssistIn(BaseModel):
    """Body of PUT /api/settings/statement-assist."""

    mode: str = Field(..., pattern="^(off|browser|server)$")
