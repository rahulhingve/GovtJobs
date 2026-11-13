from datetime import date
import pytest
from govjobs.utils import fmt_date, days_left, parse_to_iso_date, get_ist_today

def test_fmt_date():
    assert fmt_date(None) == "-"
    assert fmt_date("") == "-"
    assert fmt_date("2026-11-18") == "18/11/2026"
    assert fmt_date("18/11/2026") == "18/11/2026"

def test_days_left():
    fake_today = date(2026, 11, 13)
    # End date in 5 days
    assert days_left("2026-11-18", today=fake_today) == 5
    # End date today
    assert days_left("2026-11-13", today=fake_today) == 0
    # End date in the past
    assert days_left("2026-11-10", today=fake_today) == -3
    # No end date
    assert days_left(None, today=fake_today) is None

def test_parse_to_iso_date():
    # ISO input
    assert parse_to_iso_date("2026-11-18") == "2026-11-18"
    
    # Indian Day-first formats
    assert parse_to_iso_date("05/06/2026") == "2026-06-05"  # June 5, never May 6
    assert parse_to_iso_date("18.11.2026") == "2026-11-18"
    assert parse_to_iso_date("31-12-2026") == "2026-12-31"

    # Rejects invalid day
    with pytest.raises(ValueError):
        parse_to_iso_date("32/01/2026")

    # Rejects invalid month
    with pytest.raises(ValueError):
        parse_to_iso_date("15/13/2026")

    # Rejects month-first or invalid string format
    with pytest.raises(ValueError):
        parse_to_iso_date("November 18, 2026")
