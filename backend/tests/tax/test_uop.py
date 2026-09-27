"""Golden umowa o pracę values, hand-computed for 2026 by the architect.

These must match to the grosz - they are the contract this module is held
to, not just a smoke test.
"""
from src.tax.pl.uop import UopOptions, uop_schedule


def test_10k_month1():
    opts = UopOptions(ppk_employee=0.0, ppk_employer=0.0)
    y = uop_schedule(2026, [10_000.0] * 12, opts)
    m1 = y.months[0]
    assert m1.employee_social == 1371.00
    assert m1.health == 776.61
    assert m1.pit_base == 8379
    assert m1.pit_advance == 705
    assert m1.net == 7147.39


def test_20k_month1_and_threshold_crossing():
    opts = UopOptions(ppk_employee=0.0, ppk_employer=0.0)
    y = uop_schedule(2026, [20_000.0] * 12, opts)
    m1 = y.months[0]
    assert m1.employee_social == 2742.00
    assert m1.health == 1553.22
    assert m1.pit_base == 17008
    assert m1.pit_advance == 1741
    assert m1.net == 13963.78

    assert y.months[7].pit_advance == 4954  # month 8 crosses 120k
    assert y.months[8].pit_advance == 5143  # month 9, fully over


def test_30k_zus_cap_crossing():
    opts = UopOptions(ppk_employee=0.0, ppk_employer=0.0)
    y = uop_schedule(2026, [30_000.0] * 12, opts)

    for m in y.months[0:9]:  # months 1-9: base not yet capped
        assert not m.zus_capped

    m10 = y.months[9]
    assert m10.zus_capped
    assert m10.pension == 1229.76
    assert m10.disability == 189.00

    for m in y.months[10:12]:  # months 11-12: cap already reached
        assert m.pension == 0.0
        assert m.disability == 0.0

    for m in y.months:
        assert m.sickness == 735.00  # never capped
