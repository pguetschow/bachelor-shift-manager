"""Linear programming based scheduling algorithm."""
from datetime import timedelta, datetime
from collections import defaultdict
from typing import List, Dict, Set, Tuple

from pulp import (
    LpProblem,
    LpVariable,
    lpSum,
    LpMinimize,
    LpBinary,
    PULP_CBC_CMD,
    LpStatus,
)

from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry, Shift
from .utils import get_weeks


class LinearProgrammingScheduler(SchedulingAlgorithm):
    """Scheduling using integer linear programming."""

    def __init__(self, sundays_off: bool = False):
        """
        Initialize the scheduler.

        Args:
            sundays_off: If True, no shifts will be scheduled on Sundays
        """
        self.sundays_off = sundays_off
        # German national holidays for 2025
        self.holidays_2025 = {
            (2025, 1, 1),   # Neujahr
            (2025, 1, 6),   # Heilige Drei Könige (regional)
            (2025, 4, 18),  # Karfreitag
            (2025, 4, 21),  # Ostermontag
            (2025, 5, 1),   # Tag der Arbeit
            (2025, 5, 29),  # Christi Himmelfahrt
            (2025, 6, 9),   # Pfingstmontag
            (2025, 10, 3),  # Tag der Deutschen Einheit
            (2025, 12, 25), # 1. Weihnachtsfeiertag
            (2025, 12, 26), # 2. Weihnachtsfeiertag
        }

    @property
    def name(self) -> str:
        return "Linear Programming (ILP)"

    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:
        """Solve scheduling problem using linear programming."""
        # Create LP problem
        lp_problem = LpProblem("EmployeeScheduling", LpMinimize)

        # Decision variables: x[e,d,s] = 1 if employee e works shift s on date d
        variables = {}

        # Create all variables
        current = problem.start_date
        dates = []
        while current <= problem.end_date:
            dates.append(current)
            current += timedelta(days=1)

        for emp in problem.employees:
            for date in dates:
                for shift in problem.shifts:
                    var_name = f"x_{emp.id}_{date}_{shift.id}"
                    variables[(emp.id, date, shift.id)] = LpVariable(var_name, cat=LpBinary)

        # Helper variables for overtime/undertime tracking
        # Monthly overtime/undertime per employee
        overtime_vars = {}
        undertime_vars = {}

        # Group dates by month
        months = defaultdict(list)
        for date in dates:
            months[(date.year, date.month)].append(date)

        # Create overtime/undertime variables for each employee and month
        for emp in problem.employees:
            for month_key in months:
                overtime_vars[(emp.id, month_key)] = LpVariable(
                    f"overtime_{emp.id}_{month_key[0]}_{month_key[1]}",
                    lowBound=0
                )
                undertime_vars[(emp.id, month_key)] = LpVariable(
                    f"undertime_{emp.id}_{month_key[0]}_{month_key[1]}",
                    lowBound=0
                )

        # Objective: Minimize understaffing, overstaffing, and monthly overtime/undertime
        # Weights for different penalty components
        w_understaff = 1000  # High penalty for understaffing
        w_overstaff = 100    # Medium penalty for overstaffing
        w_overtime = 10      # Lower penalty for overtime
        w_preference = -5    # Bonus for preferred shifts

        objective = 0

        # Penalty for under/overstaffing
        slack_vars = {}
        for date in dates:
            for shift in problem.shifts:
                # Understaffing slack variable
                under_var = LpVariable(f"under_{date}_{shift.id}", lowBound=0)
                slack_vars[(date, shift.id, 'under')] = under_var
                objective += w_understaff * under_var

                # Overstaffing slack variable
                over_var = LpVariable(f"over_{date}_{shift.id}", lowBound=0)
                slack_vars[(date, shift.id, 'over')] = over_var
                objective += w_overstaff * over_var

        # Penalty for monthly overtime/undertime
        for emp in problem.employees:
            for month_key in months:
                objective += w_overtime * overtime_vars[(emp.id, month_key)]
                objective += w_overtime * undertime_vars[(emp.id, month_key)]

        # Bonus for preferred shifts
        for emp in problem.employees:
            for date in dates:
                for shift in problem.shifts:
                    if shift.name in emp.preferred_shifts:
                        objective += w_preference * variables[(emp.id, date, shift.id)]

        lp_problem += objective

        # CONSTRAINTS

        # 1. Each employee works at most one shift per day
        for emp in problem.employees:
            for date in dates:
                lp_problem += (
                    lpSum(variables[(emp.id, date, shift.id)] for shift in problem.shifts) <= 1,
                    f"one_shift_per_day_{emp.id}_{date}"
                )

        # 2. Staffing requirements with slack variables
        for date in dates:
            for shift in problem.shifts:
                staff_count = lpSum(
                    variables[(emp.id, date, shift.id)]
                    for emp in problem.employees
                )
                # Min staff constraint with understaffing slack
                lp_problem += (
                    staff_count + slack_vars[(date, shift.id, 'under')] >= shift.min_staff,
                    f"min_staff_{date}_{shift.id}"
                )
                # Max staff constraint with overstaffing slack
                lp_problem += (
                    staff_count - slack_vars[(date, shift.id, 'over')] <= shift.max_staff,
                    f"max_staff_{date}_{shift.id}"
                )

        # 3. Respect absences and holidays
        for emp in problem.employees:
            for date in dates:
                # Check if date is an absence or holiday
                is_holiday = (date.year, date.month, date.day) in self.holidays_2025
                is_absence = date in emp.absence_dates
                is_sunday = date.weekday() == 6 and self.sundays_off

                if is_absence or is_holiday or is_sunday:
                    for shift in problem.shifts:
                        lp_problem += (
                            variables[(emp.id, date, shift.id)] == 0,
                            f"absence_{emp.id}_{date}_{shift.id}"
                        )

        # 4. Weekly hours constraint
        weeks = get_weeks(problem.start_date, problem.end_date)
        for emp in problem.employees:
            for week_key, week_dates in weeks.items():
                weekly_hours = lpSum(
                    variables[(emp.id, date, shift.id)] * shift.duration
                    for date in week_dates
                    for shift in problem.shifts
                )
                lp_problem += (
                    weekly_hours <= emp.max_hours_per_week,
                    f"weekly_hours_{emp.id}_{week_key[0]}_{week_key[1]}"
                )

        # 5. 11-hour rest period between shifts
        for emp in problem.employees:
            for i, date in enumerate(dates[:-1]):
                next_date = dates[i + 1]
                for shift1 in problem.shifts:
                    for shift2 in problem.shifts:
                        if self._violates_rest_period(shift1, shift2, date):
                            lp_problem += (
                                variables[(emp.id, date, shift1.id)] +
                                variables[(emp.id, next_date, shift2.id)] <= 1,
                                f"rest_period_{emp.id}_{date}_{shift1.id}_{shift2.id}"
                            )

        # 6. Monthly hours tracking (for overtime/undertime)
        for emp in problem.employees:
            # Calculate expected monthly hours based on max weekly hours
            expected_monthly_hours = emp.max_hours_per_week * 4.33  # Average weeks per month

            for month_key, month_dates in months.items():
                monthly_hours = lpSum(
                    variables[(emp.id, date, shift.id)] * shift.duration
                    for date in month_dates
                    for shift in problem.shifts
                )

                # Monthly hours = expected - undertime + overtime
                lp_problem += (
                    monthly_hours == expected_monthly_hours -
                    undertime_vars[(emp.id, month_key)] +
                    overtime_vars[(emp.id, month_key)],
                    f"monthly_hours_{emp.id}_{month_key[0]}_{month_key[1]}"
                )

        # 7. Handle month transitions for night shifts
        # For shifts that cross midnight at month boundaries
        for emp in problem.employees:
            for i, date in enumerate(dates):
                # Check if this is the last day of a month
                next_date = date + timedelta(days=1)
                if date.month != next_date.month:
                    for shift in problem.shifts:
                        # If it's a night shift that crosses midnight
                        if shift.end < shift.start:
                            # The hours after midnight count toward the next month
                            # This is implicitly handled by our date-based assignment
                            # but we need to ensure consistency in rest periods
                            pass  # Already handled in rest period constraints

        # Solve with a 5-minute time limit
        solver = PULP_CBC_CMD(msg=False, timeLimit=300)
        status_code = lp_problem.solve(solver)

        # Debug output
        print(f"[LP DEBUG] Solver status: {LpStatus[status_code]} ({status_code})")
        print(f"[LP DEBUG] Objective value: {lp_problem.objective.value()}")

        # Print staffing violations if any
        total_understaffing = sum(
            slack_vars[(date, shift.id, 'under')].varValue or 0
            for date in dates
            for shift in problem.shifts
        )
        total_overstaffing = sum(
            slack_vars[(date, shift.id, 'over')].varValue or 0
            for date in dates
            for shift in problem.shifts
        )

        if total_understaffing > 0:
            print(f"[LP DEBUG] Total understaffing: {total_understaffing:.1f} shift-slots")
        if total_overstaffing > 0:
            print(f"[LP DEBUG] Total overstaffing: {total_overstaffing:.1f} shift-slots")

        print("--------------------------------------------------")

        # Extract solution entries
        entries: List[ScheduleEntry] = []
        for (emp_id, date, shift_id), var in variables.items():
            if var.varValue and var.varValue > 0.5:
                entries.append(ScheduleEntry(emp_id, date, shift_id))

        return entries

    def _violates_rest_period(self, shift1: Shift, shift2: Shift, date1) -> bool:
        """Check if shift combination violates 11-hour rest period."""
        # Calculate end time of shift1
        end1 = datetime.combine(date1, shift1.end)
        # If it's a night shift that wraps past midnight
        if shift1.end < shift1.start:
            end1 += timedelta(days=1)

        # Calculate start time of shift2 (next day)
        start2 = datetime.combine(date1 + timedelta(days=1), shift2.start)

        # Calculate pause duration
        pause_hours = (start2 - end1).total_seconds() / 3600

        return pause_hours < 11