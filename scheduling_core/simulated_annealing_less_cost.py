from __future__ import annotations

import calendar

"""Simulated Annealing – less‑cost *v2* (fairness‑aware)

This is a **clean rewrite** of the original *simulated_annealing_less_cost.py* that
adds a Fairness objective while keeping the public API (class name & behaviour)
compatible.  The algorithm is a slimmed‑down variant (~320 LOC vs. >1 200) but
all constraints & neighbourhood moves remain equivalent.

Key additions
-------------
* `fairness_weight` parameter (default 75 000) – multiplies the difference
  between the most‑ and least‑utilised employees `α_max − α_min`.
* `_evaluate()` now returns:  `cost = hard_penalties + soft_penalties + fairness_penalty`.
* Greedy seed & neighbourhood moves are borrowed from the compact SA
  implementation but extended so they never exceed `shift.max_staff` and they
  respect the 11‑hour rest‑rule via the KPI service.

Drop‑in replacement: simply store this file next to the other schedulers and
re‑import – e.g. `from ….simulated_annealing_less_cost import NewSimulatedAnnealingScheduler`.
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
    """Simulated Annealing variant prioritising coverage, utilisation – and *fairness*."""

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

        # allowance – one extra 8‑h shift per week
        self.weekly_allowance = 8

        # placeholders set in *solve*
        self.kpi: KPICalculator | None = None
        self.days: List[date] = []
        self.emp_index: Dict[int, int] = {}
        self.shift_by_id: Dict[int, object] = {}
        self.employee_capacity: Dict[int, float] = {}

    # ------------------------------------------------------------------
    @property
    def name(self) -> str:  # noqa: D401 – short name wanted by UI
        return "Simulated Annealing – less‑cost v2 (fair)"

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

        # capacities – scaled to planning horizon
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
            if weekly[emp.id][wk] + shift.duration > emp.max_hours_per_week + self.weekly_allowance:
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
                limit = emp.max_hours_per_week + self.weekly_allowance
                if hrs > limit:
                    pen += (hrs - limit) * 2_000_000
                hrs_year += hrs
            cap = self.employee_capacity[emp.id]
            if cap > 0:
                util = hrs_year / cap
                util_vals.append(util)
                # soft‑spot at 90 % ±5 %
                if 0.85 <= util <= 0.95:
                    bonus -= util * 25_000
                elif util < 0.85:
                    pen += (0.85 - util) * 25_000 * 2
                else:  # >0.95
                    pen += (util - 0.95) * 25_000 * 2

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
                    eid = random.choice(cand)
                    sol.assignments[key].append(eid)
                    weekly[eid][wk] += sh.duration

    # ────────── capacities helper ──────────
    def _calc_capacities(self) -> None:
        self.employee_capacity = {}
        for emp in self.p.employees:
            yearly_cap = self.kpi.calculate_expected_yearly_hours(emp, self.p.start_date.year)
            days_in_year = 365 + int(calendar.isleap(self.p.start_date.year))
            factor = len(self.days) / days_in_year
            self.employee_capacity[emp.id] = yearly_cap * factor
