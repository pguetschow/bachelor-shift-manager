"""Utility functions for the rostering app."""
from datetime import date, datetime, timedelta
from typing import Set, List, Optional
import calendar


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


def monthly_hours(year: int, month: int, weekly_hours: float, company, holidays: Optional[Set[date]] = None) -> float:
    """
    Calculate possible monthly hours based on weekly hours and workdays.
    
    Args:
        year: The year
        month: The month (1-12)
        weekly_hours: Weekly working hours (e.g., 32, 40)
        company: Company object to check Sunday work policy
        holidays: Optional set of additional holidays to exclude
    
    Returns:
        Possible monthly hours (rounded to nearest multiple of 8)
    """
    workdays = workdays_in_month(year, month, company, holidays)
    days_per_week = 7 if company.sunday_is_workday else 6
    hours_per_day = weekly_hours / days_per_week
    raw_hours = workdays * hours_per_day
    
    # Round to nearest multiple of 8
    rounded_hours = round(raw_hours / 8) * 8
    return rounded_hours


def get_shift_display_name(shift_name: str) -> str:
    """Get German display name for a shift."""
    shift_translations = {
        'EarlyShift': 'Frühschicht',
        'MorningShift': 'Morgenschicht',
        'LateShift': 'Spätschicht',
        'NightShift': 'Nachtschicht',
    }
    return shift_translations.get(shift_name, shift_name) 