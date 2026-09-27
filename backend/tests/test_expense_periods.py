"""Tests for quarterly and yearly expense periods."""
from datetime import date


class TestAppliesInMonth:
    """Test which months a recurring expense applies in."""

    def test_yearly_applies_in_correct_months(self):
        """Yearly starting 2026-03-15 applies in 2026-03 and 2027-03, not 2026-04."""
        from src.models.expense import Expense
        from src.services.budget import applies_in_month

        e = Expense(
            name="Annual fee",
            amount=1200.0,
            currency="PLN",
            period="yearly",
            category="",
            starts_on=date(2026, 3, 15),
            ends_on=None,
            notes="",
        )
        # Should apply in March 2026
        assert applies_in_month(e, date(2026, 3, 1), date(2026, 3, 31))
        # Should not apply in April 2026
        assert not applies_in_month(e, date(2026, 4, 1), date(2026, 4, 30))
        # Should apply in March 2027
        assert applies_in_month(e, date(2027, 3, 1), date(2027, 3, 31))

    def test_quarterly_applies_in_correct_months(self):
        """Quarterly from 2026-01-10 applies in Jan/Apr/Jul/Oct."""
        from src.models.expense import Expense
        from src.services.budget import applies_in_month

        e = Expense(
            name="Quarterly insurance",
            amount=300.0,
            currency="PLN",
            period="quarterly",
            category="",
            starts_on=date(2026, 1, 10),
            ends_on=None,
            notes="",
        )
        # January
        assert applies_in_month(e, date(2026, 1, 1), date(2026, 1, 31))
        # February (not a quarterly month)
        assert not applies_in_month(e, date(2026, 2, 1), date(2026, 2, 28))
        # April
        assert applies_in_month(e, date(2026, 4, 1), date(2026, 4, 30))
        # July
        assert applies_in_month(e, date(2026, 7, 1), date(2026, 7, 31))
        # October
        assert applies_in_month(e, date(2026, 10, 1), date(2026, 10, 31))
        # November (not a quarterly month)
        assert not applies_in_month(e, date(2026, 11, 1), date(2026, 11, 30))

    def test_ends_on_respected(self):
        """An expense with ends_on should not apply after that date."""
        from src.models.expense import Expense
        from src.services.budget import applies_in_month

        e = Expense(
            name="Temporary quarterly",
            amount=100.0,
            currency="PLN",
            period="quarterly",
            category="",
            starts_on=date(2026, 1, 1),
            ends_on=date(2026, 6, 30),
            notes="",
        )
        # Should apply in January
        assert applies_in_month(e, date(2026, 1, 1), date(2026, 1, 31))
        # Should apply in April (before ends_on)
        assert applies_in_month(e, date(2026, 4, 1), date(2026, 4, 30))
        # Should not apply in July (after ends_on)
        assert not applies_in_month(e, date(2026, 7, 1), date(2026, 7, 31))


class TestMonthlyEquivalent:
    """Test monthly equivalent calculation."""

    def test_yearly_monthly_equivalent(self):
        """Monthly equivalent of yearly 1200 = 100."""
        from src.models.expense import Expense
        from src.services.budget import monthly_equivalent

        e = Expense(
            name="Annual",
            amount=1200.0,
            currency="PLN",
            period="yearly",
            category="",
            starts_on=date(2026, 1, 1),
            ends_on=None,
            notes="",
        )
        assert monthly_equivalent(e) == 100.0

    def test_quarterly_monthly_equivalent(self):
        """Monthly equivalent of quarterly 300 = 100."""
        from src.models.expense import Expense
        from src.services.budget import monthly_equivalent

        e = Expense(
            name="Quarterly",
            amount=300.0,
            currency="PLN",
            period="quarterly",
            category="",
            starts_on=date(2026, 1, 1),
            ends_on=None,
            notes="",
        )
        assert monthly_equivalent(e) == 100.0

    def test_monthly_monthly_equivalent(self):
        """Monthly equivalent of monthly 100 = 100."""
        from src.models.expense import Expense
        from src.services.budget import monthly_equivalent

        e = Expense(
            name="Monthly",
            amount=100.0,
            currency="PLN",
            period="monthly",
            category="",
            starts_on=date(2026, 1, 1),
            ends_on=None,
            notes="",
        )
        assert monthly_equivalent(e) == 100.0

    def test_once_monthly_equivalent(self):
        """Monthly equivalent of once = 0."""
        from src.models.expense import Expense
        from src.services.budget import monthly_equivalent

        e = Expense(
            name="One-off",
            amount=1000.0,
            currency="PLN",
            period="once",
            category="",
            starts_on=date(2026, 1, 1),
            ends_on=None,
            notes="",
        )
        assert monthly_equivalent(e) == 0.0


class TestNextDue:
    """Test next due date calculation."""

    def test_yearly_next_due(self):
        """Next due for yearly starting 2025-01-31 with today 2026-02-01 is 2027-01-31."""
        from src.models.expense import Expense
        from src.services.budget import next_due

        e = Expense(
            name="Annual",
            amount=1200.0,
            currency="PLN",
            period="yearly",
            category="",
            starts_on=date(2025, 1, 31),
            ends_on=None,
            notes="",
        )
        today = date(2026, 2, 1)
        result = next_due(e, today)
        assert result == date(2027, 1, 31)

    def test_next_due_clamps_to_month_length(self):
        """Next due clamps 31st to Feb 28/29 for a monthly-like quarterly."""
        from src.models.expense import Expense
        from src.services.budget import next_due

        # Start on Jan 31, today is Feb 1.
        # Next quarterly should be Apr 30 (last day of April).
        e = Expense(
            name="Quarterly",
            amount=300.0,
            currency="PLN",
            period="quarterly",
            category="",
            starts_on=date(2026, 1, 31),
            ends_on=None,
            notes="",
        )
        today = date(2026, 2, 1)
        result = next_due(e, today)
        # April has 30 days, so it should be clamped to 30.
        assert result == date(2026, 4, 30)

    def test_next_due_before_starts(self):
        """Next due when today is before starts_on returns starts_on."""
        from src.models.expense import Expense
        from src.services.budget import next_due

        e = Expense(
            name="Future",
            amount=100.0,
            currency="PLN",
            period="monthly",
            category="",
            starts_on=date(2026, 5, 1),
            ends_on=None,
            notes="",
        )
        today = date(2026, 1, 1)
        result = next_due(e, today)
        assert result == date(2026, 5, 1)

    def test_next_due_after_ended(self):
        """Next due for ended expense returns None."""
        from src.models.expense import Expense
        from src.services.budget import next_due

        e = Expense(
            name="Ended",
            amount=100.0,
            currency="PLN",
            period="monthly",
            category="",
            starts_on=date(2025, 1, 1),
            ends_on=date(2025, 12, 31),
            notes="",
        )
        today = date(2026, 1, 1)
        result = next_due(e, today)
        assert result is None

    def test_next_due_once(self):
        """Next due for once-only in the future returns starts_on."""
        from src.models.expense import Expense
        from src.services.budget import next_due

        e = Expense(
            name="One-off",
            amount=1000.0,
            currency="PLN",
            period="once",
            category="",
            starts_on=date(2026, 3, 15),
            ends_on=None,
            notes="",
        )
        today = date(2026, 1, 1)
        result = next_due(e, today)
        assert result == date(2026, 3, 15)

    def test_next_due_once_past(self):
        """Next due for once-only in the past returns None."""
        from src.models.expense import Expense
        from src.services.budget import next_due

        e = Expense(
            name="One-off",
            amount=1000.0,
            currency="PLN",
            period="once",
            category="",
            starts_on=date(2025, 3, 15),
            ends_on=None,
            notes="",
        )
        today = date(2026, 1, 1)
        result = next_due(e, today)
        assert result is None


def _yearly(start, end=None, amount=1200.0):
    from src.models.expense import Expense

    return Expense(name="Insurance", amount=amount, currency="PLN", period="yearly",
                   category="Car", starts_on=start, ends_on=end, notes="")


def test_next_due_is_this_years_charge_when_still_ahead():
    """Regression: a charge later this month must not jump a whole period."""
    from src.services.budget import next_due

    e = _yearly(date(2025, 3, 15))
    assert next_due(e, date(2026, 3, 10)) == date(2026, 3, 15)
    assert next_due(e, date(2026, 3, 15)) == date(2026, 3, 15)
    assert next_due(e, date(2026, 3, 16)) == date(2027, 3, 15)


def test_next_due_none_after_last_charge():
    from src.services.budget import next_due

    e = _yearly(date(2025, 3, 15), end=date(2026, 12, 31))
    assert next_due(e, date(2026, 4, 1)) is None


def test_committed_counts_yearly_in_full_in_its_month_only():
    """Regression: the cash view charges the whole amount, not 1/12 of it."""
    from src.services.budget import committed_for_month
    from src.services.price_service import PriceService

    e = _yearly(date(2025, 3, 15))
    ps = PriceService("PLN")
    assert committed_for_month([e], "2026-03", ps, "PLN")[0] == 1200.0
    assert committed_for_month([e], "2026-04", ps, "PLN")[0] == 0.0
