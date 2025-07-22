from datetime import timedelta, datetime
from collections import defaultdict
from typing import List

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
    """Optimized ILP scheduler: consolidates constraints and uses utilization for fairness."""

    def __init__(self, sundays_off: bool = False):
        self.sundays_off = sundays_off
        self.holidays = set()

    @property
    def name(self) -> str:
        return "Optimized ILP (Utilization)"

    def _get_holidays_for_year(self, year: int) -> set:
        if year == 2024:
            return {
                (2024, 1, 1), (2024, 1, 6), (2024, 3, 29), (2024, 4, 1),
                (2024, 5, 1), (2024, 5, 9), (2024, 5, 20), (2024, 10, 3),
                (2024, 12, 25), (2024, 12, 26),
            }
        elif year == 2025:
            return {
                (2025, 1, 1), (2025, 1, 6), (2025, 4, 18), (2025, 4, 21),
                (2025, 5, 1), (2025, 5, 29), (2025, 6, 9), (2025, 10, 3),
                (2025, 12, 25), (2025, 12, 26),
            }
        elif year == 2026:
            return {
                (2026, 1, 1), (2026, 1, 6), (2026, 4, 3), (2026, 4, 6),
                (2026, 5, 1), (2026, 5, 14), (2026, 5, 25), (2026, 10, 3),
                (2026, 12, 25), (2026, 12, 26),
            }
        else:
            return set()

    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:
        # 1) Build the full list of dates
        current = problem.start_date
        dates = []
        while current <= problem.end_date:
            dates.append(current)
            current += timedelta(days=1)

        # 2) Populate holidays for the date range
        self.holidays = set()
        for year in range(problem.start_date.year, problem.end_date.year + 1):
            self.holidays.update(self._get_holidays_for_year(year))

        # 3) Compute weeks
        weeks = get_weeks(problem.start_date, problem.end_date)
        num_weeks = len(weeks)

        # 4) Pre-check capacity vs. demand & scale min_staff if needed
        total_emp_hours = sum(emp.max_hours_per_week for emp in problem.employees) * num_weeks
        total_req_hours = sum(
            shift.min_staff * shift.duration * len(dates)
            for shift in problem.shifts
        )
        if total_req_hours > total_emp_hours:
            scale = total_emp_hours / total_req_hours
            for shift in problem.shifts:
                shift.min_staff = max(1, int(round(shift.min_staff * scale)))
            print(f"[INFO] Scaled down min_staff by {scale:.2f}× to restore feasibility.")

        # 5) Build feasible assignment set
        feasible_assignments = []
        for emp in problem.employees:
            for date in dates:
                is_holiday = (date.year, date.month, date.day) in self.holidays
                is_absent = date in emp.absence_dates
                is_sunday = (date.weekday() == 6 and self.sundays_off)
                if is_holiday or is_absent or is_sunday:
                    continue
                for shift in problem.shifts:
                    feasible_assignments.append((emp.id, date, shift.id))

        # 6) Decision variables only for feasible assignments
        vars_x = {
            (eid, dt, sid): LpVariable(f"x_{eid}_{dt}_{sid}", cat=LpBinary)
            for (eid, dt, sid) in feasible_assignments
        }

        # 7) Objective: staffing slack, overtime, undertime, preferences, utilization fairness
        months = defaultdict(list)
        for date in dates:
            months[(date.year, date.month)].append(date)
        overtime = {}
        undertime = {}
        for emp in problem.employees:
            exp_hours = emp.max_hours_per_week * 4.33
            max_ot = exp_hours * 0.2
            for mk in months:
                overtime[(emp.id, mk)] = LpVariable(f"ot_{emp.id}_{mk[0]}_{mk[1]}", lowBound=0, upBound=max_ot)
                undertime[(emp.id, mk)] = LpVariable(f"ut_{emp.id}_{mk[0]}_{mk[1]}", lowBound=0)

        # Initialize LP problem (this was missing)
        lp_problem = LpProblem("EmployeeScheduling", LpMinimize)

        # Utilization variables
        total_hours = {}
        utilization = {}
        for emp in problem.employees:
            total_hours[emp.id] = LpVariable(f"total_hours_{emp.id}", lowBound=0)
            # Possible hours = max_hours_per_week * weeks_workable (not counting absences/holidays)
            possible_days = [d for d in dates if (d not in emp.absence_dates and not (d.weekday()==6 and self.sundays_off) and (d.year, d.month, d.day) not in self.holidays)]
            possible_hours = len(possible_days) * sum(s.duration for s in problem.shifts) / len(problem.shifts) if problem.shifts else 0
            # Use yearly capacity as denominator for fairness
            yearly_capacity = emp.max_hours_per_week * 52
            utilization[emp.id] = total_hours[emp.id] / yearly_capacity if yearly_capacity > 0 else 0

        slack = {}
        w_understaff = 1_000_000
        w_overstaff  = 100_000
        w_overtime   = 50
        w_undertime  = 30
        w_utilization = -1000  # Encourage high utilization, penalize low
        w_preference = -5
        w_shift_fairness = 10000  # Penalty for shift coverage imbalance

        objective = 0
        for date in dates:
            for shift in problem.shifts:
                u = LpVariable(f"under_{date}_{shift.id}", lowBound=0)
                o = LpVariable(f"over_{date}_{shift.id}", lowBound=0)
                slack[(date, shift.id, 'under')] = u
                slack[(date, shift.id, 'over')]  = o
                objective += w_understaff * u + w_overstaff * o
                # Add a penalty to the objective for the relative (fractional) under-coverage of this shift.
                # This encourages the solver to fill all shifts as evenly as possible, regardless of their absolute size.
                assigned = lpSum(vars_x[(e.id, date, shift.id)] for e in problem.employees if (e.id, date, shift.id) in vars_x)
                objective += w_shift_fairness * ((shift.max_staff - assigned) / shift.max_staff)

        for emp in problem.employees:
            for mk in months:
                objective += w_overtime * overtime[(emp.id, mk)]
                objective += w_undertime * undertime[(emp.id, mk)]
            # Utilization fairness: encourage utilization close to 0.9 (90%)
            objective += w_utilization * (1 - utilization[emp.id])
            for date in dates:
                for shift in problem.shifts:
                    if (emp.id, date, shift.id) in vars_x and shift.name in emp.preferred_shifts:
                        objective += w_preference * vars_x[(emp.id, date, shift.id)]
        lp_problem += objective

        # 1) One shift per day
        for emp in problem.employees:
            for date in dates:
                lp_problem += (
                    lpSum(vars_x[(emp.id, date, s.id)] for s in problem.shifts if (emp.id, date, s.id) in vars_x) <= 1
                )

        # 2) Staffing with slack
        for date in dates:
            for shift in problem.shifts:
                count = lpSum(vars_x[(e.id, date, shift.id)] for e in [emp for emp in problem.employees if (emp.id, date, shift.id) in vars_x])
                lp_problem += count + slack[(date, shift.id, 'under')] >= shift.min_staff
                lp_problem += count - slack[(date, shift.id, 'over')]  <= shift.max_staff

        # 3) Weekly hours
        for emp in problem.employees:
            for wk, wk_dates in weeks.items():
                lp_problem += (
                    lpSum(vars_x[(emp.id, d, s.id)] * s.duration for d in wk_dates for s in problem.shifts if (emp.id, d, s.id) in vars_x)
                    <= emp.max_hours_per_week
                )

        # 4) Rest period (11h)
        for emp in problem.employees:
            for i in range(len(dates)-1):
                d1, d2 = dates[i], dates[i+1]
                for s1 in problem.shifts:
                    for s2 in problem.shifts:
                        if (emp.id, d1, s1.id) in vars_x and (emp.id, d2, s2.id) in vars_x:
                            if self._violates_rest_period(s1, s2, d1):

                                lp_problem += vars_x[(emp.id, d1, s1.id)] + vars_x[(emp.id, d2, s2.id)] <= 1

        # 5) Monthly hours and hard limit
        overtime_cap = 1.15  # Allow up to 15% overtime per month (adjustable)
        for emp in problem.employees:
            days_per_week = 6 if self.sundays_off else 7
            avg_daily_hours = emp.max_hours_per_week / days_per_week
            for mk, mdates in months.items():
                # Only count days employee could actually work
                possible_days = [
                    d for d in mdates
                    if d not in emp.absence_dates
                    and not (d.weekday() == 6 and self.sundays_off)
                    and (d.year, d.month, d.day) not in self.holidays
                ]
                possible_month_hours = len(possible_days) * avg_daily_hours
                expr = lpSum(
                    vars_x[(emp.id, d, s.id)] * s.duration
                    for d in mdates for s in problem.shifts
                    if (emp.id, d, s.id) in vars_x and s.end >= s.start
                )
                lp_problem += expr == possible_month_hours - undertime[(emp.id, mk)] + overtime[(emp.id, mk)]
                lp_problem += expr <= possible_month_hours * overtime_cap

        # 6) Total hours
        for emp in problem.employees:
            # Set total_hours[emp.id] to the sum of all assigned shift hours for this employee.
            # This ensures total_hours[emp.id] always reflects the actual planned working hours for the employee over the entire planning period.
            lp_problem += total_hours[emp.id] == lpSum(vars_x[(emp.id, d, s.id)]*s.duration for d in dates for s in problem.shifts if (emp.id, d, s.id) in vars_x)
            # Min utilization (e.g. 75% of yearly capacity)
            lp_problem += total_hours[emp.id] >= emp.max_hours_per_week * 52 * 0.75

        # Solve
        solver = PULP_CBC_CMD(msg=False, timeLimit=300)
        status = lp_problem.solve(solver)
        print(f"[OptILP DEBUG] Status: {LpStatus[status]}")

        # Extract
        entries: List[ScheduleEntry] = []
        for (eid, dt, sid), v in vars_x.items():
            if v.varValue and v.varValue > 0.5:
                entries.append(ScheduleEntry(eid, dt, sid))
        return entries

    def _violates_rest_period(self, shift1: Shift, shift2: Shift, date1) -> bool:
        end1 = datetime.combine(date1, shift1.end)
        if shift1.end < shift1.start:
            end1 += timedelta(days=1)
        start2 = datetime.combine(date1 + timedelta(days=1), shift2.start)
        pause = (start2 - end1).total_seconds() / 3600
        return pause < 11
