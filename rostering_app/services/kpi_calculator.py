"""
KPI Calculator Service

This service consolidates all KPI calculations used throughout the application,
using the new_linear_programming.py implementation as the baseline for consistency.
"""
import calendar
from calendar import monthrange
from collections import defaultdict, Counter
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional, Set, Iterable

from rostering_app.utils import is_non_working_day, get_working_days_in_range

# ---------------------------------------------------------------------------
# Configuration / constants used across KPI calculations
# ---------------------------------------------------------------------------
WEEKLY_OVERRUN_FACTOR = 1.15  # 15% buffer over contract hours
WEEKLY_OVERRUN_BUFFER_HOURS = 2  # Additional tolerance in hours
ROUND_TO_HOURS = 8  # Round calculations to nearest 8-hour block


class KPICalculator:
    """
    Centralized KPI calculation service that consolidates all redundant calculations.
    Uses new_linear_programming.py as the baseline for consistent calculations.
    """

    def __init__(self, company):
        self.company = company
        self.sundays_off = not company.sunday_is_workday


    def is_date_blocked(self, employee, day: date) -> bool:
        # Use utils for company-wide non-working day
        if is_non_working_day(day, self.company):
            return True
        # Employee-specific absences
        if day in getattr(employee, 'absence_dates', set()):
            return True
        return False

    def is_planned_absence(self, employee, day: date) -> bool:
        """Check if a day is a planned absence (not including holidays/Sundays)."""
        # Only check employee-specific absences, not company-wide non-working days
        return day in getattr(employee, 'absence_dates', set())

    def workdays_in_month(self,year: int,
                           month: int,
                           workweek: Iterable[int],
                           company) -> int:
        """How many *working* days occur in the month?

        workweek : iterable of weekday ints (0=Mon … 6=Sun) on which the employee
                   normally works.
        company  : object passed through to `is_non_working_day`.
        """
        cal = calendar.Calendar()
        return sum(
            1
            for day in cal.itermonthdates(year, month)
            if (
                    day.month == month
                    and day.weekday() in workweek
                    and not is_non_working_day(day, company)  # <── NEW
            )
        )

    # -----------------------------------------------------------------------------
    # Patched KPI‑Calculator mix‑in functions
    # -----------------------------------------------------------------------------

    def calculate_expected_month_hours(self, employee, year: int, month: int, company=None) -> float:  # noqa: N802
        """Expected *contractual* hours in *year‑month* after deducting holidays & absences.

        *   **Shift length is fixed to 8 h** – any fractional daily workload is
            translated into *fewer full‑day shifts* rather than shorter days.
        *   Only **employee vacation days in this month** are deducted.  Public
            holidays and company‑wide non‑working days are already excluded from
            the base *working‑day* count via :pyfunc:`_workdays_in_month`.
        """
        if company is None:
            company = self.company  # fall back to the calculator‑wide default

        # 1) Contract parameters --------------------------------------------------
        weekly_hours = getattr(employee, "weekly_hours", getattr(employee, "max_hours_per_week", 0))
        if weekly_hours % 8 != 0:
            raise ValueError(
                f"Weekly hours {weekly_hours} for employee {employee} are not a multiple of the 8‑hour shift length."
            )
        shifts_per_week = weekly_hours // 8  # always an int (32→4, 40→5)

        company_workweek = getattr(company, "working_days_per_week", 5) or 5
        workweek_days = getattr(company, "workweek", list(range(company_workweek)))  # 0‑Mon …

        # 2) Company workdays in the target month --------------------------------
        workdays_in_month = self.workdays_in_month(year, month, workweek_days, company)

        # 3) Planned absences this month (vacation etc.) --------------------------
        absences_raw = getattr(employee, "absences", [])
        absence_dates: Set[date] = {date.fromisoformat(d) for d in absences_raw if isinstance(d, str)}
        # Consider *only* those falling on company workdays of the month
        first_day, last_day = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
        month_workdays: Set[date] = {d for d in (first_day + timedelta(days=n)  # type: ignore[attr-defined]
                                                 for n in range((last_day - first_day).days + 1))
                                     if d.weekday() in workweek_days and not is_non_working_day(d, company)}
        absences_this_month = absence_dates & month_workdays

        # 4) Expected *shifts* & hours -------------------------------------------
        expected_shifts_raw = (workdays_in_month * shifts_per_week) / company_workweek
        expected_shifts = round(expected_shifts_raw) - len(absences_this_month)
        expected_hours = expected_shifts * 8

        # 5) Round to nearest 8‑h block to stay compatible with the ILP model ----
        expected_hours = round(expected_hours / 8) * 8
        return max(expected_hours, 0)

    def calculate_expected_yearly_hours(self, employee, year: int) -> float:  # noqa: N802
        """Aggregate the *monthly* contractual hours (already holiday‑adjusted)."""
        total = 0.0
        for m in range(1, 13):
            total += self.calculate_expected_month_hours(employee, year, m)
        # Keep the original 8‑hour rounding for consistency
        return round(total / 8) * 8

    # def calculate_expected_month_hours(self, employee, year: int, month: int, company) -> float:
    #     # 1) Contracted hours --------------------------------------------
    #     weekly_hours = getattr(
    #         employee, "weekly_hours", getattr(employee, "max_hours_per_week", 0)
    #     )
    #     workweek = getattr(company, "working_days_per_week", 5) or 5
    #     daily_hours = weekly_hours / workweek
    #
    #     # 2) Date range ---------------------------------------------------
    #     last_day = calendar.monthrange(year, month)[1]
    #     month_start = date(year, month, 1)
    #     month_end = date(year, month, last_day)
    #
    #     # 3) Company working days in range -------------------------------
    #     working_days: Set[date] = set(
    #         get_working_days_in_range(month_start, month_end, company)
    #     )
    #
    #     # 4) Absences -----------------------------------------------------
    #     raw_absences: Set[date] = {
    #         date.fromisoformat(d)
    #         for d in getattr(employee, "absences", [])
    #         if isinstance(d, str)
    #     }
    #     absences_on_working_days = {d for d in raw_absences if d in working_days}
    #
    #     # 5) Expected hours ----------------------------------------------
    #     total_working_days = len(working_days)
    #     expected_hours = (total_working_days - len(absences_on_working_days)) * daily_hours
    #
    #     # 6)  rounding -------------------------------------------
    #     expected_hours = round(expected_hours / 8) * 8
    #
    #     return expected_hours
    #
    # def calculate_expected_yearly_hours(self, employee, year: int) -> float:
    #     weekly_hours = getattr(employee, "weekly_hours",
    #                            getattr(employee, "max_hours_per_week", 0))
    #
    #     absence_dates: Set[date] = {
    #         date.fromisoformat(d)
    #         for d in getattr(employee, "absences", [])
    #         if isinstance(d, str)
    #     }
    #
    #     total_hours = weekly_hours * 52 - len(absence_dates)
    #
    #     return total_hours
    #



    # def calculate_expected_month_hours(self, employee, year: int, month: int) -> float:
    #     # 1) Nominal hours for one week
    #     weekly_hours = getattr(
    #         employee, "weekly_hours",
    #         getattr(employee, "max_hours_per_week", 0)
    #     )
    #
    #     absences_raw = getattr(employee, 'absences', [])
    #     absence_dates: Set[date] = set()
    #     for d in absences_raw:
    #         try:
    #             absence_dates.add(date.fromisoformat(d))
    #         except Exception:
    #             pass
    #     # 3) Generate every calendar date in the requested month
    #     num_days = calendar.monthrange(year, month)[1]  # e.g. 31 for July
    #     month_days = {date(year, month, d) for d in range(1, num_days + 1)}
    #
    #     # 4) Intersection: only the absences that actually land in this month
    #     absences_this_month = absence_dates & month_days
    #
    #     # 5) Convert full-day absences to hours (assume 8 h per day)
    #     absences_hours = len(absences_this_month) * 8
    #
    #     # number_of_weeks_this_month = len(calendar.monthcalendar(year, month))
    #     number_of_weeks_this_month = 4.33
    #     # 6) Return planned hours minus the absence hours.
    #     expected_month_hours = weekly_hours * number_of_weeks_this_month - absences_hours
    #     expected_month_hours = round(expected_month_hours / 8) * 8  # round to nearest multiple of 8
    #     return expected_month_hours

    # def calculate_expected_yearly_hours(self, employee, year: int) -> float:
    #     total_hours = 0.0
    #     for month in range(1, 13):
    #         total_hours += self.calculate_expected_month_hours(employee, year, month, self.company)
    #     return total_hours
    #

    def violates_rest_period(self, shift1, shift2, date1: date) -> bool:
        end_first = datetime.combine(date1, shift1.end)
        if shift1.end < shift1.start:
            end_first += timedelta(days=1)  # overnight shift wraps
        start_second = datetime.combine(date1 + timedelta(days=1), shift2.start)
        pause_hours = (start_second - end_first).total_seconds() / 3600
        return pause_hours < 11

    def calculate_shift_hours_in_range(self, shift, shift_date: date, start_date: date, end_date: date) -> float:
        start = shift.start
        end = shift.end
        dt1 = datetime.combine(shift_date, start)
        dt2 = datetime.combine(shift_date, end)
        if dt2 < dt1:
            dt2 += timedelta(days=1)
        range_start = datetime.combine(start_date, start)
        range_end = datetime.combine(end_date, end)
        actual_start = max(dt1, range_start)
        actual_end = min(dt2, range_end)
        duration = (actual_end - actual_start).total_seconds() / 3600
        return max(duration, 0)

    def calculate_shift_hours_in_month(self, shift, shift_date: date, month_start_date: date,
                                       month_end_date: date) -> float:
        return self.calculate_shift_hours_in_range(shift, shift_date, month_start_date, month_end_date)

    def calculate_employee_hours(self, entries, start_date: date, end_date: date) -> Dict[int, float]:
        hours = defaultdict(float)
        for entry in entries:
            emp_id = entry.employee.id
            actual_hours = self.calculate_shift_hours_in_range(entry.shift, entry.date, start_date, end_date)
            hours[emp_id] += actual_hours
        return dict(hours)

    def calculate_employee_hours_with_month_boundaries(self, entries, month_start_date: date, month_end_date: date) -> \
    Dict[int, float]:
        return self.calculate_employee_hours(entries, month_start_date, month_end_date)

    def calculate_utilization_percentage(self, total_hours: float, max_monthly_hours: float) -> float:
        if max_monthly_hours > 0:
            return (total_hours / max_monthly_hours) * 100
        return 0.0

    def calculate_overtime_undertime(self, actual_hours: float, expected_hours: float) -> Tuple[float, float]:
        diff = actual_hours - expected_hours
        overtime = max(diff, 0)
        undertime = max(-diff, 0)
        return overtime, undertime

    def calculate_weekly_hours(self, entries, start_date: date, end_date: date) -> Dict[
        int, Dict[Tuple[int, int], float]]:
        weekly_hours = defaultdict(lambda: defaultdict(float))
        for entry in entries:
            if start_date <= entry.date <= end_date:
                emp_id = entry.employee.id
                week_key = entry.date.isocalendar()[:2]  # (year, week)
                hours = self.calculate_shift_hours_in_range(entry.shift, entry.date, start_date, end_date)
                weekly_hours[emp_id][week_key] += hours
        return dict(weekly_hours)

    def check_weekly_hours_violations(self, entries, start_date: date, end_date: date) -> Dict[int, int]:
        weekly_hours = self.calculate_weekly_hours(entries, start_date, end_date)
        from rostering_app.models import Employee
        violations = {}
        for emp_id, week_data in weekly_hours.items():
            employee = Employee.objects.get(id=emp_id)
            violations[emp_id] = sum(
                1 for hours in week_data.values()
                if hours > round((
                                             employee.max_hours_per_week * WEEKLY_OVERRUN_FACTOR) / ROUND_TO_HOURS) * ROUND_TO_HOURS + WEEKLY_OVERRUN_BUFFER_HOURS
                # Uses configurable constants
            )
        return violations

    def check_weekly_hours_violations_detailed(self, entries, start_date: date, end_date: date) -> Dict[str, Any]:
        """Get detailed weekly hours violations with actual hours worked."""
        weekly_hours = self.calculate_weekly_hours(entries, start_date, end_date)

        violations = {
            'total_violations': 0,
            'employee_violations': {},
            'detailed_violations': []
        }

        for emp_id, week_data in weekly_hours.items():
            from rostering_app.models import Employee
            employee = Employee.objects.get(id=emp_id)
            emp_violations = []

            for week_key, hours in week_data.items():
                # Round max_allowed to nearest 8-hour block (like the expected hours calculation)
                max_allowed_raw = employee.max_hours_per_week * WEEKLY_OVERRUN_FACTOR
                max_allowed = round(max_allowed_raw / ROUND_TO_HOURS) * ROUND_TO_HOURS

                # Only count as violation if significantly over (more than 2 hours over)
                if hours > max_allowed + WEEKLY_OVERRUN_BUFFER_HOURS:
                    violation = {
                        'employee_id': emp_id,
                        'employee_name': employee.name,
                        'week': week_key,
                        'actual_hours': hours,
                        'max_allowed': max_allowed,
                        'max_allowed_raw': max_allowed_raw,
                        'excess_hours': hours - max_allowed
                    }
                    emp_violations.append(violation)
                    violations['detailed_violations'].append(violation)

            violations['employee_violations'][emp_id] = len(emp_violations)
            violations['total_violations'] += len(emp_violations)

        return violations

    def check_rest_period_violations(self, entries, start_date: date, end_date: date) -> int:
        violations = 0
        employee_dates = defaultdict(dict)
        for entry in entries:
            if start_date <= entry.date <= end_date:
                emp_id = entry.employee.id
                if entry.date not in employee_dates[emp_id]:
                    employee_dates[emp_id][entry.date] = []
                employee_dates[emp_id][entry.date].append(entry.shift)
        for emp_id, dates_data in employee_dates.items():
            dates = sorted(dates_data.keys())
            for i in range(len(dates) - 1):
                d1, d2 = dates[i], dates[i + 1]
                if d2 - d1 == timedelta(days=1):  # Consecutive days
                    shifts1 = dates_data[d1]
                    shifts2 = dates_data[d2]
                    for shift1 in shifts1:
                        for shift2 in shifts2:
                            if self.violates_rest_period(shift1, shift2, d1):
                                violations += 1
        return violations

    def check_rest_period_violations_detailed(self, entries, start_date: date, end_date: date) -> Dict[str, Any]:
        """Get detailed rest period violations with specific conflicts."""
        violations = {
            'total_violations': 0,
            'employee_violations': {},
            'detailed_violations': []
        }

        employee_dates = defaultdict(dict)
        for entry in entries:
            if start_date <= entry.date <= end_date:
                emp_id = entry.employee.id
                if entry.date not in employee_dates[emp_id]:
                    employee_dates[emp_id][entry.date] = []
                employee_dates[emp_id][entry.date].append(entry.shift)

        for emp_id, dates_data in employee_dates.items():
            emp_violations = []
            dates = sorted(dates_data.keys())

            for i in range(len(dates) - 1):
                d1, d2 = dates[i], dates[i + 1]
                if d2 - d1 == timedelta(days=1):  # Consecutive days
                    shifts1 = dates_data[d1]
                    shifts2 = dates_data[d2]

                    for shift1 in shifts1:
                        for shift2 in shifts2:
                            if self.violates_rest_period(shift1, shift2, d1):
                                # Calculate actual rest period
                                end_first = datetime.combine(d1, shift1.end)
                                if shift1.end < shift1.start:
                                    end_first += timedelta(days=1)  # overnight shift wraps
                                start_second = datetime.combine(d2, shift2.start)
                                rest_hours = (start_second - end_first).total_seconds() / 3600

                                # Get employee name
                                try:
                                    from rostering_app.models import Employee
                                    employee = Employee.objects.get(id=emp_id)
                                    employee_name = employee.name
                                except Employee.DoesNotExist:
                                    employee_name = f"Employee {emp_id}"

                                violation = {
                                    'employee_id': emp_id,
                                    'employee_name': employee_name,
                                    'date1': d1.isoformat(),
                                    'date2': d2.isoformat(),
                                    'shift1_name': shift1.name,
                                    'shift2_name': shift2.name,
                                    'shift1_start': shift1.start.isoformat(),
                                    'shift1_end': shift1.end.isoformat(),
                                    'shift2_start': shift2.start.isoformat(),
                                    'shift2_end': shift2.end.isoformat(),
                                    'actual_rest_hours': rest_hours,
                                    'required_rest_hours': 11.0
                                }
                                emp_violations.append(violation)
                                violations['detailed_violations'].append(violation)

            violations['employee_violations'][emp_id] = len(emp_violations)
            violations['total_violations'] += len(emp_violations)

        return violations

    def calculate_employee_statistics(self, employee, entries, year: int, month: int,
                                      algorithm: Optional[str] = None) -> Dict[str, Any]:
        from rostering_app.utils import get_working_days_in_range
        month_start = date(year, month, 1)
        month_end = date(year, month, monthrange(year, month)[1])
        month_entries = [
            entry for entry in entries
            if entry.employee.id == employee.id and month_start <= entry.date <= month_end
        ]
        if algorithm:
            month_entries = [entry for entry in month_entries if entry.algorithm == algorithm]
        monthly_hours_worked = sum(
            self.calculate_shift_hours_in_month(entry.shift, entry.date, month_start, month_end)
            for entry in month_entries
        )
        monthly_shifts = len(month_entries)
        expected_monthly_hours = self.calculate_expected_month_hours(employee, year, month, self.company)
        overtime, undertime = self.calculate_overtime_undertime(monthly_hours_worked, expected_monthly_hours)
        utilization = self.calculate_utilization_percentage(monthly_hours_worked, expected_monthly_hours)
        working_days = get_working_days_in_range(month_start, month_end, self.company)
        days_worked = len(set(entry.date for entry in month_entries))
        possible_employee_days = sum(
            1 for day in working_days
            if not self.is_date_blocked(employee, day)
        )
        absence_days = max(possible_employee_days - days_worked, 0)

        # Calculate planned absences only (excluding holidays/Sundays)
        planned_absences = sum(
            1 for day in working_days
            if self.is_planned_absence(employee, day)
        )
        return {
            'employee_id': employee.id,
            'employee_name': getattr(employee, 'name', str(employee)),
            'monthly_hours_worked': monthly_hours_worked,
            'monthly_shifts': monthly_shifts,
            'expected_monthly_hours': expected_monthly_hours,
            'overtime_hours': overtime,
            'undertime_hours': undertime,
            'utilization_percentage': utilization,
            'absence_days': absence_days,
            'planned_absences': planned_absences,
            'days_worked': days_worked,
            'possible_days': possible_employee_days,
        }

    def calculate_company_analytics(self, entries, year: int, month: int, algorithm: Optional[str] = None) -> Dict[
        str, Any]:
        month_start = date(year, month, 1)
        month_end = date(year, month, monthrange(year, month)[1])
        month_entries = [
            entry for entry in entries
            if month_start <= entry.date <= month_end
        ]
        if algorithm:
            month_entries = [entry for entry in month_entries if entry.algorithm == algorithm]
        employee_hours = self.calculate_employee_hours_with_month_boundaries(month_entries, month_start, month_end)
        hours_list = list(employee_hours.values())
        total_hours_worked = sum(hours_list)
        avg_hours_per_employee = sum(hours_list) / len(hours_list) if hours_list else 0
        if len(hours_list) > 1:
            mean_hours = avg_hours_per_employee
            variance = sum((h - mean_hours) ** 2 for h in hours_list) / (len(hours_list) - 1)
            hours_std_dev = variance ** 0.5
            hours_cv = (hours_std_dev / avg_hours_per_employee * 100) if avg_hours_per_employee > 0 else 0
        else:
            hours_std_dev = 0
            hours_cv = 0
        gini_coefficient = self._calculate_gini_coefficient(hours_list)
        min_hours = min(hours_list) if hours_list else 0
        max_hours = max(hours_list) if hours_list else 0
        weekly_violations = self.check_weekly_hours_violations(entries, month_start, month_end)
        total_weekly_violations = sum(weekly_violations.values())
        rest_period_violations = self.check_rest_period_violations(entries, month_start, month_end)
        return {
            'total_hours_worked': total_hours_worked,
            'avg_hours_per_employee': avg_hours_per_employee,
            'hours_std_dev': hours_std_dev,
            'hours_cv': hours_cv,
            'gini_coefficient': gini_coefficient,
            'min_hours': min_hours,
            'max_hours': max_hours,
            'total_weekly_violations': total_weekly_violations,
            'rest_period_violations': rest_period_violations,
            'employee_hours': employee_hours,
            'weekly_violations': weekly_violations,
        }

    def _calculate_gini_coefficient(self, values: List[float]) -> float:
        n = len(values)
        total = sum(values)
        if n == 0 or total == 0:
            return 0.0
        if n == 1:
            return 0.0
        sorted_values = sorted(values)
        cumsum = sum((i + 1) * val for i, val in enumerate(sorted_values))
        return (2 * cumsum) / (n * total) - (n + 1) / n

    def calculate_coverage_stats(self, entries, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Return coverage stats for every shift over a date range (O(S+E) instead of O(S*E))."""
        from rostering_app.models import Shift

        working_days = get_working_days_in_range(start_date, end_date, self.company)
        total_working_days = len(working_days) or 1  # avoid division by zero

        # Build a Counter of shift_id -> number of assignments once (linear in E)
        shift_counter: Counter[int] = Counter(entry.shift_id for entry in entries)

        stats: List[Dict[str, Any]] = []
        for shift in Shift.objects.filter(company=self.company):
            assigned = shift_counter.get(shift.id, 0)
            avg_staff = assigned / total_working_days
            coverage_percentage = round((avg_staff / shift.max_staff) * 100, 1) if shift.max_staff > 0 else 0

            if avg_staff < shift.min_staff:
                status = "understaffed"
            elif avg_staff > shift.max_staff:
                status = "overstaffed"
            else:
                status = "optimal" if shift.min_staff <= avg_staff <= shift.max_staff else "ok"

            stats.append({
                "shift": {
                    "id": shift.id,
                    "name": shift.name,
                    "start_time": shift.start.isoformat(),
                    "end_time": shift.end.isoformat(),
                    "min_staff": shift.min_staff,
                    "max_staff": shift.max_staff,
                },
                "coverage_percentage": coverage_percentage,
                "avg_staff": round(avg_staff, 1),
                "status": status,
            })
        return stats
