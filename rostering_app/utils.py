"""Utility functions for the rostering app."""
from datetime import date, datetime, timedelta
from typing import Set, List


def get_german_holidays_2025() -> Set[date]:
    """Get German national holidays for 2025."""
    return {
        date(2025, 1, 1),   # Neujahr
        date(2025, 1, 6),   # Heilige Drei Könige
        date(2025, 4, 18),  # Karfreitag
        date(2025, 4, 21),  # Ostermontag
        date(2025, 5, 1),   # Tag der Arbeit
        date(2025, 5, 29),  # Christi Himmelfahrt
        date(2025, 6, 9),   # Pfingstmontag
        date(2025, 10, 3),  # Tag der Deutschen Einheit
        date(2025, 12, 25), # Weihnachten
        date(2025, 12, 26), # Zweiter Weihnachtstag
    }


def get_german_holidays_2024() -> Set[date]:
    """Get German national holidays for 2024."""
    return {
        date(2024, 1, 1),   # Neujahr
        date(2024, 1, 6),   # Heilige Drei Könige
        date(2024, 3, 29),  # Karfreitag
        date(2024, 4, 1),   # Ostermontag
        date(2024, 5, 1),   # Tag der Arbeit
        date(2024, 5, 9),   # Christi Himmelfahrt
        date(2024, 5, 20),  # Pfingstmontag
        date(2024, 10, 3),  # Tag der Deutschen Einheit
        date(2024, 12, 25), # Weihnachten
        date(2024, 12, 26), # Zweiter Weihnachtstag
    }


def get_german_holidays_2026() -> Set[date]:
    """Get German national holidays for 2026."""
    return {
        date(2026, 1, 1),   # Neujahr
        date(2026, 1, 6),   # Heilige Drei Könige
        date(2026, 4, 3),   # Karfreitag
        date(2026, 4, 6),   # Ostermontag
        date(2026, 5, 1),   # Tag der Arbeit
        date(2026, 5, 14),  # Christi Himmelfahrt
        date(2026, 5, 25),  # Pfingstmontag
        date(2026, 10, 3),  # Tag der Deutschen Einheit
        date(2026, 12, 25), # Weihnachten
        date(2026, 12, 26), # Zweiter Weihnachtstag
    }


def get_holidays_for_year(year: int) -> Set[date]:
    """Get German national holidays for a specific year."""
    if year == 2024:
        return get_german_holidays_2024()
    elif year == 2025:
        return get_german_holidays_2025()
    elif year == 2026:
        return get_german_holidays_2026()
    else:
        # For other years, return an empty set or implement a more sophisticated calculation
        return set()


def is_holiday(check_date: date) -> bool:
    """Check if a date is a German national holiday."""
    return check_date in get_holidays_for_year(check_date.year)


def is_sunday(check_date: date) -> bool:
    """Check if a date is a Sunday."""
    return check_date.weekday() == 6


def is_non_working_day(check_date: date, company) -> bool:
    """Check if a date is a non-working day (holiday or Sunday if company doesn't work Sundays)."""
    if is_holiday(check_date):
        return True
    if is_sunday(check_date) and not company.sunday_is_workday:
        return True
    return False


def get_working_days_in_range(start_date: date, end_date: date, company) -> List[date]:
    """Get all working days in a date range."""
    working_days = []
    current = start_date
    while current <= end_date:
        if not is_non_working_day(current, company):
            working_days.append(current)
        current = current + timedelta(days=1)
    return working_days


def get_non_working_days_in_range(start_date: date, end_date: date, company) -> List[date]:
    """Get all non-working days in a date range."""
    non_working_days = []
    current = start_date
    while current <= end_date:
        if is_non_working_day(current, company):
            non_working_days.append(current)
        current = current + timedelta(days=1)
    return non_working_days


def get_shift_display_name(shift_name: str) -> str:
    """Get German display name for a shift."""
    shift_translations = {
        'EarlyShift': 'Frühschicht',
        'MorningShift': 'Morgenschicht',
        'LateShift': 'Spätschicht',
        'NightShift': 'Nachtschicht',
    }
    return shift_translations.get(shift_name, shift_name) 