"""Utility functions for the rostering app."""
import calendar
from datetime import date, timedelta
from typing import Set, List, Optional, Tuple


def get_german_holidays() -> Set[Tuple[int, int]]:
    """Get German national holidays as (month, day) tuples without year."""
    return {
        (1, 1),   # Neujahr
        (1, 6),   # Heilige Drei Könige
        (3, 29),  # Karfreitag (varies by year)
        (4, 1),   # Ostermontag (varies by year)
        (5, 1),   # Tag der Arbeit
        (5, 9),   # Christi Himmelfahrt (varies by year)
        (5, 20),  # Pfingstmontag (varies by year)
        (10, 3),  # Tag der Deutschen Einheit
        (12, 25), # Weihnachten
        (12, 26), # Zweiter Weihnachtstag
    }


def get_german_holidays_2024() -> Set[Tuple[int, int]]:
    """Get German national holidays for 2024 as (month, day) tuples."""
    return {
        (1, 1), (1, 6), (3, 29), (4, 1),
        (5, 1), (5, 9), (5, 20), (10, 3),
        (12, 25), (12, 26),
    }


def get_german_holidays_2025() -> Set[Tuple[int, int]]:
    """Get German national holidays for 2025 as (month, day) tuples."""
    return {
        (1, 1), (1, 6), (4, 18), (4, 21),
        (5, 1), (5, 29), (6, 9), (10, 3),
        (12, 25), (12, 26),
    }


def get_german_holidays_2026() -> Set[Tuple[int, int]]:
    """Get German national holidays for 2026 as (month, day) tuples."""
    return {
        (1, 1), (1, 6), (4, 3), (4, 6),
        (5, 1), (5, 14), (5, 25), (10, 3),
        (12, 25), (12, 26),
    }


def get_holidays_for_year(year: int) -> Set[Tuple[int, int]]:
    """Get German national holidays for a specific year as (month, day) tuples."""
    if year == 2024:
        return get_german_holidays_2024()
    elif year == 2025:
        return get_german_holidays_2025()
    elif year == 2026:
        return get_german_holidays_2026()
    else:
        # For other years, return the standard holidays (some may be wrong due to Easter variations)
        return get_german_holidays()


def is_holiday_date(check_date: date) -> bool:
    """Check if a date is a German national holiday using (month, day) tuples."""
    holidays = get_holidays_for_year(check_date.year)
    return (check_date.month, check_date.day) in holidays


def is_holiday(check_date: date) -> bool:
    """Check if a date is a German national holiday."""
    return is_holiday_date(check_date)


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


def workdays_in_month(year: int, month: int, company, holidays: Optional[Set[date]] = None) -> int:
    """
    Calculate the number of workdays in a month.
    
    Args:
        year: The year
        month: The month (1-12)
        company: Company object to check Sunday work policy
        holidays: Optional set of additional holidays to exclude
    
    Returns:
        Number of workdays in the month
    """
    if holidays is None:
        holidays = set()
    
    num_days = calendar.monthrange(year, month)[1]
    workdays = 0
    
    for day in range(1, num_days + 1):
        check_date = date(year, month, day)
        if not is_non_working_day(check_date, company) and check_date not in holidays:
            workdays += 1
    
    return workdays






def get_shift_display_name(shift_name: str) -> str:
    """Get German display name for a shift."""
    shift_translations = {
        'EarlyShift': 'Frühschicht',
        'MorningShift': 'Tagschicht',
        'LateShift': 'Spätschicht',
        'NightShift': 'Nachtschicht',
    }
    return shift_translations.get(shift_name, shift_name) 