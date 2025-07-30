from __future__ import annotations

"""Fast genetic algorithm for employee rostering (v2.2 – July 2025)
--------------------------------------------------------------------
**Bug‑fix release** — v2.1 assumed that employee IDs were contiguous
`0…N‑1` and used them directly as array indices, which breaks when the
real IDs are arbitrary integers (e.g. `16906`).

v2.2 introduces a simple mapping `emp_index[eid] → 0…N‑1` and applies it
consistently in *all* NumPy arrays (`absent`, `assign_mat`) and bitset
operations.  No other behaviour changes.
"""

import math
from datetime import timedelta
import random
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from numba import njit  # type: ignore

    def _njit(*args, **kwargs):  # noqa: WPS118
        return njit(*args, cache=True, fastmath=True, nopython=True, **kwargs)

    _NUMBA = True
except ImportError:  # pragma: no cover –­ numba optional

    def _njit(fn=None, **kwargs):  # type: ignore
        if fn is None:
            return lambda f: f
        return fn

    _NUMBA = False

from rostering_app.services.kpi_calculator import KPICalculator
from rostering_app.utils import get_working_days_in_range

from .base import ScheduleEntry, SchedulingAlgorithm, SchedulingProblem, Solution
from .utils import create_empty_solution, get_weeks

# ───────────────────────────── helpers ────────────────────────────────

def _build_numpy_templates(problem: SchedulingProblem):
    working_days = list(
        get_working_days_in_range(problem.start_date, problem.end_date, problem.company)
    )
    d_index = {d: i for i, d in enumerate(working_days)}
    s_index = {s.id: i for i, s in enumerate(problem.shifts)}

    min_staff = np.empty((len(working_days), len(problem.shifts)), dtype=np.int16)
    max_staff = np.empty_like(min_staff)
    for j, sh in enumerate(problem.shifts):
        min_staff[:, j] = sh.min_staff
        max_staff[:, j] = sh.max_staff
    return working_days, d_index, s_index, min_staff, max_staff


@_njit
def _rest_violations_numba(assign_mat: np.ndarray, rest_pairs: np.ndarray) -> int:
    v = 0
    D, S, E = assign_mat.shape
    for e in range(E):
        for d in range(D - 1):
            for idx in range(rest_pairs.shape[0]):
                s1, s2 = rest_pairs[idx]
                if assign_mat[d, s1, e] and assign_mat[d + 1, s2, e]:
                    v += 1
    return v


# ─────────────────────────── main class ───────────────────────────────

class GeneticAlgorithmScheduler(SchedulingAlgorithm):
    """Speed‑oriented GA with vectorised fitness & adaptive parameters."""

    @property
    def name(self) -> str:
        return "Genetic Algorithm (v2 fast)"

    def __init__(
        self,
        population_size: Optional[int] = None,
        max_generations: Optional[int] = None,
        time_limit: Optional[int] = None,
        mutation_rate: float = 0.12,
        crossover_rate: float = 0.85,
        elite_frac: float = 0.10,
        patience: int = 25,
        sundays_off: bool = False,
        **_legacy,
    ) -> None:
        self.user_population_size = population_size
        self.user_max_generations = max_generations
        self.user_time_limit = time_limit
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elite_frac = elite_frac
        self.patience = patience
        self.sunday_policy = sundays_off
        # Allowable weekly overtime (in hours) before counting as a violation
        self.weekly_allowance = 8

    # ───────────────────────── solve ────────────────────────────────
    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:  # noqa: C901
        self.problem = problem
        self.kpi = KPICalculator(problem.company)

        (
            self.working_days,
            self.day_index,
            self.shift_index,
            self.min_staff,
            self.max_staff,
        ) = _build_numpy_templates(problem)
        self.total_days = len(self.working_days)

        # employee‑id → row index mapping (bug‑fix)
        self.emp_index = {emp.id: idx for idx, emp in enumerate(problem.employees)}

        # adaptive params
        size_metric = len(problem.employees) * self.total_days
        pop_size = self.user_population_size or max(10, int(math.sqrt(size_metric)))
        max_gens = self.user_max_generations or max(60, int(size_metric ** 0.33) * 4)
        time_limit = self.user_time_limit or max(8, int(size_metric ** 0.25))
        elite_size = max(2, int(pop_size * self.elite_frac))

        self._build_absence_bitset()

        population: List[Tuple[Solution, float]] = []
        for _ in range(pop_size):
            sol = self._create_greedy() if random.random() < 0.6 else self._create_random()
            population.append((sol, self._evaluate(sol)))
        population.sort(key=lambda t: t[1])

        best_sol, best_cost = population[0]
        gens_no_improve, gen = 0, 0
        t0 = time.time()

        while gen < max_gens and (time.time() - t0) < time_limit and gens_no_improve < self.patience:
            gen += 1
            children: List[Tuple[Solution, float]] = []
            for _ in range(elite_size):
                p1, p2 = self._tournament(population), self._tournament(population)
                kid = self._crossover(p1, p2) if random.random() < self.crossover_rate else p1.copy()
                if random.random() < self.mutation_rate:
                    self._mutate(kid)
                children.append((kid, self._evaluate(kid)))
            population += children
            population.sort(key=lambda t: t[1])
            population = population[:pop_size]
            if population[0][1] < best_cost * 0.975:
                best_sol, best_cost = population[0]
                gens_no_improve = 0
            else:
                gens_no_improve += 1

        self._fill_understaffed(best_sol)
        # Optionally fill remaining capacity to maximize employee utilization.
        self._fill_to_capacity(best_sol)
        # Final clean-up: eliminate any remaining rest-period violations.
        self._resolve_rest_conflicts(best_sol)
        # Ensure staffing constraints after clean-up
        self._fill_understaffed(best_sol)
        return best_sol.to_entries()

    # ─────────────────── helpers: calendars & constructors ─────────────
    def _build_absence_bitset(self) -> None:
        E = len(self.problem.employees)
        self.absent = np.zeros((E, self.total_days), dtype=np.bool_)
        for emp in self.problem.employees:
            eidx = self.emp_index[emp.id]
            for d in emp.absence_dates:
                if d in self.day_index:
                    self.absent[eidx, self.day_index[d]] = True

    def _create_random(self) -> Solution:
        sol = create_empty_solution(self.problem)
        for d in self.working_days:
            d_idx = self.day_index[d]
            for sh in self.problem.shifts:
                need = sh.min_staff
                if need == 0:
                    continue
                avail = [emp.id for emp in self.problem.employees if not self.absent[self.emp_index[emp.id], d_idx]]
                sol.assignments[(d, sh.id)] = random.sample(avail, min(need, len(avail)))
        return sol

    def _create_greedy(self) -> Solution:
        sol = create_empty_solution(self.problem)
        week_hours = defaultdict(lambda: defaultdict(int))
        for d in self.working_days:
            wk = d.isocalendar()[:2]
            d_idx = self.day_index[d]
            for sh in sorted(self.problem.shifts, key=lambda s: s.min_staff, reverse=True):
                key = (d, sh.id)
                while len(sol.assignments.get(key, [])) < sh.min_staff:
                    cand = [
                        emp.id
                        for emp in self.problem.employees
                        if not self.absent[self.emp_index[emp.id], d_idx]
                        and emp.id not in sol.assignments.get(key, [])
                        and week_hours[emp.id][wk] + sh.duration <= emp.max_hours_per_week + self.weekly_allowance
                    ]
                    if not cand:
                        break
                    chosen = min(cand, key=lambda eid: week_hours[eid][wk])
                    sol.assignments.setdefault(key, []).append(chosen)
                    week_hours[chosen][wk] += sh.duration
        return sol

    # ─────────────────────── GA operators ────────────────────────────
    def _tournament(self, pop: List[Tuple[Solution, float]], k: int = 3) -> Solution:
        return min(random.sample(pop, k), key=lambda t: t[1])[0]

    def _crossover(self, p1: Solution, p2: Solution) -> Solution:
        child = create_empty_solution(self.problem)
        coin = random.getrandbits
        for key in p1.assignments.keys():
            child.assignments[key] = list(p1.assignments[key] if coin(1) else p2.assignments[key])
        return child

    def _mutate(self, sol: Solution) -> None:
        # Choose a random (day, shift) key that belongs to the set of working
        # days; otherwise operations that rely on `self.day_index` will crash.
        valid_keys = [k for k in sol.assignments.keys() if k[0] in self.day_index]
        if not valid_keys:
            return  # Should not happen, but safety first
        key = random.choice(valid_keys)
        day, sh_id = key
        sh = self.problem.shift_by_id[sh_id]
        d_idx = self.day_index[day]
        lst = sol.assignments[key]
        if lst and random.random() < 0.5:
            lst.pop(random.randrange(len(lst)))
        elif len(lst) < sh.max_staff:
            cand = [e.id for e in self.problem.employees if not self.absent[self.emp_index[e.id], d_idx] and e.id not in lst]
            if cand:
                lst.append(random.choice(cand))
        sol.assignments[key] = lst

    # ─────────────────────── fitness ────────────────────────────────
    def _evaluate(self, sol: Solution) -> float:  # noqa: C901
        D, S = self.min_staff.shape
        coverage = np.zeros((D, S), dtype=np.int16)
        for (day, sh_id), emp_ids in sol.assignments.items():
            # Skip non-working days (e.g. public holidays) that are not part of
            # the day_index generated from `get_working_days_in_range`.  These
            # entries exist because `create_empty_solution` initialises every
            # calendar day between the start and end dates, but the GA only
            # cares about company working days.
            if day not in self.day_index:
                continue
            coverage[self.day_index[day], self.shift_index[sh_id]] = len(emp_ids)

        diff_under = (self.min_staff - coverage).clip(min=0).sum()
        diff_over = (coverage - self.max_staff).clip(min=0).sum()
        cov_pen = diff_under * 5_000_000 + diff_over * 500_000
        if cov_pen > getattr(self, "_best", float("inf")) * 1.25:
            return cov_pen

        E = len(self.problem.employees)
        assign_mat = np.zeros((D, S, E), dtype=np.bool_)
        for (day, sh_id), emp_ids in sol.assignments.items():
            if day not in self.day_index:
                continue
            di, si = self.day_index[day], self.shift_index[sh_id]
            for eid in emp_ids:
                assign_mat[di, si, self.emp_index[eid]] = True

        rest_pairs = self._rest_pairs()
        rest_pen = (
            _rest_violations_numba(assign_mat, rest_pairs) if _NUMBA else self._rest_py(assign_mat, rest_pairs)
        ) * 50_000_000

        week_pen = self._weekly_pen(assign_mat) * 2_000_000
        cost = cov_pen + rest_pen + week_pen
        self._best = min(getattr(self, "_best", float("inf")), cost)
        return cost

    def _rest_pairs(self):
        if hasattr(self, "_rest_cache"):
            return self._rest_cache
        pairs = [
            (i, j)
            for i, sh1 in enumerate(self.problem.shifts)
            for j, sh2 in enumerate(self.problem.shifts)
            if self.kpi.violates_rest_period(sh1, sh2, self.working_days[0])
        ]
        self._rest_cache = np.array(pairs, dtype=np.int16)
        return self._rest_cache

    def _rest_py(self, assign_mat, pairs) -> int:  # noqa: WPS110
        v, D, _, E = 0, *assign_mat.shape[:2], assign_mat.shape[2]
        for e in range(E):
            for d in range(D - 1):
                for s1, s2 in pairs:
                    if assign_mat[d, s1, e] and assign_mat[d + 1, s2, e]:
                        v += 1
        return v

    def _weekly_pen(self, assign_mat: np.ndarray) -> int:
        shift_hours = np.array([s.duration for s in self.problem.shifts])
        week_pen = 0
        for idx, emp in enumerate(self.problem.employees):
            if emp.max_hours_per_week == 0:
                continue
            daily_hours = assign_mat[:, :, idx] @ shift_hours
            # Group days by ISO week and sum the assigned hours per employee.
            for week_days in get_weeks(self.problem.start_date, self.problem.end_date).values():
                idxs = [self.day_index[d] for d in week_days if d in self.day_index]
                if not idxs:
                    continue
                tot = daily_hours[idxs].sum()
                limit = emp.max_hours_per_week + self.weekly_allowance
                if tot > limit:
                    week_pen += int(tot - limit)
        return week_pen

    # ─────────────────────── post‑processing ─────────────────────────
    def _fill_understaffed(self, sol: Solution) -> None:
        for d in self.working_days:
            d_idx = self.day_index[d]
            for sh in self.problem.shifts:
                key = (d, sh.id)
                while len(sol.assignments.get(key, [])) < sh.min_staff:
                    free = [e.id for e in self.problem.employees if not self.absent[self.emp_index[e.id], d_idx]]
                    if not free:
                        break
                    sol.assignments.setdefault(key, []).append(random.choice(free))

    def _resolve_rest_conflicts(self, sol: Solution) -> None:
        """Detect & fix any remaining rest violations by reassigning or dropping."""
        for idx in range(1, len(self.working_days)):
            prev_day = self.working_days[idx - 1]
            curr_day = self.working_days[idx]
            for sh_prev in self.problem.shifts:
                if not sol.assignments.get((prev_day, sh_prev.id)):
                    continue
                for sh_curr in self.problem.shifts:
                    key_curr = (curr_day, sh_curr.id)
                    lst_curr = sol.assignments.get(key_curr, [])
                    if not lst_curr:
                        continue
                    conflicted = []
                    for eid in lst_curr:
                        if eid in sol.assignments.get((prev_day, sh_prev.id), []):
                            if self.kpi.violates_rest_period(sh_prev, sh_curr, prev_day):
                                conflicted.append(eid)
                    for eid in conflicted:
                        lst_curr.remove(eid)
                        # try find replacement respecting all constraints
                        d_idx = self.day_index[curr_day]
                        wk = curr_day.isocalendar()[:2]
                        for cand in self.problem.employees:
                            cid = cand.id
                            if cid in lst_curr or cid in sol.assignments.get((prev_day, sh_prev.id), []):
                                continue
                            if self.absent[self.emp_index[cid], d_idx]:
                                continue
                            # weekly hours limit
                            # quick estimate: assume 0 additional hours; skip if would exceed
                            if cand.max_hours_per_week and cand.max_hours_per_week < sh_curr.duration:
                                continue
                            # rest with previous day
                            rest_ok = True
                            for ps in self.problem.shifts:
                                if cid in sol.assignments.get((prev_day, ps.id), []):
                                    if self.kpi.violates_rest_period(ps, sh_curr, prev_day):
                                        rest_ok = False
                                        break
                            if not rest_ok:
                                continue
                            # rest with next day
                            next_day = self.working_days[idx + 1] if idx + 1 < len(self.working_days) else None
                            if next_day:
                                for ns in self.problem.shifts:
                                    if cid in sol.assignments.get((next_day, ns.id), []):
                                        if self.kpi.violates_rest_period(sh_curr, ns, curr_day):
                                            rest_ok = False
                                            break
                            if not rest_ok:
                                continue
                            lst_curr.append(cid)
                            break
                    sol.assignments[key_curr] = lst_curr

    def _fill_to_capacity(self, sol: Solution) -> None:
        """Greedily fill shifts up to their max_staff to maximise utilisation."""
        # Track hours already assigned per employee per ISO week
        week_hours = defaultdict(lambda: defaultdict(int))  # emp_id -> (year, week) -> hours

        # Pre-populate with existing assignments
        for (day, sh_id), emp_ids in sol.assignments.items():
            wk = day.isocalendar()[:2]
            shift_hours = self.problem.shift_by_id[sh_id].duration
            for eid in emp_ids:
                week_hours[eid][wk] += shift_hours

        for d in self.working_days:
            d_idx = self.day_index[d]
            wk = d.isocalendar()[:2]
            for sh in self.problem.shifts:
                key = (d, sh.id)
                while len(sol.assignments.get(key, [])) < sh.max_staff:
                    # find candidate employees available & under weekly limit & not already assigned same day/shift
                    cand = []
                    for emp in self.problem.employees:
                        eid = emp.id
                        if self.absent[self.emp_index[eid], d_idx]:
                            continue
                        if eid in sol.assignments.get(key, []):
                            continue
                        if emp.max_hours_per_week and (week_hours[eid][wk] + sh.duration) > emp.max_hours_per_week + self.weekly_allowance:
                            continue
                        # Rest-period check with previous and next day
                        rest_ok = True
                        prev_day = d - timedelta(days=1)
                        next_day = d + timedelta(days=1)
                        # Check previous day assignments
                        for prev_sh_id in [sid for sid in self.shift_index.keys()]:
                            if eid in sol.assignments.get((prev_day, prev_sh_id), []):
                                prev_sh = self.problem.shift_by_id[prev_sh_id]
                                if self.kpi.violates_rest_period(prev_sh, sh, prev_day):
                                    rest_ok = False
                                    break
                        if not rest_ok:
                            continue
                        # Check next day assignments
                        for next_sh_id in [sid for sid in self.shift_index.keys()]:
                            if eid in sol.assignments.get((next_day, next_sh_id), []):
                                next_sh = self.problem.shift_by_id[next_sh_id]
                                if self.kpi.violates_rest_period(sh, next_sh, d):
                                    rest_ok = False
                                    break
                        if not rest_ok:
                            continue
                        cand.append(eid)
                    if not cand:
                        break
                    chosen = min(cand, key=lambda eid: week_hours[eid][wk])
                    sol.assignments.setdefault(key, []).append(chosen)
                    week_hours[chosen][wk] += sh.duration
