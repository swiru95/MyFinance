"""Smoke coverage for the UoP vs. B2B comparator.

Not a golden-value test (the spec gives no hand-computed comparator figures)
- this just pins the shape of the result and a couple of sign/consistency
invariants that must hold regardless of the exact numbers.
"""
from src.tax.pl.b2b import B2bOptions
from src.tax.pl.compare import compare_uop_b2b
from src.tax.pl.uop import UopOptions


def test_compare_uop_b2b_shape_and_consistency():
    result = compare_uop_b2b(
        2026,
        10_000.0,
        UopOptions(ppk_employee=0.0, ppk_employer=0.0),
        20_000.0,
        0.0,
        B2bOptions(tax_form="liniowy", zus_stage="full", vat="standard"),
    )

    for key in (
        "uop_annual_net",
        "b2b_annual_take_home",
        "b2b_equivalent_revenue_monthly",
        "pension_gap_annual",
        "difference_net_annual",
        "uop_pension_account_contributions",
        "b2b_pension_account_contributions",
    ):
        assert key in result

    # An employee's own pension contribution is matched by an employer share
    # that a sole trader never gets, so UoP should out-contribute JDG at
    # equal ZUS stage/gross assumptions here.
    assert result["pension_gap_annual"] > 0

    assert result["difference_net_annual"] == round(
        result["b2b_annual_take_home"] - result["uop_annual_net"], 2
    )
