from datetime import timedelta, datetime, date
from collections import defaultdict
from typing import List, Set, Tuple
from calendar import monthrange

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


class OptimizedILPScheduler(SchedulingAlgorithm):
    """Optimized ILP scheduler: consolidates constraints and uses utilization for fairness.

    Variable names are made explicit for readability.
    """

    def __init__(self, sundays_off: bool = False):
        self.sundays_off = sundays_off
        # store holidays as (year, month, day) tuples
        self.holidays: Set[Tuple[int, int, int]] = set()

    @property
    def name(self) -> str:
        return "Optimized ILP (Utilization)"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:
        # 1) Build the list of all dates in the horizon (inclusive)
        all_dates: List[date] = []
        current_day = problem.start_date
        while current_day <= problem.end_date:
            all_dates.append(current_day)
            current_day += timedelta(days=1)

        # 2) Populate holiday set for every year in range
        self.holidays.clear()
        for year in range(problem.start_date.year, problem.end_date.year + 1):
            for month, day in self._get_holidays_for_year(year):
                self.holidays.add((year, month, day))

        # 3) Weeks mapping {week_index: [date, ...]}
        week_to_dates = get_weeks(problem.start_date, problem.end_date)
        number_of_weeks = len(week_to_dates)

        # 4) Quick feasibility sanity check: available capacity vs required hours
        total_available_hours = sum(emp.max_hours_per_week for emp in problem.employees) * number_of_weeks
        total_required_hours = sum(
            shift.min_staff * shift.duration * len(all_dates)
            for shift in problem.shifts
        )
        if total_required_hours > total_available_hours and total_required_hours > 0:
            scale_factor = total_available_hours / total_required_hours
            for shift in problem.shifts:
                shift.min_staff = max(1, int(round(shift.min_staff * scale_factor)))
            print(f"[INFO] Scaled down min_staff by {scale_factor:.2f}× to restore feasibility.")

        # 5) Build only feasible assignment triples (employee, date, shift)
        feasible_assignments: List[Tuple[str, date, str]] = []
        for employee in problem.employees:
            for day in all_dates:
                if self._date_blocked(employee, day):
                    continue
                for shift in problem.shifts:
                    feasible_assignments.append((employee.id, day, shift.id))

        # 6) Binary decision variables for each feasible assignment
        assign_var = {
            (emp_id, day, shift_id): LpVariable(f"x_{emp_id}_{day}_{shift_id}", cat=LpBinary)
            for (emp_id, day, shift_id) in feasible_assignments
        }

        # 7) Group dates by month: {(year, month): [dates_in_month]}
        month_to_dates = defaultdict(list)
        for day in all_dates:
            month_to_dates[(day.year, day.month)].append(day)

        # Create overtime / undertime variables and store expected hours per employee & month
        monthly_overtime_var = {}
        monthly_undertime_var = {}
        monthly_expected_hours = {}
        for employee in problem.employees:
            for (year, month), month_days in month_to_dates.items():
                expected_hours = self._expected_month_hours(employee, year, month)
                monthly_expected_hours[(employee.id, (year, month))] = expected_hours

                overtime_cap_hours = 0.2 * expected_hours  # 20% max OT
                key = (employee.id, (year, month))

                monthly_overtime_var[key] = LpVariable(
                    f"ot_{employee.id}_{year}_{month}", lowBound=0, upBound=overtime_cap_hours
                )
                monthly_undertime_var[key] = LpVariable(
                    f"ut_{employee.id}_{year}_{month}", lowBound=0
                )

        # 8) Create LP model
        model = LpProblem("EmployeeScheduling", LpMinimize)

        # 9) Total planned hours vars & utilization expressions
        total_hours_var = {
            employee.id: LpVariable(f"total_hours_{employee.id}", lowBound=0)
            for employee in problem.employees
        }

        utilization_expr = {}
        for employee in problem.employees:
            employee_absences = len(employee.absence_dates);
            yearly_capacity = employee.max_hours_per_week * 52 - (employee_absences * 8)
            utilization_expr[employee.id] = (
                total_hours_var[employee.id] / yearly_capacity if yearly_capacity > 0 else 0
            )

        # 10) Slack variables for under/over staffing per shift/day
        coverage_slack_vars = {}

        # 11) Objective weights (tune as needed)
        WEIGHT_UNDERSTAFF      = 1_000_000
        WEIGHT_OVERSTAFF       = 100_000
        WEIGHT_OVERTIME        = 50
        WEIGHT_UNDERTIME       = 30
        WEIGHT_UTILIZATION_GAP = -1000   # encourage high utilization (1 - util)
        WEIGHT_PREFERENCE      = -5
        WEIGHT_SHIFT_FAIRNESS  = 10_000  # penalize coverage imbalance

        # 12) Build objective expression
        objective_expr = 0

        # 12a) Coverage slack & fairness
        for day in all_dates:
            for shift in problem.shifts:
                under_var = LpVariable(f"under_{day}_{shift.id}", lowBound=0)
                over_var  = LpVariable(f"over_{day}_{shift.id}",  lowBound=0)
                coverage_slack_vars[(day, shift.id, 'under')] = under_var
                coverage_slack_vars[(day, shift.id, 'over')]  = over_var

                employees_assigned = lpSum(
                    assign_var[(e.id, day, shift.id)]
                    for e in problem.employees
                    if (e.id, day, shift.id) in assign_var
                )

                objective_expr += WEIGHT_UNDERSTAFF * under_var + WEIGHT_OVERSTAFF * over_var
                # fairness term (linear: denominator is constant)
                objective_expr += WEIGHT_SHIFT_FAIRNESS * ((shift.max_staff - employees_assigned) / shift.max_staff)

        # 12b) Overtime/undertime & utilization & preferences
        for employee in problem.employees:
            for ym in month_to_dates.keys():
                objective_expr += WEIGHT_OVERTIME  * monthly_overtime_var[(employee.id, ym)]
                objective_expr += WEIGHT_UNDERTIME * monthly_undertime_var[(employee.id, ym)]

            objective_expr += WEIGHT_UTILIZATION_GAP * (1 - utilization_expr[employee.id])

            for day in all_dates:
                for shift in problem.shifts:
                    if (employee.id, day, shift.id) in assign_var and shift.name in getattr(employee, 'preferred_shifts', []):
                        objective_expr += WEIGHT_PREFERENCE * assign_var[(employee.id, day, shift.id)]

        model += objective_expr

        # ------------------------------------------------------------------
        # Constraints
        # ------------------------------------------------------------------

        # (1) Max one shift per employee per day
        for employee in problem.employees:
            for day in all_dates:
                model += (
                    lpSum(assign_var[(employee.id, day, s.id)]
                          for s in problem.shifts
                          if (employee.id, day, s.id) in assign_var) <= 1
                )

        # (2) Staffing requirements with slack vars
        for day in all_dates:
            for shift in problem.shifts:
                assigned_count = lpSum(assign_var[(e.id, day, shift.id)]
                                        for e in problem.employees
                                        if (e.id, day, shift.id) in assign_var)
                model += assigned_count + coverage_slack_vars[(day, shift.id, 'under')] >= shift.min_staff
                model += assigned_count - coverage_slack_vars[(day, shift.id, 'over')]  <= shift.max_staff

        # (3) Weekly contract cap
        for employee in problem.employees:
            for week_idx, week_dates in week_to_dates.items():
                model += (
                    lpSum(assign_var[(employee.id, d, s.id)] * s.duration
                          for d in week_dates
                          for s in problem.shifts
                          if (employee.id, d, s.id) in assign_var) <= employee.max_hours_per_week
                )

        # (4) 11h rest rule between consecutive days
        for employee in problem.employees:
            for i in range(len(all_dates) - 1):
                d1, d2 = all_dates[i], all_dates[i + 1]
                for s1 in problem.shifts:
                    for s2 in problem.shifts:
                        if (employee.id, d1, s1.id) in assign_var and (employee.id, d2, s2.id) in assign_var:
                            if self._violates_rest_period(s1, s2, d1):
                                model += assign_var[(employee.id, d1, s1.id)] + assign_var[(employee.id, d2, s2.id)] <= 1

        # (5) Monthly hours balance + hard OT cap
        MONTHLY_OVERTIME_CAP_FACTOR = 1.15  # 15% cap over expected
        for employee in problem.employees:
            for ym, month_days in month_to_dates.items():
                expected_hours = monthly_expected_hours[(employee.id, ym)]
                worked_hours_expr = lpSum(
                    assign_var[(employee.id, d, s.id)] * s.duration
                    for d in month_days for s in problem.shifts
                    if (employee.id, d, s.id) in assign_var and s.end >= s.start  # skip overnight if needed
                )
                # balance equation
                model += worked_hours_expr == expected_hours - monthly_undertime_var[(employee.id, ym)] + monthly_overtime_var[(employee.id, ym)]
                # hard cap
                model += worked_hours_expr <= expected_hours * MONTHLY_OVERTIME_CAP_FACTOR

        # (6) Total hours across entire planning horizon + min utilization threshold
        for employee in problem.employees:
            model += total_hours_var[employee.id] == lpSum(
                assign_var[(employee.id, d, s.id)] * s.duration
                for d in all_dates for s in problem.shifts if (employee.id, d, s.id) in assign_var
            )
            employee_absences = len(employee.absence_dates);
            yearly_capacity = employee.max_hours_per_week * 52 - (employee_absences * 8)
            model += total_hours_var[employee.id] >= yearly_capacity * 0.90 # 85% min util

        # Solve
        solver = PULP_CBC_CMD(msg=False, timeLimit=300)
        status = model.solve(solver)
        print(f"[OptILP DEBUG] Status: {LpStatus[status]}")

        # Extract solution
        schedule_entries: List[ScheduleEntry] = []
        for (emp_id, day, shift_id), var in assign_var.items():
            if var.varValue and var.varValue > 0.5:
                schedule_entries.append(ScheduleEntry(emp_id, day, shift_id))
        return schedule_entries

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _date_blocked(self, employee, day: date) -> bool:
        """True if employee cannot work on `day` due to holiday/absence/Sunday off."""
        if (day.year, day.month, day.day) in self.holidays:
            return True
        if day in getattr(employee, 'absence_dates', set()):
            return True
        if self.sundays_off and day.weekday() == 6:
            return True
        return False

    def _expected_month_hours(self, employee, year: int, month: int) -> float:
        weekly_hours = getattr(employee, 'weekly_hours', getattr(employee, 'max_hours_per_week', 0))
        days_per_week = 6 if self.sundays_off else 7
        if days_per_week == 0:
            return 0.0

        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        day = start
        workable_days = 0
        while day <= end:
            if not self._date_blocked(employee, day):
                workable_days += 1
            day += timedelta(days=1)

        avg_daily_hours = weekly_hours / days_per_week
        raw_hours = avg_daily_hours * workable_days
        return round(raw_hours / 8) * 8  # nearest 8-hour block

    def _violates_rest_period(self, shift1: Shift, shift2: Shift, date1: date) -> bool:
        """Return True if the gap between shift1 (on date1) and shift2 (next day) is < 11h."""
        end_first = datetime.combine(date1, shift1.end)
        if shift1.end < shift1.start:
            end_first += timedelta(days=1)  # overnight shift wraps
        start_second = datetime.combine(date1 + timedelta(days=1), shift2.start)
        pause_hours = (start_second - end_first).total_seconds() / 3600
        return pause_hours < 11

    def _get_holidays_for_year(self, year: int) -> Set[Tuple[int, int]]:
        if year == 2024:
            return {
                (1, 1), (1, 6), (3, 29), (4, 1),
                (5, 1), (5, 9), (5, 20), (10, 3),
                (12, 25), (12, 26),
            }
        elif year == 2025:
            return {
                (1, 1), (1, 6), (4, 18), (4, 21),
                (5, 1), (5, 29), (6, 9), (10, 3),
                (12, 25), (12, 26),
            }
        elif year == 2026:
            return {
                (1, 1), (1, 6), (4, 3), (4, 6),
                (5, 1), (5, 14), (5, 25), (10, 3),
                (12, 25), (12, 26),
            }
        else:
            return set()
