"""Golden JDG (B2B) values, hand-computed for 2026 by the architect."""
from src.tax.pl.b2b import B2bOptions, b2b_schedule, jdg_social_monthly
from src.tax.pl.params import get_params


def test_jdg_social_full_with_sickness():
    p = get_params(2026)
    social = jdg_social_monthly(p, "full", sickness=True)
    assert social["pension"] == 1103.27
    assert social["disability"] == 452.16
    assert social["accident"] == 94.39
    assert social["sickness"] == 138.47
    assert social["fp"] == 138.47
    assert social["total"] == 1926.76


def test_jdg_social_preferential():
    p = get_params(2026)
    without_sickness = jdg_social_monthly(p, "preferential", sickness=False)
    assert without_sickness["total"] == 420.86
    with_sickness = jdg_social_monthly(p, "preferential", sickness=True)
    assert with_sickness["total"] == 456.18


def test_b2b_liniowy_month1():
    opts = B2bOptions(tax_form="liniowy", zus_stage="full", sickness=True, vat="standard")
    y = b2b_schedule(2026, [20_000.0] * 12, [0.0] * 12, opts)
    m1 = y.months[0]
    assert m1.income == 18073.24
    assert m1.health == 885.59
    assert m1.pit_advance == 3266
    assert m1.take_home == 13921.65
    assert m1.vat_due == 4600.00
    assert m1.invoice_gross == 24600.00
    assert m1.set_aside == 10678.35


def test_b2b_ryczalt_month1():
    opts = B2bOptions(
        tax_form="ryczalt", ryczalt_rate=0.12, zus_stage="full", sickness=True, vat="standard"
    )
    y = b2b_schedule(2026, [20_000.0] * 12, [0.0] * 12, opts)
    for m in y.months:
        assert m.health_tier == 2
        assert m.health == 830.58
    assert y.months[0].pit_advance == 2119
    assert y.months[0].take_home == 15123.66
    # Auto tier already equals the implied tier, so nothing to settle.
    assert y.ryczalt_health_tier_actual == 2
    assert y.ryczalt_health_reconciliation == 0.00


def test_b2b_ryczalt_chosen_tier_reconciles():
    # Paying at last year's (higher) tier 3 all year while this year's
    # actual revenue only implies tier 2 - the annual return refunds the
    # difference.
    opts = B2bOptions(
        tax_form="ryczalt",
        ryczalt_rate=0.12,
        zus_stage="full",
        sickness=True,
        vat="standard",
        ryczalt_health_tier=3,
    )
    y = b2b_schedule(2026, [20_000.0] * 12, [0.0] * 12, opts)
    m1 = y.months[0]
    assert m1.health_tier == 3
    assert m1.health == 1495.04
    assert m1.income == 20_000.00  # ryczalt income is informational only
    pit_base = round(20_000 - 1926.76 - 0.5 * 1495.04)
    assert pit_base == 17326
    assert m1.pit_advance == 2079
    assert m1.take_home == 14499.20
    assert y.ryczalt_health_tier_actual == 2
    assert y.ryczalt_health_reconciliation == -7973.52


def test_b2b_skala_absorbs_reduction_then_owes():
    opts = B2bOptions(tax_form="skala", zus_stage="full", sickness=True, vat="standard")
    y = b2b_schedule(2026, [20_000.0] * 12, [0.0] * 12, opts)
    assert y.months[0].pit_advance == 0  # the 3 600 annual reduction absorbs it
    assert y.months[1].pit_advance == 738


def test_vat_exempt_over_limit_warns():
    opts = B2bOptions(tax_form="liniowy", zus_stage="full", vat="exempt")
    y = b2b_schedule(2026, [25_000.0] * 12, [0.0] * 12, opts)  # sums to 300 000
    assert "vat_exempt_limit_exceeded" in y.warnings


def test_ryczalt_unusual_rate_warns():
    opts = B2bOptions(tax_form="ryczalt", ryczalt_rate=0.075, zus_stage="full", vat="standard")
    y = b2b_schedule(2026, [10_000.0] * 12, [0.0] * 12, opts)
    assert "ryczalt_rate_unusual" in y.warnings
