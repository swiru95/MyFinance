"""Checking the configured KEK against the database, and reporting on rotation.

A KEK that is wrong is the one failure that would not announce itself: every
existing user would simply fail to unlock - and new users would be wrapped under
a key the database has never seen. So each KEK version gets a *key-check value*
(table `key_check`, crypto/core.make_key_check): a fixed message sealed under it.
The schema job writes them; startup and the schema job open them with whatever is
configured and refuse to go on if one does not open.
"""
from __future__ import annotations

import logging

from sqlalchemy import insert, inspect, select, text
from sqlalchemy.engine import Connection, Engine

from ..crypto.core import KekError, KekSet, active_keks, make_key_check, verify_key_check
from ..models.keycheck import KeyCheck

log = logging.getLogger(__name__)


def _stored(conn: Connection) -> dict[int, bytes]:
    return {
        row[0]: bytes(row[1])
        for row in conn.execute(select(KeyCheck.kek_version, KeyCheck.check_value))
    }


def mismatches(keks: KekSet, stored: dict[int, bytes]) -> list[str]:
    """Configured versions whose stored check value does not open with their key."""
    return [
        f"KEK version {version} does not open the key-check value this database was "
        "initialised with: the configured Secret is not the one in use (a typo, an old "
        "value, another environment's?). Nothing has been written."
        for version, key in sorted(keks.keys.items())
        if version in stored and not verify_key_check(key, version, stored[version])
    ]


def startup_check(eng: Engine) -> None:
    """Called by the application at startup. Raises `KekError` on any mismatch.

    With authentication on, the current KEK must already have its check value
    (the schema job, which runs first, writes it). With authentication off - a
    local run - a missing one is simply created, on a best-effort basis.
    """
    from ..auth import auth_enabled

    keks = active_keks()
    if not inspect(eng).has_table(KeyCheck.__tablename__):
        if auth_enabled():
            raise KekError("the key_check table is missing: run the schema job (python -m src.schema) first")
        return
    with eng.connect() as conn:
        stored = _stored(conn)
    problems = mismatches(keks, stored)
    if problems:
        raise KekError("; ".join(problems))
    if keks.current not in stored:
        if auth_enabled():
            raise KekError(
                f"the database has no key-check value for the current KEK version {keks.current}: "
                "run the schema job (python -m src.schema) with this KEK configured"
            )
        try:
            with eng.begin() as conn:
                conn.execute(
                    insert(KeyCheck).values(
                        kek_version=keks.current,
                        check_value=make_key_check(keks.get(keks.current), keks.current),
                    )
                )
        except Exception:  # pragma: no cover - read-only role, or a race
            log.warning("could not record the key-check value for the development KEK", exc_info=True)
    unknown = sorted(set(stored) - set(keks.keys))
    if unknown:
        log.warning(
            "the database knows KEK version(s) %s which are not configured; users still wrapped "
            "under them cannot sign in until they are added back to MYFINANCE_KEKS",
            unknown,
        )


def ensure_key_check(conn: Connection) -> list[int]:
    """Schema job: verify the configured KEKs against the stored check values
    and add the missing ones. Returns the versions added. Raises `KekError`
    before writing anything if one does not match, or if users are wrapped under
    a version that is not configured."""
    keks = active_keks()
    stored = _stored(conn)
    problems = mismatches(keks, stored)
    if problems:
        raise KekError("; ".join(problems))
    used = {
        row[0]: row[1]
        for row in conn.execute(
            text("SELECT kek_version, count(*) FROM users WHERE kek_version IS NOT NULL GROUP BY kek_version")
        )
    }
    missing = {v: n for v, n in used.items() if v not in keks.keys}
    if missing:
        listing = ", ".join(f"v{v} ({n} user{'s' if n != 1 else ''})" for v, n in sorted(missing.items()))
        raise KekError(
            f"users are wrapped under KEK version(s) {listing} that MYFINANCE_KEKS does not list; "
            "add them back (they are needed until every user has been rewrapped) before going on"
        )
    added = []
    for version, key in sorted(keks.keys.items()):
        if version not in stored:
            conn.execute(insert(KeyCheck).values(kek_version=version, check_value=make_key_check(key, version)))
            added.append(version)
    return added


def version_report(conn: Connection) -> dict:
    """How many users are on each KEK version, and how many have no key yet."""
    keks = active_keks()
    counts = {
        row[0]: row[1]
        for row in conn.execute(
            text("SELECT kek_version, count(*) FROM users WHERE wrapped_dek IS NOT NULL GROUP BY kek_version")
        )
    }
    keyless = conn.execute(text("SELECT count(*) FROM users WHERE wrapped_dek IS NULL")).scalar_one()
    total = conn.execute(text("SELECT count(*) FROM users")).scalar_one()
    return {
        "current": keks.current,
        "configured": sorted(keks.keys),
        "total": total,
        "by_version": dict(sorted(counts.items())),
        "behind": sum(n for v, n in counts.items() if v != keks.current),
        "keyless": keyless,
    }
