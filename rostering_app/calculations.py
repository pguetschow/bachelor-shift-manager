from datetime import time as pytime
from typing import List, Dict, Any


def to_time(val):
    # Helper to ensure value is a Python time object
    if isinstance(val, pytime):
        return val
    if hasattr(val, 'hour') and hasattr(val, 'minute') and hasattr(val, 'second'):
        return pytime(val.hour, val.minute, val.second)
    raise ValueError(f"Cannot convert {val} to time object")


# These functions have been moved to KPICalculator service
# Use KPICalculator.calculate_shift_hours_in_range() instead
# Use KPICalculator.calculate_shift_hours_in_month() instead  
# Use KPICalculator.calculate_employee_hours_with_month_boundaries() instead
# Use KPICalculator.calculate_utilization_percentage() instead


def calculate_coverage_stats(entries, start_date, end_date, company) -> List[Dict[str, Any]]:
    """
    Calculate coverage statistics for date range.
    Returns a list of dicts with shift and coverage info.
    """
    from rostering_app.services.kpi_calculator import KPICalculator
    kpi_calculator = KPICalculator(company)
    return kpi_calculator.calculate_coverage_stats(entries, start_date, end_date)
