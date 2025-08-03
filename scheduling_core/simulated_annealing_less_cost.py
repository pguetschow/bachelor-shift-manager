from __future__ import annotations

import calendar

"""Simulated Annealing – less‑cost *v2.1* (fairness‑aware + fixed overutilization)

This is a **fixed version** of the NewSimulatedAnnealingScheduler that addresses
overutilization issues, particularly for 32h contracts.

Key fixes in v2.1
-----------------
* **Removed weekly_allowance** - was causing systematic overutilization
* **Improved utilization incentives** - better balanced soft-spot around target hours
* **Enhanced capacity calculation** - more accurate scaling for planning horizon
* **Stricter weekly constraints** - no longer allows systematic overtime
* **Better fairness calculation** - uses actual contract hours as baseline

The algorithm now respects contract hours more strictly while maintaining fairness.
"""

import math
import random
from collections import defaultdict
from datetime import timedelta, date
from enum import Enum
from typing import List, Dict, Tuple

from rostering_app.services.kpi_calculator import KPICalculator
from rostering_app.utils import get_working_days_in_range

from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry, Solution
from .utils import create_empty_solution, get_weeks


# ────────────────────────────── helpers ────────────────────────────────
class CoolingSchedule(Enum):
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    LOGARITHMIC = "logarithmic"


def _week_key(d: date) -> Tuple[int, int]:
    """Year‑week tuple used as dictionary key."""
    return d.isocalendar()[:2]


# ───────────────────────── main scheduler ──────────────────────────────
class NewSimulatedAnnealingScheduler(SchedulingAlgorithm):
    """Simulated Annealing variant prioritising coverage, utilisation – and *fairness*."""

    # ------------------------------------------------------------------
    def __init__(
            self,
            *,
            initial_temp: float = 800.0,
            final_temp: float = 1.0,
            iterations: int = 2_000,
            cooling_schedule: CoolingSchedule = CoolingSchedule.EXPONENTIAL,
            sundays_off: bool = False,
            fairness_weight: int = 75_000,
    ) -> None:
        self.initial_temp = initial_temp
        self.final_temp = final_temp
        self.iterations = iterations
        self.cooling_schedule = cooling_schedule
        self.sundays_off = sundays_off
        self.fairness_weight = fairness_weight

        # REMOVED: weekly_allowance (was causing overutilization)
        # self.weekly_allowance = 8

        # placeholders set in *solve*
        self.kpi: KPICalculator | None = None
        self.days: List[date] = []
        self.emp_index: Dict[int, int] = {}
        self.shift_by_id: Dict[int, object] = {}
        self.employee_capacity: Dict[int, float] = {}

    # ------------------------------------------------------------------
    @property
    def name(self) -> str:  # noqa: D401 – short name wanted by UI
        return "Simulated Annealing – less‑cost v2.1 (fair, fixed)"

    # ────────── public entry point ──────────
    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:  # noqa: C901
        self.p = problem
        self.kpi = KPICalculator(problem.company)
        self.days = list(
            get_working_days_in_range(problem.start_date, problem.end_date, problem.company)
        )
        self.weeks = get_weeks(problem.start_date, problem.end_date)
        self.emp_index = {e.id: i for i, e in enumerate(problem.employees)}
        self.shift_by_id = problem.shift_by_id

        # capacities – scaled to planning horizon
        self._calc_capacities()

        # greedy seed
        sol = self._initial_solution()
        best = sol.copy()
        best.cost = self._evaluate(best)

        temp = self.initial_temp
        for it in range(self.iterations):
            neigh = self._neighbor(sol)
            neigh.cost = self._evaluate(neigh)
            if self._accept(sol.cost, neigh.cost, temp):
                sol = neigh
            if neigh.cost < best.cost:
                best = neigh.copy()
            temp = self._cool(it)
            if temp < self.final_temp:
                break

        # final greedy fill to hit *max_staff* where feasible
        self._greedy_fill(best)
        return best.to_entries()

    # ────────── initial greedy seed ──────────
    def _initial_solution(self) -> Solution:
        sol = create_empty_solution(self.p)
        weekly = defaultdict(lambda: defaultdict(int))  # emp‑id → week → hours

        for d in self.days:  # first pass – satisfy *min_staff*
            wk = _week_key(d)
            for sh in self.p.shifts:
                key = (d, sh.id)
                cand = self._available(d, sh, sol, weekly, need=sh.min_staff)
                sol.assignments[key] = cand
                for eid in cand:
                    weekly[eid][wk] += sh.duration

        for d in self.days:  # second pass – fill up to *max_staff*
            wk = _week_key(d)
            for sh in self.p.shifts:
                key = (d, sh.id)
                while len(sol.assignments[key]) < sh.max_staff:
                    cand = self._available(d, sh, sol, weekly)
                    if not cand:
                        break
                    eid = random.choice(cand)
                    sol.assignments[key].append(eid)
                    weekly[eid][wk] += sh.duration
        return sol

    # ────────── neighbour generation ──────────
    def _neighbor(self, sol: Solution) -> Solution:
        nb = sol.copy()
        day = random.choice(self.days)
        sh = random.choice(self.p.shifts)
        key = (day, sh.id)
        assigned = nb.assignments.get(key, [])
        if assigned and (random.random() < 0.5):  # remove one
            assigned.pop(random.randrange(len(assigned)))
        else:  # try add
            weekly = defaultdict(lambda: defaultdict(int))
            for (d, sid), emps in nb.assignments.items():
                dur = self.shift_by_id[sid].duration
                for eid in emps:
                    weekly[eid][_week_key(d)] += dur
            cand = self._available(day, sh, nb, weekly)
            if cand:
                assigned.append(random.choice(cand))
        nb.assignments[key] = assigned
        return nb

    # ────────── candidate employees helper ──────────
    def _available(
            self,
            day: date,
            shift,
            sol: Solution,
            weekly: Dict[int, Dict[Tuple[int, int], int]],
            *,
            need: int | None = None,
    ) -> List[int]:
        wk = _week_key(day)
        res: List[int] = []
        for emp in self.p.employees:
            if need is not None and len(res) >= need:
                break
            if day in emp.absence_dates:
                continue
            if any(emp.id in sol.assignments.get((day, s.id), []) for s in self.p.shifts):
                continue
            # FIXED: Removed weekly_allowance - strict adherence to contract hours
            if emp.max_hours_per_week and weekly[emp.id][wk] + shift.duration > emp.max_hours_per_week:
                continue
            if self._rest_violation(emp.id, day, shift, sol):
                continue
            res.append(emp.id)
        return res

    def _rest_violation(self, eid: int, day: date, shift, sol: Solution) -> bool:
        prev, nxt = day - timedelta(days=1), day + timedelta(days=1)
        for sh in self.p.shifts:
            if eid in sol.assignments.get((prev, sh.id), []) and self.kpi.violates_rest_period(sh, shift, prev):
                return True
            if eid in sol.assignments.get((nxt, sh.id), []) and self.kpi.violates_rest_period(shift, sh, day):
                return True
        return False

    # ────────── evaluation ──────────
    def _evaluate(self, sol: Solution) -> float:  # lower is better
        pen, bonus = 0, 0
        util_vals: List[float] = []
        weekly_hrs = defaultdict(lambda: defaultdict(int))

        for (d, sid), emps in sol.assignments.items():
            sh = self.shift_by_id[sid]
            staff = len(emps)
            if staff < sh.min_staff:
                pen += (sh.min_staff - staff) * 5_000_000
            elif staff > sh.max_staff:
                pen += (staff - sh.max_staff) * 500_000
            else:
                bonus -= staff * 10_000  # reward filled spots
            for eid in emps:
                weekly_hrs[eid][_week_key(d)] += sh.duration

        # weekly hours limit & utilisation -------------------------------
        for emp in self.p.employees:
            hrs_year = 0
            for wk, hrs in weekly_hrs[emp.id].items():
                # FIXED: Strict weekly limit - no allowance
                if emp.max_hours_per_week and hrs > emp.max_hours_per_week:
                    pen += (hrs - emp.max_hours_per_week) * 3_000_000  # Higher penalty
                hrs_year += hrs

            cap = self.employee_capacity[emp.id]
            if cap > 0:
                util = hrs_year / cap
                util_vals.append(util)
                # FIXED: Better balanced utilization incentives
                # Target range: 90% ± 10% (80%-100%)
                if 0.80 <= util <= 1.00:
                    # Reward being in target range, with peak reward at 90%
                    reward_factor = 1.0 - abs(util - 0.90) / 0.20
                    bonus -= reward_factor * 30_000
                elif util < 0.80:
                    # Penalize underutilization
                    pen += (0.80 - util) * 40_000
                else:  # util > 1.00
                    # Strong penalty for overutilization
                    pen += (util - 1.00) * 60_000

        # rest period violations ----------------------------------------
        pen += self._rest_violations(sol) * 50_000_000

        # fairness penalty ---------------------------------------------
        fair_pen = 0
        if util_vals:
            fair_pen = (max(util_vals) - min(util_vals)) * self.fairness_weight

        return pen + fair_pen + bonus

    def _rest_violations(self, sol: Solution) -> int:
        v = 0
        for idx in range(len(self.days) - 1):
            d1, d2 = self.days[idx], self.days[idx + 1]
            for eid in self.emp_index.keys():
                sh1 = sh2 = None
                for s in self.p.shifts:
                    if eid in sol.assignments.get((d1, s.id), []):
                        sh1 = s
                    if eid in sol.assignments.get((d2, s.id), []):
                        sh2 = s
                if sh1 and sh2 and self.kpi.violates_rest_period(sh1, sh2, d1):
                    v += 1
        return v

    # ────────── SA helpers ──────────
    def _accept(self, curr: float, nxt: float, temp: float) -> bool:
        return nxt < curr or random.random() < math.exp((curr - nxt) / max(temp, 1e-9))

    def _cool(self, it: int) -> float:
        ratio = it / max(self.iterations - 1, 1)
        if self.cooling_schedule == CoolingSchedule.LINEAR:
            return self.initial_temp - (self.initial_temp - self.final_temp) * ratio
        if self.cooling_schedule == CoolingSchedule.LOGARITHMIC:
            return self.initial_temp / (1 + 5 * ratio)
        # exponential (default)
        return self.initial_temp * (self.final_temp / self.initial_temp) ** ratio

    # ────────── greedy post‑processing ──────────
    def _greedy_fill(self, sol: Solution) -> None:
        weekly = defaultdict(lambda: defaultdict(int))
        for (d, sid), emps in sol.assignments.items():
            dur = self.shift_by_id[sid].duration
            for eid in emps:
                weekly[eid][_week_key(d)] += dur

        for d in self.days:
            wk = _week_key(d)
            for sh in self.p.shifts:
                key = (d, sh.id)
                while len(sol.assignments[key]) < sh.max_staff:
                    cand = self._available(d, sh, sol, weekly)
                    if not cand:
                        break
                    # FIXED: Prefer employees with lower utilization to avoid overutilization
                    eid = min(cand, key=lambda e: weekly[e][wk])
                    sol.assignments[key].append(eid)
                    weekly[eid][wk] += sh.duration

    # ────────── capacities helper ──────────
    def _calc_capacities(self) -> None:
        """Calculate expected working hours for each employee in the planning period."""
        self.employee_capacity = {}
        for emp in self.p.employees:
            # Calculate working days available for this employee
            available_days = 0
            for day in self.days:
                if day not in emp.absence_dates:
                    available_days += 1

            # Estimate hours based on contract and availability
            if emp.max_hours_per_week and emp.max_hours_per_week > 0:
                # Use contract hours as baseline
                weeks_in_period = len(self.days) / 7.0
                contract_hours = emp.max_hours_per_week * weeks_in_period

                # Adjust for actual availability
                total_possible_days = len(self.days)
                availability_factor = available_days / total_possible_days if total_possible_days > 0 else 1.0

                self.employee_capacity[emp.id] = contract_hours * availability_factor
            else:
                # Fallback to KPI calculator if no contract hours
                yearly_cap = self.kpi.calculate_expected_yearly_hours(emp, self.p.start_date.year)
                days_in_year = 365 + int(calendar.isleap(self.p.start_date.year))
                factor = len(self.days) / days_in_year
                self.employee_capacity[emp.id] = yearly_cap * factor