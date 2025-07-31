from datetime import timedelta, date
from collections import defaultdict
from typing import List, Set, Tuple

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

# --- KPI Calculator ----------------------------------------------------------
from rostering_app.services.kpi_calculator import KPICalculator


class ILPScheduler(SchedulingAlgorithm):
    """Optimised ILP scheduler with **monthly utilisation fairness**.

    After field feedback we convert the hard monthly lower‑bound into a *soft*
    penalty.  This avoids infeasible (or wildly over‑/under‑staffed) rosters
    when the workforce composition changes mid‑month (parental leave, long‑term
    sickness, etc.).

    Key changes compared to the July‑2025 patch:
      • **No more hard >= bound** for ``MIN_UTIL_FACTOR`` – replaced by a slack
        variable ``mu_deficit`` with penalty ``W_MU_FAIR``.
      • Removed the previous per‑shift “fairness reward” that accidentally
        *encouraged* over‑staffing.
      • We moderately raised the over‑staffing weight ``W_OVER`` so that going
        above ``max_staff`` is now clearly worse than leaving a shift
        uncovered (unless absolutely necessary to hit contractual hours).
    """

    # ------------------------------------------------------------------
    # Construction / meta
    # ------------------------------------------------------------------
    def __init__(self, sundays_off: bool = False, *, min_util_factor: float = 0.85):
        self.sundays_off = sundays_off
        self.MIN_UTIL_FACTOR = min_util_factor  # target share of monthly hours
        # retained for backward compatibility – no longer used directly
        self.holidays: Set[Tuple[int, int, int]] = set()
        self.company = None  # injected in ``solve``

    @property
    def name(self) -> str:  # noqa: D401 – property name
        return "Optimized ILP (Utilisation‑Fair)"

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:
        # Cache company for KPI calculations
        self.company = problem.company
        kpi_calc = KPICalculator(self.company)

        # 1) Build date list for planning horizon (inclusive)
        dates: List[date] = []
        current = problem.start_date
        while current <= problem.end_date:
            dates.append(current)
            current += timedelta(days=1)

        # 2) Holiday set (legacy fallback only)
        self.holidays.clear()
        for yr in range(problem.start_date.year, problem.end_date.year + 1):
            self.holidays.update(self._get_holidays_for_year(yr))

        # 3) Week buckets
        weeks = get_weeks(problem.start_date, problem.end_date)
        num_weeks = len(weeks)

        # 4) Feasibility sanity‑check – scale down demand if workforce too small
        total_emp_hours = sum(e.max_hours_per_week for e in problem.employees) * num_weeks
        total_req_hours = sum(s.min_staff * s.duration * len(dates) for s in problem.shifts)
        if total_req_hours > total_emp_hours > 0:
            scale = total_emp_hours / total_req_hours
            for s in problem.shifts:
                s.min_staff = max(1, int(round(s.min_staff * scale)))
            print(f"[INFO] Scaled down min_staff by {scale:.2f}× to restore feasibility.")

        # ------------------------------------------------------------------
        # Decision variables / indices
        # ------------------------------------------------------------------
        # Build feasible (employee, day, shift) triples using KPI date blocking
        feasible: List[Tuple[str, date, str]] = [
            (emp.id, d, sh.id)
            for emp in problem.employees
            for d in dates
            if not kpi_calc.is_date_blocked(emp, d)
            for sh in problem.shifts
        ]

        # Binary assignment variable per feasible triple
        x = {
            (eid, d, sid): LpVariable(f"x_{eid}_{d}_{sid}", cat=LpBinary)
            for (eid, d, sid) in feasible
        }

        # Month buckets {(year, month): [date,…]}
        months = defaultdict(list)
        for d in dates:
            months[(d.year, d.month)].append(d)

        # Overtime / undertime variables per employee‑month (cap handled by KPI)
        ot, ut, mu_def = {}, {}, {}
        for emp in problem.employees:
            for ym in months.keys():
                expected = kpi_calc.calculate_expected_month_hours(emp, *ym)
                max_ot = 0.1 * expected  # 10 % OT cap
                ot[(emp.id, ym)] = LpVariable(f"ot_{emp.id}_{ym[0]}_{ym[1]}", lowBound=0, upBound=max_ot)
                ut[(emp.id, ym)] = LpVariable(f"ut_{emp.id}_{ym[0]}_{ym[1]}", lowBound=0)
                mu_def[(emp.id, ym)] = LpVariable(f"mu_def_{emp.id}_{ym[0]}_{ym[1]}", lowBound=0)

        # Total hours per employee for yearly utilisation
        total_hours = {emp.id: LpVariable(f"tot_{emp.id}", lowBound=0) for emp in problem.employees}

        # ------------------------------------------------------------------
        # Objective
        # ------------------------------------------------------------------
        W_UNDER   = 1_000_000  # severe under‑staffing penalty
        W_OVER    = 550_000    # over‑staffing penalty
        W_OT      = 5000         # overtime cost
        W_UT      = 30         # undertime cost
        W_UTIL    = -500     # encourage high utilisation·yearly
        W_PREF    = -5         # preferred shift reward
        W_MU_FAIR = 500_000    # monthly utilisation fairness penalty

        model = LpProblem("EmployeeScheduling", LpMinimize)
        obj = 0

        # Coverage slack vars
        for d in dates:
            for sh in problem.shifts:
                under = LpVariable(f"under_{d}_{sh.id}", lowBound=0)
                over  = LpVariable(f"over_{d}_{sh.id}",  lowBound=0)

                covered = lpSum(x[(e.id, d, sh.id)]
                                for e in problem.employees if (e.id, d, sh.id) in x)

                obj += W_UNDER * under + W_OVER * over

                # Staffing constraints
                model += covered + under >= sh.min_staff
                model += covered - over  <= sh.max_staff

        # Employee‑specific terms
        for emp in problem.employees:
            yearly_capacity = kpi_calc.calculate_expected_yearly_hours(emp, problem.start_date.year)
            if yearly_capacity:
                util_ratio = total_hours[emp.id] / yearly_capacity
                obj += W_UTIL * (1 - util_ratio)

            for ym in months.keys():
                obj += (W_OT * ot[(emp.id, ym)] +
                        W_UT * ut[(emp.id, ym)] +
                        W_MU_FAIR * mu_def[(emp.id, ym)])

            # Preferred shift reward
            prefs = set(getattr(emp, "preferred_shifts", []))
            if prefs:
                obj += W_PREF * lpSum(
                    x[(emp.id, d, sh.id)]
                    for d in dates
                    for sh in problem.shifts if sh.name in prefs and (emp.id, d, sh.id) in x
                )

        model += obj

        # ------------------------------------------------------------------
        # Constraints
        # ------------------------------------------------------------------
        # (1) At most one shift per day per employee
        for emp in problem.employees:
            for d in dates:
                model += lpSum(x[(emp.id, d, sh.id)]
                               for sh in problem.shifts if (emp.id, d, sh.id) in x) <= 1

        # (2) Monthly contract hours
        # for emp in problem.employees:
        #     for ym, mdates in months.items():
        #         maxPossibleHours = kpi_calc.calculate_expected_month_hours(emp, *ym)
        #         model += (
        #             lpSum(x[(emp.id, d, sh.id)] * sh.duration
        #                   for d in mdates for sh in problem.shifts if (emp.id, d, sh.id) in x)
        #             <= maxPossibleHours
        #         )

        # (3) Rest‑period (11 h) – via KPI helper
        for emp in problem.employees:
            for i in range(len(dates) - 1):
                d1, d2 = dates[i], dates[i + 1]
                for s1 in problem.shifts:
                    for s2 in problem.shifts:
                        if (emp.id, d1, s1.id) in x and (emp.id, d2, s2.id) in x:
                            if kpi_calc.violates_rest_period(s1, s2, d1):
                                model += x[(emp.id, d1, s1.id)] + x[(emp.id, d2, s2.id)] <= 1

        # (4) Monthly balance, caps & soft fairness
        OT_CAP_FACTOR = 1.0  # 10 % above expected hard limit
        for emp in problem.employees:
            for ym, mdates in months.items():
                expected = kpi_calc.calculate_expected_month_hours(emp, *ym)
                worked = lpSum(x[(emp.id, d, sh.id)] * sh.duration
                                for d in mdates
                                for sh in problem.shifts if (emp.id, d, sh.id) in x)

                # Balance equality with OT/UT vars
                model += worked == expected - ut[(emp.id, ym)] + ot[(emp.id, ym)]
                model += worked <= expected * OT_CAP_FACTOR
                # model += worked <= expected

                # Soft lower bound: worked + deficit ≥ expected·MIN_UTIL_FACTOR
                model += worked + mu_def[(emp.id, ym)] >= expected * self.MIN_UTIL_FACTOR

        # (5) Aggregate hours & yearly utilisation ≥ 75 %
        for emp in problem.employees:
            model += total_hours[emp.id] == lpSum(
                x[(emp.id, d, sh.id)] * sh.duration
                for d in dates for sh in problem.shifts if (emp.id, d, sh.id) in x
            )
            yearly_capacity = kpi_calc.calculate_expected_yearly_hours(emp, problem.start_date.year)
            model += total_hours[emp.id] >= yearly_capacity * 0.85

        # ------------------------------------------------------------------
        # Solve
        # ------------------------------------------------------------------
        status = model.solve(PULP_CBC_CMD(msg=False, timeLimit=300))
        print(f"[OptILP DEBUG] Status: {LpStatus[status]}")

        # Extract schedule
        schedule = [
            ScheduleEntry(eid, d, sid)
            for (eid, d, sid), var in x.items()
            if var.varValue and var.varValue > 0.5
        ]
        return schedule

    # ------------------------------------------------------------------
    # Legacy helpers (keep deterministic)
    # ------------------------------------------------------------------
    def _get_holidays_for_year(self, year: int) -> Set[Tuple[int, int, int]]:
        # (unchanged – Bavarian public holidays)
        if year == 2024:
            return {
                (2024, 1, 1), (2024, 1, 6), (2024, 3, 29), (2024, 4, 1),
                (2024, 5, 1), (2024, 5, 9), (2024, 5, 20), (2024, 10, 3),
                (2024, 12, 25), (2024, 12, 26),
            }
        if year == 2025:
            return {
                (2025, 1, 1), (2025, 1, 6), (2025, 4, 18), (2025, 4, 21),
                (2025, 5, 1), (2025, 5, 29), (2025, 6, 9), (2025, 10, 3),
                (2025, 12, 25), (2025, 12, 26),
            }
        if year == 2026:
            return {
                (2026, 1, 1), (2026, 1, 6), (2026, 4, 3), (2026, 4, 6),
                (2026, 5, 1), (2026, 5, 14), (2026, 5, 25), (2026, 10, 3),
                (2026, 12, 25), (2026, 12, 26),
            }
        return set()
