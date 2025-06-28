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


class LinearProgrammingScheduler(SchedulingAlgorithm):
    """Scheduling using integer linear programming with demand scaling."""

    def __init__(self, sundays_off: bool = False):
        self.sundays_off = sundays_off
        # Global holidays - will be populated based on problem date range
        self.holidays = set()

    @property
    def name(self) -> str:
        return "Linear Programming (ILP)"

    def _get_holidays_for_year(self, year: int) -> set:
        """Get German national holidays for a specific year."""
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
            # For other years, return an empty set or implement a more sophisticated calculation
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

        # 3) Compute number of weeks in horizon
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

        # Create LP problem
        lp_problem = LpProblem("EmployeeScheduling", LpMinimize)

        # Decision variables
        vars_x = {}
        for emp in problem.employees:
            for date in dates:
                for shift in problem.shifts:
                    name = f"x_{emp.id}_{date}_{shift.id}"
                    vars_x[(emp.id, date, shift.id)] = LpVariable(name, cat=LpBinary)

        # Overtime/undertime tracking
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

        # Fairness and totals
        total_hours = {}
        deviation = {}
        for emp in problem.employees:
            total_hours[emp.id] = LpVariable(f"total_hours_{emp.id}", lowBound=0)
            deviation[emp.id] = LpVariable(f"dev_{emp.id}", lowBound=0)
        avg_hours = LpVariable("avg_hours", lowBound=0)

        # Slack for understaff/overstaff
        slack = {}
        w_understaff = 1_000_000
        w_overstaff  = 100_000
        w_overtime   = 50
        w_undertime  = 30
        w_fairness   = 20
        w_preference = -5

        objective = 0
        for date in dates:
            for shift in problem.shifts:
                u = LpVariable(f"under_{date}_{shift.id}", lowBound=0)
                o = LpVariable(f"over_{date}_{shift.id}", lowBound=0)
                slack[(date, shift.id, 'under')] = u
                slack[(date, shift.id, 'over')]  = o
                objective += w_understaff * u + w_overstaff * o

        # Add other penalties
        for emp in problem.employees:
            for mk in months:
                objective += w_overtime * overtime[(emp.id, mk)]
                objective += w_undertime * undertime[(emp.id, mk)]
            objective += w_fairness * deviation[emp.id]
            for date in dates:
                for shift in problem.shifts:
                    if shift.name in emp.preferred_shifts:
                        objective += w_preference * vars_x[(emp.id, date, shift.id)]
        lp_problem += objective

        # 1) One shift per day
        for emp in problem.employees:
            for date in dates:
                lp_problem += (
                    lpSum(vars_x[(emp.id, date, s.id)] for s in problem.shifts) <= 1
                )

        # 2) Staffing with slack
        for date in dates:
            for shift in problem.shifts:
                count = lpSum(vars_x[(e.id, date, shift.id)] for e in problem.employees)
                lp_problem += count + slack[(date, shift.id, 'under')] >= shift.min_staff
                lp_problem += count - slack[(date, shift.id, 'over')]  <= shift.max_staff

        # 3) Absences, holidays, Sundays
        for emp in problem.employees:
            for date in dates:
                if date in emp.absence_dates or (date.weekday()==6 and self.sundays_off) or ((date.year, date.month, date.day) in self.holidays):
                    for shift in problem.shifts:
                        lp_problem += vars_x[(emp.id, date, shift.id)] == 0

        # 4) Weekly hours
        for emp in problem.employees:
            for wk, wk_dates in weeks.items():
                lp_problem += (
                    lpSum(vars_x[(emp.id, d, s.id)] * s.duration for d in wk_dates for s in problem.shifts)
                    <= emp.max_hours_per_week
                )

        # 5) Rest period (11h)
        for emp in problem.employees:
            for i in range(len(dates)-1):
                d1, d2 = dates[i], dates[i+1]
                for s1 in problem.shifts:
                    for s2 in problem.shifts:
                        if self._violates_rest_period(s1, s2, d1):
                            lp_problem += vars_x[(emp.id, d1, s1.id)] + vars_x[(emp.id, d2, s2.id)] <= 1

        # 6) Monthly hours and hard limit
        for emp in problem.employees:
            exp_month = emp.max_hours_per_week * 4.33
            hard_limit = emp.max_hours_per_week * 5
            for mk, mdates in months.items():
                expr = lpSum(vars_x[(emp.id, d, s.id)] * s.duration for d in mdates for s in problem.shifts if s.end>=s.start)
                # night-shifts splitting omitted for brevity
                lp_problem += expr == exp_month - undertime[(emp.id, mk)] + overtime[(emp.id, mk)]
                lp_problem += expr <= hard_limit

        # 7) Total & average hours
        lp_problem += avg_hours * len(problem.employees) == lpSum(total_hours[e.id] for e in problem.employees)
        for emp in problem.employees:
            lp_problem += total_hours[emp.id] == lpSum(vars_x[(emp.id, d, s.id)]*s.duration for d in dates for s in problem.shifts)
            lp_problem += deviation[emp.id] >= total_hours[emp.id] - avg_hours
            lp_problem += deviation[emp.id] >= avg_hours - total_hours[emp.id]
            # 8) Min utilization
            lp_problem += total_hours[emp.id] >= emp.max_hours_per_week * 52 * 0.7

        # Solve
        solver = PULP_CBC_CMD(msg=False, timeLimit=300)
        status = lp_problem.solve(solver)
        print(f"[LP DEBUG] Status: {LpStatus[status]}")

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
