"""The key hierarchy and the primitives under it (src/crypto), without a database.

What is proved here: the properties the design rests on. A data key opens only
with the KEK *and* the user's secret *and* the right user; a sealed value opens
only for the user, table and column it was sealed for; the recovery code and the
contact key are separate trust domains.
"""
from __future__ import annotations

import base64
import os
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

from src.crypto import contacts, recovery
from src.crypto.core import (
    DecryptionError,
    KekError,
    KeyExpired,
    KeyRing,
    KeysUnavailable,
    activated,
    active_keyring,
    aead_open,
    aead_seal,
    hkdf,
    make_key_check,
    new_dek,
    new_salt,
    parse_keks,
    unwrap_dek,
    verify_key_check,
    wrap_dek,
)
from src.crypto.fields import EncDate, EncDecimal, EncInt, EncJSON, EncStr
from src.config import settings

KEK_A = os.urandom(32)
KEK_B = os.urandom(32)


def _wrap(user_id, secret="sub-1", kek=KEK_A, version=1, salt=None, dek=None):
    salt = salt or new_salt()
    dek = dek or new_dek()
    return dek, salt, wrap_dek(dek, user_id=user_id, kek=kek, kek_version=version, salt=salt, secret=secret)


# --- wrapping the data key -------------------------------------------------------------

def test_the_data_key_unwraps_with_the_kek_the_salt_and_the_secret():
    user = uuid.uuid4()
    dek, salt, wrapped = _wrap(user)
    assert unwrap_dek(wrapped, user_id=user, kek=KEK_A, kek_version=1, salt=salt, secret="sub-1") == dek


def test_the_database_plus_the_kek_without_the_users_secret_opens_nothing():
    user = uuid.uuid4()
    _, salt, wrapped = _wrap(user)
    # Everything the database and the Secret hold: the wrapped key, the salt, the
    # KEK, the user id and the KEK version. Not the token's claim.
    for guess in ("sub-2", "", "sub-1 ", "SUB-1"):
        with pytest.raises(DecryptionError if guess else Exception):
            unwrap_dek(wrapped, user_id=user, kek=KEK_A, kek_version=1, salt=salt, secret=guess)


def test_the_secret_without_the_kek_opens_nothing():
    user = uuid.uuid4()
    _, salt, wrapped = _wrap(user)
    with pytest.raises(DecryptionError):
        unwrap_dek(wrapped, user_id=user, kek=KEK_B, kek_version=1, salt=salt, secret="sub-1")


def test_a_wrapped_key_is_bound_to_its_user_and_kek_version_and_salt():
    user = uuid.uuid4()
    _, salt, wrapped = _wrap(user)
    with pytest.raises(DecryptionError):  # another user's id in the AAD
        unwrap_dek(wrapped, user_id=uuid.uuid4(), kek=KEK_A, kek_version=1, salt=salt, secret="sub-1")
    with pytest.raises(DecryptionError):  # another KEK version
        unwrap_dek(wrapped, user_id=user, kek=KEK_A, kek_version=2, salt=salt, secret="sub-1")
    with pytest.raises(DecryptionError):  # another salt
        unwrap_dek(wrapped, user_id=user, kek=KEK_A, kek_version=1, salt=new_salt(), secret="sub-1")


def test_the_salt_makes_two_users_with_one_secret_wrap_differently():
    a, b = uuid.uuid4(), uuid.uuid4()
    dek = new_dek()
    wa = wrap_dek(dek, user_id=a, kek=KEK_A, kek_version=1, salt=new_salt(), secret="same")
    wb = wrap_dek(dek, user_id=b, kek=KEK_A, kek_version=1, salt=new_salt(), secret="same")
    assert wa != wb


def test_an_empty_secret_is_refused_rather_than_used():
    with pytest.raises(Exception, match="secret is empty"):
        wrap_dek(new_dek(), user_id=uuid.uuid4(), kek=KEK_A, kek_version=1, salt=new_salt(), secret="")


def test_every_wrap_uses_a_fresh_nonce():
    user, dek, salt = uuid.uuid4(), new_dek(), new_salt()
    wraps = {wrap_dek(dek, user_id=user, kek=KEK_A, kek_version=1, salt=salt, secret="s") for _ in range(20)}
    assert len(wraps) == 20


# --- the KEK configuration --------------------------------------------------------------

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode()


def test_keks_are_versioned_and_the_highest_is_current():
    keks = parse_keks(f"1:{_b64(KEK_A)},3:{_b64(KEK_B)}")
    assert keks.current == 3 and keks.get(1) == KEK_A and keks.current_key == KEK_B


def test_both_base64_alphabets_are_accepted_so_openssl_output_works_as_is():
    key = bytes(range(250, 250 - 32, -1))  # bytes whose encodings differ between the alphabets
    std, url = base64.b64encode(key).decode(), base64.urlsafe_b64encode(key).decode()
    assert std != url
    assert parse_keks(f"1:{std}").get(1) == key == parse_keks(f"1:{url}").get(1)
    assert parse_keks(f"1:{std.rstrip('=')}").get(1) == key  # padding optional


def test_the_current_version_can_be_chosen():
    assert parse_keks(f"1:{_b64(KEK_A)},3:{_b64(KEK_B)}", current=1).current == 1
    with pytest.raises(KekError):
        parse_keks(f"1:{_b64(KEK_A)}", current=2)


@pytest.mark.parametrize("raw", [
    "", "   ", "nonsense", "x:" + "A" * 43, "0:" + "A" * 43, "1:short", f"1:{'A' * 43},1:{'B' * 43}",
])
def test_a_malformed_kek_setting_is_refused_by_name(raw):
    with pytest.raises(KekError):
        parse_keks(raw)


def test_an_unlisted_kek_version_says_which_one_is_missing():
    keks = parse_keks(f"2:{_b64(KEK_A)}")
    with pytest.raises(KekError, match="version 1"):
        keks.get(1)


def test_the_key_check_value_opens_only_with_its_own_kek_and_version():
    blob = make_key_check(KEK_A, 2)
    assert verify_key_check(KEK_A, 2, blob)
    assert not verify_key_check(KEK_B, 2, blob)
    assert not verify_key_check(KEK_A, 3, blob)
    assert not verify_key_check(KEK_A, 2, blob[:-1] + bytes([blob[-1] ^ 1]))


# --- sealing values -----------------------------------------------------------------------

def _ring(user=None, dek=None):
    return KeyRing(user or uuid.uuid4(), dek or new_dek())


def test_a_value_opens_only_for_its_user_table_and_column():
    ring = _ring()
    blob = ring.seal("assets", "name", b"Savings")
    assert ring.open("assets", "name", blob) == b"Savings"
    with pytest.raises(DecryptionError):  # same table, another column
        ring.open("assets", "category", blob)
    with pytest.raises(DecryptionError):  # another table
        ring.open("expenses", "name", blob)
    # The same data key under another user id: nothing else differs, so this is
    # the user binding alone.
    twin = KeyRing(uuid.uuid4(), ring.export_dek())
    with pytest.raises(DecryptionError):
        twin.open("assets", "name", blob)
    # And a different data key altogether.
    with pytest.raises(DecryptionError):
        _ring(ring.user_id).open("assets", "name", blob)


def test_only_the_column_binding_distinguishes_two_cells_of_one_table():
    """Same user, same table, same key: the AAD naming the column is all that
    stops a name from being read as a category."""
    ring = _ring()
    blob = ring.seal("assets", "name", b"x")
    with pytest.raises(DecryptionError):
        ring.open("assets", "units", blob)


def test_a_tampered_or_truncated_value_is_refused():
    ring = _ring()
    blob = ring.seal("settings", "value", b"EUR")
    for bad in (blob[:-1], blob[:-1] + bytes([blob[-1] ^ 1]), b"\x01" + blob[1:5], b"", b"\x02" + blob[1:]):
        with pytest.raises(DecryptionError):
            ring.open("settings", "value", bad)


def test_equal_values_seal_to_different_ciphertexts():
    ring = _ring()
    assert len({ring.seal("settings", "value", b"same") for _ in range(10)}) == 10


def test_a_destroyed_or_expired_key_ring_refuses():
    ring = _ring()
    blob = ring.seal("settings", "value", b"x")
    expired = KeyRing(ring.user_id, ring.export_dek(), expires_at=1.0)
    with pytest.raises(KeyExpired):
        expired.open("settings", "value", blob)
    with pytest.raises(KeyExpired):
        expired.export_dek()
    ring.destroy()
    with pytest.raises(KeyExpired):
        ring.open("settings", "value", blob)


def test_a_forked_ring_opens_the_same_data_and_has_its_own_lifetime():
    ring = _ring()
    blob = ring.seal("reports", "content", b"text")
    job = ring.fork(60)
    assert job.open("reports", "content", blob) == b"text"
    job.destroy()
    assert ring.open("reports", "content", blob) == b"text"  # the request's ring is untouched
    stale = ring.fork(-1)
    with pytest.raises(KeyExpired):
        stale.open("reports", "content", blob)


def test_no_ring_in_force_means_no_cell_can_be_read_or_written():
    with pytest.raises(KeysUnavailable):
        active_keyring()
    t = EncStr()
    t.bind_to("assets", "name")
    with pytest.raises(KeysUnavailable):
        t.process_bind_param("x", None)
    with pytest.raises(KeysUnavailable):
        t.process_result_value(b"\x01" + b"0" * 40, None)
    ring = _ring()
    with activated(ring):
        assert active_keyring() is ring
        sealed = t.process_bind_param("x", None)
        assert t.process_result_value(sealed, None) == "x"
    with pytest.raises(KeysUnavailable):  # and it is put away again
        active_keyring()


def test_subkeys_are_derived_per_table():
    dek = new_dek()
    assert hkdf(dek, salt=None, info=b"myfinance/v1/table|assets") != hkdf(dek, salt=None, info=b"myfinance/v1/table|expenses")


# --- column types keep their Python types ------------------------------------------------------

def _t(cls, *args):
    t = cls(*args)
    t.bind_to("t", "c")
    return t


@pytest.mark.parametrize("cls,args,value,expected", [
    (EncStr, (), "zażółć gęślą jaźń 💸", "zażółć gęślą jaźń 💸"),
    (EncStr, (), "", ""),
    (EncInt, (), 1990, 1990),
    (EncInt, (), -3, -3),
    (EncDate, (), date(2026, 3, 5), date(2026, 3, 5)),
    (EncDate, (), datetime(2026, 3, 5, 14, 0), date(2026, 3, 5)),
    (EncJSON, (), {"a": [1, 2.5, None, "x"], "b": {"c": True}}, {"a": [1, 2.5, None, "x"], "b": {"c": True}}),
    (EncJSON, (), [], []),
    (EncDecimal, (20, 2), Decimal("1234.50"), Decimal("1234.50")),
    (EncDecimal, (20, 2), 1234.5, Decimal("1234.50")),
    (EncDecimal, (20, 2), 7, Decimal("7.00")),
    (EncDecimal, (20, 2), "0.1", Decimal("0.10")),
    (EncDecimal, (20, 6), 0.000001, Decimal("0.000001")),
])
def test_values_round_trip_with_their_python_type(cls, args, value, expected):
    ring, t = _ring(), _t(cls, *args)
    with activated(ring):
        back = t.process_result_value(t.process_bind_param(value, None), None)
    assert back == expected and type(back) is type(expected)


def test_decimals_round_half_away_from_zero_like_numeric_does():
    ring, t = _ring(), _t(EncDecimal, 20, 2)
    with activated(ring):
        for value, expected in ((Decimal("1.005"), "1.01"), (Decimal("-1.005"), "-1.01"), (0.125, "0.13"), (2.675, "2.68")):
            assert t.process_result_value(t.process_bind_param(value, None), None) == Decimal(expected)


def test_none_stays_null_and_never_needs_a_key():
    t = _t(EncStr)
    assert t.process_bind_param(None, None) is None
    assert t.process_result_value(None, None) is None


@pytest.mark.parametrize("cls,args,bad", [
    (EncStr, (), 5), (EncInt, (), "5"), (EncInt, (), True), (EncDecimal, (20, 2), float("nan")),
    (EncDecimal, (20, 2), float("inf")), (EncDecimal, (20, 2), object()), (EncDate, (), 12),
])
def test_a_value_of_the_wrong_kind_is_refused_not_stored(cls, args, bad):
    ring, t = _ring(), _t(cls, *args)
    with activated(ring), pytest.raises((TypeError, ValueError)):
        t.process_bind_param(bad, None)


def test_comparing_an_encrypted_column_with_a_literal_in_sql_is_an_error_not_a_silent_miss():
    from src.models.asset import Asset

    with pytest.raises(TypeError, match="encrypted column"):
        Asset.name == "Cash"
    with pytest.raises(TypeError):
        Asset.name.like("C%")
    # IS NULL is meaningful, and so is comparing two columns.
    assert Asset.archived_at.is_(None) is not None
    assert Asset.name.is_(None) is not None


# --- the recovery code ---------------------------------------------------------------------------

def test_a_recovery_code_has_the_documented_shape_and_round_trips():
    user, dek = uuid.uuid4(), new_dek()
    material = recovery.create(user, dek)
    assert material.code.startswith("MF1-")
    groups = material.code.split("-")
    assert groups[0] == "MF1" and all(len(g) == 5 for g in groups[1:]) and len(groups) == 11
    parsed = recovery.parse(material.code)
    assert parsed.recovery_id == material.recovery_id
    wrap_key, proof = recovery.derive(parsed.secret, material.salt, material.kdf)
    assert recovery.unwrap(user, material.wrapped_dek, wrap_key) == dek
    assert recovery.verifier_of(proof) == material.verifier


def test_the_code_is_read_forgivingly_and_typos_are_caught_before_any_lookup():
    material = recovery.create(uuid.uuid4(), new_dek())
    code = material.code
    assert recovery.parse(code.lower()).recovery_id == material.recovery_id
    assert recovery.parse(code.replace("-", " ")).recovery_id == material.recovery_id
    assert recovery.parse("  " + code + "\n").recovery_id == material.recovery_id
    body = code.replace("-", "")
    flipped = body[:20] + ("Z" if body[20] != "Z" else "Y") + body[21:]
    with pytest.raises(recovery.RecoveryCodeError, match="typo"):
        recovery.parse(flipped)
    for bad in ("", "MF1", "hello", code[:-3], code + "AAAA", code.replace(code[8], "U")):
        with pytest.raises(recovery.RecoveryCodeError):
            recovery.parse(bad)


def test_a_wrong_secret_half_does_not_open_the_recovery_wrap():
    user, dek = uuid.uuid4(), new_dek()
    material = recovery.create(user, dek)
    other = recovery.format_code(material.recovery_id, os.urandom(recovery.SECRET_BYTES))
    parsed = recovery.parse(other)
    wrap_key, proof = recovery.derive(parsed.secret, material.salt, material.kdf)
    with pytest.raises(DecryptionError):
        recovery.unwrap(user, material.wrapped_dek, wrap_key)
    assert recovery.verifier_of(proof) != material.verifier


def test_the_recovery_wrap_is_bound_to_its_user():
    user = uuid.uuid4()
    material = recovery.create(user, new_dek())
    parsed = recovery.parse(material.code)
    wrap_key, _ = recovery.derive(parsed.secret, material.salt, material.kdf)
    with pytest.raises(DecryptionError):
        recovery.unwrap(uuid.uuid4(), material.wrapped_dek, wrap_key)


def test_each_code_is_unique_and_the_kdf_is_recorded_with_it():
    codes = {recovery.create(uuid.uuid4(), new_dek()) for _ in range(5)}
    assert len({m.code for m in codes}) == 5
    assert all(m.kdf == f"scrypt:n={settings.recovery_scrypt_n},r=8,p=1" for m in codes)


@pytest.mark.parametrize("descriptor", [
    "scrypt:n=2,r=8,p=1", "scrypt:n=1048577,r=8,p=1", "scrypt:n=1024,r=99,p=1", "md5:n=1", "", "scrypt:n=1024,r=8,p=99",
])
def test_stored_kdf_parameters_are_data_not_trusted(descriptor):
    with pytest.raises(recovery.RecoveryCodeError):
        recovery.derive(b"x" * 20, new_salt(), descriptor)


# --- the contact key ------------------------------------------------------------------------------

@pytest.fixture
def contact_key(monkeypatch):
    monkeypatch.setattr(settings, "contact_key", _b64(os.urandom(32)))


def test_an_address_opens_with_the_contact_key_and_only_for_its_user(contact_key):
    user = uuid.uuid4()
    blob = contacts.seal_email(user, "someone@example.test")
    assert contacts.open_email(user, blob) == "someone@example.test"
    with pytest.raises(DecryptionError):
        contacts.open_email(uuid.uuid4(), blob)


def test_the_contact_key_is_not_a_finance_key(contact_key):
    """What a notifier would hold opens addresses and nothing a user owns: not a
    wrapped data key, not a sealed cell - whichever way it is tried."""
    user, dek = uuid.uuid4(), new_dek()
    ring = KeyRing(user, dek)
    cell = ring.seal("positions", "amount", b"123456.00")
    key = base64.urlsafe_b64decode(settings.contact_key + "==")
    # As a KEK for wrapping:
    salt = new_salt()
    wrapped = wrap_dek(dek, user_id=user, kek=KEK_A, kek_version=1, salt=salt, secret="sub-1")
    with pytest.raises(DecryptionError):
        unwrap_dek(wrapped, user_id=user, kek=key, kek_version=1, salt=salt, secret="sub-1")
    # As a data key, directly or through the table-subkey derivation:
    for candidate in (key, hkdf(key, salt=None, info=b"myfinance/v1/table|positions")):
        with pytest.raises(DecryptionError):
            aead_open(candidate, cell, KeyRing(user, dek)._aad("positions", "amount"))
    # And a ring built from it:
    with pytest.raises(DecryptionError):
        KeyRing(user, key).open("positions", "amount", cell)


def test_an_address_sealed_under_the_contact_key_is_not_a_cell(contact_key):
    user = uuid.uuid4()
    blob = contacts.seal_email(user, "x@example.test")
    ring = KeyRing(user, new_dek())
    with pytest.raises(DecryptionError):
        ring.open("user_contacts", "email", blob)


def test_the_unsubscribe_token_is_stable_per_version_and_distinct_across_users(contact_key):
    a, b = uuid.uuid4(), uuid.uuid4()
    assert contacts.unsubscribe_token(a, 1) == contacts.unsubscribe_token(a, 1)
    assert contacts.unsubscribe_token(a, 1) != contacts.unsubscribe_token(a, 2)
    assert contacts.unsubscribe_token(a, 1) != contacts.unsubscribe_token(b, 1)
    token = contacts.unsubscribe_token(a, 1)
    assert contacts.token_hash(token) != token.encode() and len(contacts.token_hash(token)) == 32


@pytest.mark.parametrize("value", ["", "!!!", _b64(b"short")])
def test_a_missing_or_malformed_contact_key_is_refused(monkeypatch, value):
    monkeypatch.setattr(settings, "contact_key", value)
    assert not contacts.configured()
    with pytest.raises(contacts.ContactKeyError):
        contacts.seal_email(uuid.uuid4(), "x@example.test")
