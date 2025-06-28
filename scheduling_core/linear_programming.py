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
            expected_monthly_hours = emp.max_hours_per_week * 4.33  # Average weeks per month
            max_overtime = expected_monthly_hours * 0.2

            for month_key in months:
                # Limit overtime to something reasonable (e.g., 20% of expected hours)
                overtime_vars[(emp.id, month_key)] = LpVariable(
                    f"overtime_{emp.id}_{month_key[0]}_{month_key[1]}",
                    lowBound=0,
                    upBound=max_overtime
                )
                undertime_vars[(emp.id, month_key)] = LpVariable(
                    f"undertime_{emp.id}_{month_key[0]}_{month_key[1]}",
                    lowBound=0
                )

        # Objective: Minimize understaffing, overstaffing, and monthly overtime/undertime
        # Weights for different penalty components
        w_understaff = 1000  # High penalty for understaffing
        w_overstaff = 100    # Medium penalty for overstaffing
        w_overtime = 50      # Higher penalty for overtime to discourage it
        w_undertime = 30     # Increased penalty for undertime to encourage fuller utilization
        w_fairness = 20      # Penalty for deviation from average hours
        w_preference = -5    # Bonus for preferred shifts

        objective = 0

        # Add fairness component - penalize deviation from average hours
        # Create variables for total hours per employee
        total_hours_vars = {}
        for emp in problem.employees:
            total_hours_vars[emp.id] = LpVariable(
                f"total_hours_{emp.id}",
                lowBound=0
            )

        # Variable for average hours
        avg_hours_var = LpVariable("avg_hours", lowBound=0)

        # Variables for absolute deviation from average
        deviation_vars = {}
        for emp in problem.employees:
            deviation_vars[emp.id] = LpVariable(
                f"deviation_{emp.id}",
                lowBound=0
            )

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
                objective += w_undertime * undertime_vars[(emp.id, month_key)]

        # Penalty for unfair distribution (deviation from average)
        for emp in problem.employees:
            objective += w_fairness * deviation_vars[emp.id]

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
            # Hard limit: no more than weekly_max * 5 hours per month (accounting for 5-week months)
            monthly_hard_limit = emp.max_hours_per_week * 5

            for month_key, month_dates in months.items():
                # Calculate hours worked in this month using proper linear expressions
                monthly_hours_expr = 0

                # Add hours for each shift in this month
                for date in month_dates:
                    for shift in problem.shifts:
                        if shift.end >= shift.start:  # Day shift
                            monthly_hours_expr += variables[(emp.id, date, shift.id)] * shift.duration
                        else:  # Night shift - need to split hours
                            # Calculate hours before and after midnight
                            hours_before_midnight = (
                                datetime.combine(date, datetime.min.time().replace(hour=23, minute=59, second=59)) -
                                datetime.combine(date, shift.start)
                            ).total_seconds() / 3600 + 0.0167  # +1 minute

                            # Hours before midnight count for this date's month
                            monthly_hours_expr += variables[(emp.id, date, shift.id)] * hours_before_midnight

                # Account for spillover hours from previous month's night shifts
                if month_key[1] > 1:  # Not January
                    prev_month_last_day = dates[dates.index(month_dates[0]) - 1] if dates.index(month_dates[0]) > 0 else None
                else:  # January
                    prev_month_last_day = None

                if prev_month_last_day and prev_month_last_day >= problem.start_date:
                    for shift in problem.shifts:
                        if shift.end < shift.start:  # Night shift
                            # Calculate hours after midnight
                            hours_after_midnight = (
                                datetime.combine(prev_month_last_day + timedelta(days=1), shift.end) -
                                datetime.combine(prev_month_last_day + timedelta(days=1), datetime.min.time())
                            ).total_seconds() / 3600

                            # Add these hours to current month
                            monthly_hours_expr += variables[(emp.id, prev_month_last_day, shift.id)] * hours_after_midnight

                # Monthly hours = expected - undertime + overtime
                lp_problem += (
                    monthly_hours_expr == expected_monthly_hours -
                    undertime_vars[(emp.id, month_key)] +
                    overtime_vars[(emp.id, month_key)],
                    f"monthly_hours_{emp.id}_{month_key[0]}_{month_key[1]}"
                )

                # Add hard constraint: monthly hours cannot exceed the hard limit
                lp_problem += (
                    monthly_hours_expr <= monthly_hard_limit,
                    f"monthly_hours_hard_limit_{emp.id}_{month_key[0]}_{month_key[1]}"
                )

        # 7. Calculate total hours per employee for fairness
        for emp in problem.employees:
            total_hours_expr = lpSum(
                variables[(emp.id, date, shift.id)] * shift.duration
                for date in dates
                for shift in problem.shifts
            )
            lp_problem += (
                total_hours_vars[emp.id] == total_hours_expr,
                f"total_hours_{emp.id}"
            )

        # 8. Calculate average hours
        lp_problem += (
            avg_hours_var * len(problem.employees) == lpSum(total_hours_vars[emp.id] for emp in problem.employees),
            "average_hours"
        )

        # 9. Calculate deviations from average (absolute value approximation)
        for emp in problem.employees:
            # deviation >= total_hours - avg_hours
            lp_problem += (
                deviation_vars[emp.id] >= total_hours_vars[emp.id] - avg_hours_var,
                f"deviation_pos_{emp.id}"
            )
            # deviation >= avg_hours - total_hours
            lp_problem += (
                deviation_vars[emp.id] >= avg_hours_var - total_hours_vars[emp.id],
                f"deviation_neg_{emp.id}"
            )

        # 10. Minimum utilization constraint - ensure employees get at least 70% of their potential hours
        for emp in problem.employees:
            min_annual_hours = emp.max_hours_per_week * 52 * 0.7  # 70% utilization
            lp_problem += (
                total_hours_vars[emp.id] >= min_annual_hours,
                f"min_utilization_{emp.id}"
            )

        # 11. Ensure feasibility - add a constraint to prevent infeasible solutions
        # If the total available work hours is less than required, we need to relax constraints
        total_available_hours = sum(
            emp.max_hours_per_week * len(weeks)
            for emp in problem.employees
        )
        total_required_hours = sum(
            shift.min_staff * shift.duration * len(dates)
            for shift in problem.shifts
        )

        if total_required_hours > total_available_hours:
            print(f"[LP WARNING] Problem may be infeasible: required hours ({total_required_hours:.1f}) > available hours ({total_available_hours:.1f})")

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