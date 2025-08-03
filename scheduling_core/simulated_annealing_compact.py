from __future__ import annotations


import math
import random
from collections import defaultdict
from datetime import timedelta, date
from typing import List, Dict, Tuple, Optional

from rostering_app.services.kpi_calculator import KPICalculator
from rostering_app.utils import get_working_days_in_range

from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry, Solution
from .utils import create_empty_solution, get_weeks


# ──────────────────────────────────────────────────────────────────────────────


class SimulatedAnnealingScheduler(SchedulingAlgorithm):
    """Space-efficient SA rostering algorithm with fairness."""

    # -------------------------------------------------------------------------
    def __init__(
            self,
            *,
            iterations: int = 2_000,
            init_temp: float = 800.0,
            final_temp: float = 1.0,
            monthly_allowance: int = 0,  # allowance disabled in v2.1
            sundays_off: bool = False,
            fairness_weight: int = 75_000,
    ) -> None:
        self.iterations = iterations
        self.init_temp = init_temp
        self.final_temp = final_temp
        self.monthly_allowance = monthly_allowance
        self.sundays_off = sundays_off
        self.fairness_weight = fairness_weight

    # public ------------------------------------------------------------------
    @property
    def name(self) -> str:  # noqa: D401 – short description
        return "Simulated Annealing (compact v2.1 fair)"

    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:  # noqa: C901
        self.p = problem
        self.kpi = KPICalculator(problem.company)

        # days & helpers -------------------------------------------------------
        self.days: List[date] = list(
            get_working_days_in_range(problem.start_date, problem.end_date, problem.company)
        )
        self.weeks = get_weeks(problem.start_date, problem.end_date)
        self.day_idx = {d: i for i, d in enumerate(self.days)}
        self.emp_index = {e.id: idx for idx, e in enumerate(problem.employees)}
        self.shift_index = {s.id: idx for idx, s in enumerate(problem.shifts)}
        self.shift_by_id = problem.shift_by_id

        # pre-compute possible hours for fairness -----------------------------
        self._compute_possible_hours()

        # greedy seed ----------------------------------------------------------
        sol = self._initial_solution()
        best = sol.copy()
        best.cost = self._evaluate(best)

        temp = self.init_temp
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

        self._greedy_fill(best)
        return best.to_entries()

    # ───────────────────────── helpers ──────────────────────────────────────
    # availability ------------------------------------------------------------
    def _compute_possible_hours(self) -> None:
        """Store `possible_hours[eid]` = hours employee *could* work."""
        self.possible_hours: Dict[int, int] = {e.id: 0 for e in self.p.employees}
        for d in self.days:
            for sh in self.p.shifts:
                for emp in self.p.employees:
                    if d not in emp.absence_dates:
                        self.possible_hours[emp.id] += sh.duration

    # initial greedy fill -----------------------------------------------------
    def _initial_solution(self) -> Solution:
        sol = create_empty_solution(self.p)
        weekly = defaultdict(lambda: defaultdict(int))  # emp_id -> week_key -> hrs

        for d in self.days:
            wk = d.isocalendar()[:2]
            for sh in self.p.shifts:
                key = (d, sh.id)
                # first fill to min_staff
                cand = self._available_emps(d, sh, sol, weekly, need=sh.min_staff)
                sol.assignments[key] = cand
                for eid in cand:
                    weekly[eid][wk] += sh.duration

        # second pass – fill up to max_staff
        for d in self.days:
            wk = d.isocalendar()[:2]
            for sh in self.p.shifts:
                key = (d, sh.id)
                while len(sol.assignments[key]) < sh.max_staff:
                    cand = self._available_emps(d, sh, sol, weekly)
                    if not cand:
                        break
                    chosen = random.choice(cand)
                    sol.assignments[key].append(chosen)
                    weekly[chosen][wk] += sh.duration
        return sol

    # candidate employees -----------------------------------------------------
    def _available_emps(
            self,
            day: date,
            shift,
            sol: Solution,
            weekly: Dict[int, Dict[Tuple[int, int], int]],
            *,
            need: Optional[int] = None,
    ) -> List[int]:
        wk_key = day.isocalendar()[:2]
        res: List[int] = []
        for emp in self.p.employees:
            if need is not None and len(res) >= need:
                break
            if day in emp.absence_dates:
                continue
            # already working a shift today?
            if any(emp.id in sol.assignments.get((day, s.id), []) for s in self.p.shifts):
                continue
            # weekly hours limit
            if (
                    emp.max_hours_per_week
                    and weekly[emp.id][wk_key] + shift.duration > emp.max_hours_per_week
            ):
                continue
            if self._rest_violation(emp.id, day, shift, sol):
                continue
            res.append(emp.id)
        return res

    # rest check --------------------------------------------------------------
    def _rest_violation(self, eid: int, day: date, shift, sol: Solution) -> bool:
        prev, nxt = day - timedelta(days=1), day + timedelta(days=1)
        for sh in self.p.shifts:
            if eid in sol.assignments.get((prev, sh.id), []) and self.kpi.violates_rest_period(
                    sh, shift, prev
            ):
                return True
            if eid in sol.assignments.get((nxt, sh.id), []) and self.kpi.violates_rest_period(
                    shift, sh, day
            ):
                return True
        return False

    # evaluation --------------------------------------------------------------
    def _evaluate(self, sol: Solution) -> float:  # lower is better
        pen, bonus = 0, 0
        weekly_hrs = defaultdict(lambda: defaultdict(int))
        worked_hrs = defaultdict(int)  # for fairness

        for (d, sid), emps in sol.assignments.items():
            sh = self.shift_by_id[sid]
            staff = len(emps)
            if staff < sh.min_staff:
                pen += (sh.min_staff - staff) * 5_000_000
            elif staff > sh.max_staff:
                pen += (staff - sh.max_staff) * 500_000
            else:
                bonus -= staff * 10_000  # encourage fully staffed shifts
            for eid in emps:
                weekly_hrs[eid][d.isocalendar()[:2]] += sh.duration
                worked_hrs[eid] += sh.duration

        # weekly hours penalty -------------------------------------------------
        for emp in self.p.employees:
            for wk, hrs in weekly_hrs[emp.id].items():
                if emp.max_hours_per_week and hrs > emp.max_hours_per_week:
                    pen += (hrs - emp.max_hours_per_week) * 2_000_000

        # rest period penalty --------------------------------------------------
        pen += self._rest_violations(sol) * 50_000_000

        # ─── fairness penalty (NEW) ──────────────────────────────────────────
        ratios = [
            worked_hrs[eid] / ph
            for eid, ph in self.possible_hours.items()
            if ph > 0
        ]
        fair_pen = 0
        if ratios:
            fair_pen = (max(ratios) - min(ratios)) * self.fairness_weight

        return pen + bonus + fair_pen

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

    # neighbour generation -----------------------------------------------------
    def _neighbor(self, sol: Solution) -> Solution:
        nb = sol.copy()
        day = random.choice(self.days)
        shift = random.choice(self.p.shifts)
        key = (day, shift.id)
        assigned = nb.assignments.get(key, [])
        if assigned and (random.random() < 0.5):  # remove one
            assigned.pop(random.randrange(len(assigned)))
        else:  # try to add
            wk_map = defaultdict(lambda: defaultdict(int))
            for (d, sid), emps in nb.assignments.items():
                s = self.shift_by_id[sid]
                for eid in emps:
                    wk_map[eid][d.isocalendar()[:2]] += s.duration
            cand = self._available_emps(day, shift, nb, wk_map)
            if cand:
                assigned.append(random.choice(cand))
        nb.assignments[key] = assigned
        return nb

    # SA helpers ---------------------------------------------------------------
    def _accept(self, curr: float, nxt: float, temp: float) -> bool:
        return nxt < curr or random.random() < math.exp((curr - nxt) / max(temp, 1e-9))

    def _cool(self, it: int) -> float:
        ratio = it / max(self.iterations - 1, 1)
        base = self.init_temp * (self.final_temp / self.init_temp) ** ratio
        # aggressive cooling mid-run
        if ratio < 0.3:
            return base
        elif ratio < 0.7:
            return base * 0.7
        return base * 0.3

    # final greedy fill to max_staff ------------------------------------------
    def _greedy_fill(self, sol: Solution) -> None:
        weekly = defaultdict(lambda: defaultdict(int))
        for (d, sid), emps in sol.assignments.items():
            hrs = self.shift_by_id[sid].duration
            for eid in emps:
                weekly[eid][d.isocalendar()[:2]] += hrs

        for d in self.days:
            wk = d.isocalendar()[:2]
            for sh in self.p.shifts:
                key = (d, sh.id)
                while len(sol.assignments[key]) < sh.max_staff:
                    cand = self._available_emps(d, sh, sol, weekly)
                    if not cand:
                        break
                    eid = random.choice(cand)
                    sol.assignments[key].append(eid)
                    weekly[eid][wk] += sh.duration
