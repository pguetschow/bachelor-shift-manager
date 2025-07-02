from datetime import date, timedelta, time as pytime
from typing import List, Dict, Any
from rostering_app.utils import get_working_days_in_range, monthly_hours


def to_time(val):
    # Helper to ensure value is a Python time object
    if isinstance(val, pytime):
        return val
    if hasattr(val, 'hour') and hasattr(val, 'minute') and hasattr(val, 'second'):
        return pytime(val.hour, val.minute, val.second)
    raise ValueError(f"Cannot convert {val} to time object")


def calculate_shift_hours_in_date_range(shift, shift_date: date, start_date: date, end_date: date) -> float:
    """
    Calculate the hours for a shift within a given date range (handles night shifts).
    """
    from datetime import datetime, timedelta
    start = to_time(shift.start)
    end = to_time(shift.end)
    dt1 = datetime.combine(shift_date, start)
    dt2 = datetime.combine(shift_date, end)
    if dt2 < dt1:
        dt2 += timedelta(days=1)
    # Clamp to range
    range_start = datetime.combine(start_date, start)
    range_end = datetime.combine(end_date, end)
    actual_start = max(dt1, range_start)
    actual_end = min(dt2, range_end)
    duration = (actual_end - actual_start).total_seconds() / 3600
    return max(duration, 0)


def calculate_shift_hours_in_month(shift, shift_date: date, month_start_date: date, month_end_date: date) -> float:
    """
    Calculate the hours for a shift within a given month (handles night shifts).
    """
    from datetime import datetime, timedelta
    start = to_time(shift.start)
    end = to_time(shift.end)
    dt1 = datetime.combine(shift_date, start)
    dt2 = datetime.combine(shift_date, end)
    if dt2 < dt1:
        dt2 += timedelta(days=1)
    # Clamp to month
    range_start = datetime.combine(month_start_date, start)
    range_end = datetime.combine(month_end_date, end)
    actual_start = max(dt1, range_start)
    actual_end = min(dt2, range_end)
    duration = (actual_end - actual_start).total_seconds() / 3600
    return max(duration, 0)


def calculate_employee_hours_with_month_boundaries(entries, month_start_date: date, month_end_date: date) -> Dict[int, float]:
    """
    Calculate total hours per employee, properly handling night shifts that overlap months.
    Returns a dict of employee_id -> total hours.
    """
    hours = {}
    for entry in entries:
        # Support both Django model and core dataclass
        emp_id = getattr(entry.employee, 'id', getattr(entry, 'employee_id', None))
        # For Django model, entry.shift is a Shift instance; for dataclass, it should be as well
        shift = entry.shift if hasattr(entry.shift, 'start') else getattr(entry, 'shift', None)
        shift_date = entry.date if isinstance(entry.date, date) else getattr(entry, 'date', None)
        if not isinstance(shift_date, date):
            from datetime import date as dt_date
            shift_date = dt_date.today()  # fallback to today if not a date
        actual_hours = calculate_shift_hours_in_month(shift, shift_date, month_start_date, month_end_date)
        hours[emp_id] = hours.get(emp_id, 0) + actual_hours
    return hours


def calculate_utilization_percentage(total_hours: float, max_monthly_hours: float) -> float:
    """
    Calculate utilization percentage based on total and possible monthly hours.
    """
    if max_monthly_hours > 0:
        return (total_hours / max_monthly_hours) * 100
    return 0.0


def calculate_coverage_stats(entries, start_date, end_date, company) -> List[Dict[str, Any]]:
    """
    Calculate coverage statistics for date range.
    Returns a list of dicts with shift and coverage info.
    """
    from rostering_app.models import Shift  # Import inside function
    stats = []
    # Import get_shift_status from views
    from rostering_app.views import get_shift_status
    for shift in Shift.objects.filter(company=company):  # type: ignore
        shift_entries = entries.filter(shift=shift)
        working_days = get_working_days_in_range(start_date, end_date, company)
        total_working_days = len(working_days)
        if total_working_days > 0:
            avg_staff = shift_entries.count() / total_working_days
            coverage_percentage = round((avg_staff / shift.max_staff) * 100, 1) if shift.max_staff > 0 else 0
            # Use get_shift_status to determine status
            status = get_shift_status(avg_staff, shift.min_staff, shift.max_staff)
            stats.append({
                'shift': {
                    'id': shift.id,
                    'name': shift.name,
                    'start_time': shift.start.isoformat(),
                    'end_time': shift.end.isoformat(),
                    'min_staff': shift.min_staff,
                    'max_staff': shift.max_staff
                },
                'coverage_percentage': coverage_percentage,
                'avg_staff': round(avg_staff, 1),
                'status': status
            })
    return stats 