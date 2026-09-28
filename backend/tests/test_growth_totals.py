"""services.growth._totals: the total row must reconcile exactly -
opening_value + contributed + growth == value, always, not just usually.

_totals() is exercised directly with hand-picked per-asset dicts (bypassing
asset_growth) because the bug this guards against is specifically about how
*already-rounded* per-asset figures are summed, and picking numbers that
land awkwardly on a rounding boundary is easiest to do by constructing the
per-asset dicts directly rather than hoping real positions happen to trip
it.
"""
import pytest

from src.services.growth import _totals


def test_total_reconciles_even_when_per_asset_rounding_would_drift():
    """Two assets, each with opening=1.004 and contributed=1.004: rounded
    independently that is opening=1.00, contributed=1.00 per asset (4 dp
    truncates to 2 dp downward), but invested = opening+contributed BEFORE
    rounding is 2.008, which rounds to 2.01 - one grosz more than
    1.00 + 1.00. Summing each asset's own (independently rounded) `invested`
    the old way gave a total invested of 4.02 while opening_value+contributed
    totalled 4.00 - a discrepancy that broke the PDF report's reconciliation
    line. The fix computes total invested as (total opening + total
    contributed), not as a sum of already-rounded per-asset "invested"
    figures, so this must now reconcile exactly."""
    assets = [
        {
            "opening_value": round(1.004, 2), "contributed": round(1.004, 2),
            "invested": round(1.004 + 1.004, 2), "value": 2.20,
            "untracked_updates": 0,
        },
        {
            "opening_value": round(1.004, 2), "contributed": round(1.004, 2),
            "invested": round(1.004 + 1.004, 2), "value": 2.20,
            "untracked_updates": 0,
        },
    ]
    # Confirm the setup actually exhibits the drift this test means to catch
    # - otherwise this would pass for the wrong reason.
    naive_invested_total = round(sum(a["invested"] for a in assets), 2)
    assert naive_invested_total == pytest.approx(4.02)

    total = _totals(assets, value_raw=4.40)
    assert total["opening_value"] == pytest.approx(2.00)
    assert total["contributed"] == pytest.approx(2.00)
    assert total["invested"] == pytest.approx(4.00)  # not 4.02
    reconciled = round(total["opening_value"] + total["contributed"] + total["growth"], 2)
    assert reconciled == total["value"]


def test_reconciliation_holds_for_ordinary_numbers_too():
    assets = [
        {"opening_value": 1000.0, "contributed": 100.0, "invested": 1100.0,
         "value": 1120.0, "untracked_updates": 0},
        {"opening_value": 500.0, "contributed": 0.0, "invested": 500.0,
         "value": 480.0, "untracked_updates": 1},
    ]
    total = _totals(assets, value_raw=1600.0)
    reconciled = round(total["opening_value"] + total["contributed"] + total["growth"], 2)
    assert reconciled == total["value"]
    assert total["value"] == pytest.approx(1600.0)
