"""Encrypted column types.

Each is a `TypeDecorator` over a binary column: the model keeps the Python type
it always had (str, int, Decimal, date, dict/list) and the database holds
`version || nonce || AES-256-GCM ciphertext`. Writing seals with the active key
ring (core.activated - the session sets it around its own operations), reading
opens with it. With no ring in force they raise `KeysUnavailable`: ciphertext is
never returned as if it were a value, and a plaintext value is never written.

`None` stays SQL NULL. That reveals which optional fields are unset, and nothing
about their content; it is what keeps nullable columns nullable.

What these columns cannot do, because the database cannot see inside them:
compare, sort, filter, group or aggregate. Any such query has to load rows and
do it in Python (the few places that did are noted where they were changed).
Comparing one with a literal in SQL would encrypt the literal under a fresh
nonce and so silently never match; the comparator below turns that into an error.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Column, Date, Integer, LargeBinary, Numeric, Text, event
from sqlalchemy import JSON as SAJSON
from sqlalchemy.sql.elements import ClauseElement
from sqlalchemy.types import TypeDecorator

from .core import active_keyring

_NULL_TESTS = {"is_", "is_not", "isnot", "is_distinct_from", "is_not_distinct_from"}


class _Comparator(TypeDecorator.Comparator, LargeBinary.Comparator):
    def operate(self, op, *other, **kw):
        # IS [NOT] NULL is meaningful against ciphertext; so is comparing the
        # column with another SQL expression, which SQLAlchemy itself does
        # internally (matching columns up). What is refused is a *literal*: it
        # would be encrypted under a fresh nonce and so never equal anything.
        if getattr(op, "__name__", "") in _NULL_TESTS or all(
            isinstance(o, ClauseElement) for o in other
        ):
            return super().operate(op, *other, **kw)
        raise TypeError(
            f"cannot apply {getattr(op, '__name__', op)} to an encrypted column in SQL: its value "
            "is only known after decryption; load the rows and compare in Python"
        )

    def reverse_operate(self, op, other, **kw):
        raise TypeError("cannot compare an encrypted column in SQL; load the rows and compare in Python")


class Encrypted(TypeDecorator):
    """Base class: subclasses define how a Python value becomes bytes and back."""

    impl = LargeBinary
    cache_ok = True
    comparator_factory = _Comparator

    # Set when the column is attached to its table (see _bind_on_attach), so the
    # AAD can name them. Not constructor arguments: the same type class is used
    # for many columns.
    table: str | None = None
    column: str | None = None

    def bind_to(self, table: str, column: str) -> None:
        self.table, self.column = table, column

    def _where(self) -> tuple[str, str]:
        if self.table is None or self.column is None:
            raise RuntimeError("an encrypted column type was used before it was attached to a table")
        return self.table, self.column

    # -- subclass hooks --
    def encode(self, value) -> bytes:  # pragma: no cover - abstract
        raise NotImplementedError

    def decode(self, data: bytes):  # pragma: no cover - abstract
        raise NotImplementedError

    def legacy_type(self):  # pragma: no cover - abstract
        """The plain column type this one replaced (the schema job reads old rows with it)."""
        raise NotImplementedError

    # -- SQLAlchemy --
    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        table, column = self._where()
        return active_keyring().seal(table, column, self.encode(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        table, column = self._where()
        return self.decode(active_keyring().open(table, column, bytes(value)))

    def seal_with(self, ring, value) -> bytes | None:
        """Seal `value` under `ring` without a session (the migration, tests)."""
        if value is None:
            return None
        table, column = self._where()
        return ring.seal(table, column, self.encode(value))

    def open_with(self, ring, blob):
        if blob is None:
            return None
        table, column = self._where()
        return self.decode(ring.open(table, column, bytes(blob)))


class EncStr(Encrypted):

    cache_ok = True
    def encode(self, value) -> bytes:
        if not isinstance(value, str):
            raise TypeError(f"expected str, got {type(value).__name__}")
        return value.encode("utf-8")

    def decode(self, data: bytes) -> str:
        return data.decode("utf-8")

    def legacy_type(self):
        return Text()


class EncInt(Encrypted):

    cache_ok = True
    def encode(self, value) -> bytes:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"expected int, got {type(value).__name__}")
        return str(value).encode("ascii")

    def decode(self, data: bytes) -> int:
        return int(data.decode("ascii"))

    def legacy_type(self):
        return Integer()


class EncDecimal(Encrypted):
    """A money or quantity figure. Comes back as `Decimal`, rounded to `scale`
    places half away from zero - what the NUMERIC(precision, scale) column it
    replaced did on PostgreSQL."""

    cache_ok = True

    def __init__(self, precision: int, scale: int):
        super().__init__()
        self.precision = precision
        self.scale = scale
        self._quantum = Decimal(1).scaleb(-scale)

    def encode(self, value) -> bytes:
        if isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("NaN and infinity are not amounts")
            value = Decimal(repr(value))
        elif isinstance(value, (int, str)) and not isinstance(value, bool):
            value = Decimal(value)
        elif not isinstance(value, Decimal):
            raise TypeError(f"expected a number, got {type(value).__name__}")
        if not value.is_finite():
            raise ValueError("NaN and infinity are not amounts")
        return format(value.quantize(self._quantum, rounding=ROUND_HALF_UP), "f").encode("ascii")

    def decode(self, data: bytes) -> Decimal:
        return Decimal(data.decode("ascii"))

    def legacy_type(self):
        return Numeric(self.precision, self.scale)


class EncDate(Encrypted):

    cache_ok = True
    def encode(self, value) -> bytes:
        if isinstance(value, datetime):
            value = value.date()
        elif isinstance(value, str):
            value = date.fromisoformat(value)
        if not isinstance(value, date):
            raise TypeError(f"expected a date, got {type(value).__name__}")
        return value.isoformat().encode("ascii")

    def decode(self, data: bytes) -> date:
        return date.fromisoformat(data.decode("ascii"))

    def legacy_type(self):
        return Date()


class EncJSON(Encrypted):
    """Any JSON-serialisable value (the columns hold dicts and lists)."""

    cache_ok = True

    def encode(self, value) -> bytes:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def decode(self, data: bytes):
        return json.loads(data.decode("utf-8"))

    def legacy_type(self):
        return SAJSON()


@event.listens_for(Column, "after_parent_attach")
def _bind_on_attach(column: Column, table) -> None:
    """Tell an encrypted type which table and column it sits in, once it is attached."""
    if isinstance(column.type, Encrypted) and getattr(table, "name", None):
        column.type.bind_to(table.name, column.name)


def encrypted_columns(table):
    """(column, type) for every encrypted column of `table`."""
    return [(c, c.type) for c in table.columns if isinstance(c.type, Encrypted)]
