from __future__ import annotations

from enum import Enum

"""Compact Simulated Annealing scheduler (v3.0 – Aug 2025)
──────────────────────────────────────────────────────────
A **Markov‑chain friendly** rewrite of the v2.1 compact SA.  The algorithm
is still ~350 LOC but now features *four* distinct neighbourhood operators
so the state‑space is explored more richly:

1. **Add/Remove** – previous single‑shift tweak (legacy).
2. **Swap‑Emp**   – swap two employees assigned to (possibly different)
   shifts.
3. **Move‑Emp**   – move an employee from shift A→ B (can span days).
4. **Swap‑Shift‑Block** – swap entire employee lists of two shifts.

`_neighbor()` now samples one of these moves according to `self.move_probs`;
users can override the distribution via constructor.  All fairness and
coverage constraints from v2.1 are kept.
"""

import math
import random
from collections import defaultdict
from datetime import timedelta, date
from typing import List, Dict, Tuple, Optional

from rostering_app.services.kpi_calculator import KPICalculator
from rostering_app.utils import get_working_days_in_range

from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry, Solution
from .utils import create_empty_solution, get_weeks


class CoolingSchedule(Enum):
    """Types of cooling schedules."""
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    LOGARITHMIC = "logarithmic"


class SimulatedAnnealingScheduler(SchedulingAlgorithm):
    """Space‑efficient SA with multi‑move neighbourhoods and fairness."""

    # ------------------------------------------------------------------
    def __init__(
            self,
            *,
            sundays_off: bool = False,
            iterations: int = 2_500,
            init_temp: float = 900.0,
            final_temp: float = 1.0,
            fairness_weight: int = 250_000,
            move_probs: Optional[Dict[str, float]] = None,
    ) -> None:
        """Parameters
        ----------------
        iterations        – max iterations (Markov chain length)
        init_temp/final   – SA temperature schedule bounds
        fairness_weight   – penalty multiplier for α_max−α_min
        move_probs        – dict mapping move names to probabilities;
                            keys: add_remove, swap_emp, move_emp, swap_block
        """
        self.iterations = iterations
        self.init_temp = init_temp
        self.final_temp = final_temp
        self.fairness_weight = fairness_weight
        default = {
            "add_remove": 0.45,
            "swap_emp": 0.25,
            "move_emp": 0.20,
            "swap_block": 0.10,
        }
        self.move_probs = default if move_probs is None else move_probs
        # normalise
        tot = sum(self.move_probs.values())
        for k in list(self.move_probs.keys()):
            self.move_probs[k] /= tot

    @property
    def name(self) -> str:
        return "Simulated Annealing (compact v3 – fair, Markov)"

    # ------------------------- public API -----------------------------
    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:  # noqa: C901
        self.p = problem
        self.kpi = KPICalculator(problem.company)

        # global helpers ------------------------------------------------
        self.days: List[date] = list(
            get_working_days_in_range(problem.start_date, problem.end_date, problem.company)
        )
        self.day_idx = {d: i for i, d in enumerate(self.days)}
        self.emp_index = {e.id: idx for idx, e in enumerate(problem.employees)}
        self.shift_index = {s.id: idx for idx, s in enumerate(problem.shifts)}
        self.shift_by_id = problem.shift_by_id
        self.weeks = get_weeks(problem.start_date, problem.end_date)

        self._compute_possible_hours()

        sol = self._initial_solution()
        sol.cost = self._evaluate(sol)
        best = sol.copy()

        temp = self.init_temp
        for it in range(self.iterations):
            nb = self._neighbor(sol)
            nb.cost = self._evaluate(nb)
            if self._accept(sol.cost, nb.cost, temp):
                sol = nb
            if nb.cost < best.cost:
                best = nb.copy()
            temp = self._cool(it)
            if temp < self.final_temp:
                break

        self._greedy_fill(best)
        return best.to_entries()

    # ---------------------- availability & helpers --------------------
    def _compute_possible_hours(self) -> None:
        self.possible_hours: Dict[int, int] = {e.id: 0 for e in self.p.employees}
        for d in self.days:
            for sh in self.p.shifts:
                for emp in self.p.employees:
                    if d not in emp.absence_dates:
                        self.possible_hours[emp.id] += sh.duration

    def _initial_solution(self) -> Solution:
        sol = create_empty_solution(self.p)
        weekly = defaultdict(lambda: defaultdict(int))
        for d in self.days:
            wk_key = d.isocalendar()[:2]
            for sh in self.p.shifts:
                key = (d, sh.id)
                cand = self._available_emps(d, sh, sol, weekly, need=sh.min_staff)
                sol.assignments[key] = cand
                for eid in cand:
                    weekly[eid][wk_key] += sh.duration
        return sol

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
            if any(emp.id in sol.assignments.get((day, s.id), []) for s in self.p.shifts):
                continue
            if emp.max_hours_per_week and weekly[emp.id][wk_key] + shift.duration > emp.max_hours_per_week:
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

    # ───────────────────────── evaluation & helpers ─────────────────────────
    def _evaluate(self, sol: Solution) -> float:
        pen, bonus = 0, 0
        weekly_hrs = defaultdict(lambda: defaultdict(int))
        worked_hrs = defaultdict(int)

        # coverage & bonuses --------------------------------------------------
        for (d, sid), emps in sol.assignments.items():
            sh = self.shift_by_id[sid]
            staff = len(emps)
            if staff < sh.min_staff:
                pen += (sh.min_staff - staff) * 5_000_000
            elif staff > sh.max_staff:
                pen += (staff - sh.max_staff) * 500_000
            else:
                bonus -= staff * 10_000
                if staff == sh.max_staff:
                    bonus -= 5_000
            for eid in emps:
                weekly_hrs[eid][d.isocalendar()[:2]] += sh.duration
                worked_hrs[eid] += sh.duration

        # weekly limits -------------------------------------------------------
        for emp in self.p.employees:
            for wk, hrs in weekly_hrs[emp.id].items():
                if emp.max_hours_per_week and hrs > emp.max_hours_per_week:
                    pen += (hrs - emp.max_hours_per_week) * 2_000_000

        # rest periods --------------------------------------------------------
        pen += self._rest_violations(sol) * 50_000_000

        # fairness penalty (quadratic) ---------------------------------------
        ratios = [worked_hrs[eid] / ph for eid, ph in self.possible_hours.items() if ph]
        fair_pen = 0
        if ratios:
            gap = max(ratios) - min(ratios)
            fair_pen = (gap ** 2) * self.fairness_weight * 4
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

    # ------------------ Markov‑chain neighbourhoods -------------------
    def _neighbor(self, sol: Solution) -> Solution:
        move = random.choices(
            population=list(self.move_probs.keys()),
            weights=list(self.move_probs.values()),
            k=1,
        )[0]
        if move == "add_remove":
            return self._nb_add_remove(sol)
        if move == "swap_emp":
            return self._nb_swap_emp(sol)
        if move == "move_emp":
            return self._nb_move_emp(sol)
        if move == "swap_block":
            return self._nb_swap_block(sol)
        return sol.copy()

    # ---- 1. Add/Remove ------------------------------------------------
    def _nb_add_remove(self, sol: Solution) -> Solution:
        nb = sol.copy()
        day = random.choice(self.days)
        shift = random.choice(self.p.shifts)
        key = (day, shift.id)
        assigned = nb.assignments.get(key, [])
        if assigned and random.random() < 0.5:
            assigned.pop(random.randrange(len(assigned)))
        else:
            wk_map = defaultdict(lambda: defaultdict(int))
            for (d, sid), emps in nb.assignments.items():
                hrs = self.shift_by_id[sid].duration
                for eid in emps:
                    wk_map[eid][d.isocalendar()[:2]] += hrs
            cand = self._available_emps(day, shift, nb, wk_map)
            if cand:
                assigned.append(random.choice(cand))
        nb.assignments[key] = assigned
        return nb

    # ---- 2. Swap two employees ---------------------------------------
    def _nb_swap_emp(self, sol: Solution) -> Solution:
        nb = sol.copy()
        # pick two random shift instances with at least one employee each
        filled = [(k, emps) for k, emps in nb.assignments.items() if emps]
        if len(filled) < 2:
            return nb
        (k1, emps1), (k2, emps2) = random.sample(filled, 2)
        e1 = random.choice(emps1)
        e2 = random.choice(emps2)
        # check feasibility: swapping shouldn't break rest/absence
        day1, sh1 = k1
        day2, sh2 = k2
        shift1 = self.shift_by_id[sh1]
        shift2 = self.shift_by_id[sh2]
        feasible = True
        for eid, day, shift in [(e1, day2, shift2), (e2, day1, shift1)]:
            if day in self.p.emp_by_id[eid].absence_dates:
                feasible = False
                break
            if self._rest_violation(eid, day, shift, nb):
                feasible = False
                break
        if not feasible:
            return nb
        emps1[emps1.index(e1)] = e2
        emps2[emps2.index(e2)] = e1
        nb.assignments[k1] = emps1
        nb.assignments[k2] = emps2
        return nb

    # ---- 3. Move employee A→B ----------------------------------------
    def _nb_move_emp(self, sol: Solution) -> Solution:
        nb = sol.copy()
        filled = [(k, emps) for k, emps in nb.assignments.items() if emps]
        if not filled:
            return nb
        (src_key, src_emps) = random.choice(filled)
        e = random.choice(src_emps)
        day_src, sh_src = src_key
        # choose random target shift (possibly same day)
        day_tgt = random.choice(self.days)
        shift_tgt = random.choice(self.p.shifts)
        tgt_key = (day_tgt, shift_tgt.id)
        if e in nb.assignments.get(tgt_key, []):
            return nb  # already there
        # feasibility
        if day_tgt in self.p.emp_by_id[e].absence_dates:
            return nb
        if self._rest_violation(e, day_tgt, shift_tgt, nb):
            return nb
        # weekly hours ok?
        # quick heuristic: allow if target week's load <= limit
        emp = self.p.emp_by_id[e]
        if emp.max_hours_per_week:
            wk_src = day_src.isocalendar()[:2]
            wk_tgt = day_tgt.isocalendar()[:2]
            delta = shift_tgt.duration - self.shift_by_id[sh_src].duration
            weekly = defaultdict(lambda: defaultdict(int))
            for (d, sid), emps in nb.assignments.items():
                hrs = self.shift_by_id[sid].duration
                for eid in emps:
                    weekly[eid][d.isocalendar()[:2]] += hrs
            if weekly[e][wk_tgt] + shift_tgt.duration > emp.max_hours_per_week:
                return nb
        # perform move
        src_emps.remove(e)
        nb.assignments[src_key] = src_emps
        nb.assignments.setdefault(tgt_key, []).append(e)
        return nb

    # ---- 4. Swap whole blocks ----------------------------------------
    def _nb_swap_block(self, sol: Solution) -> Solution:
        nb = sol.copy()
        keys = list(nb.assignments.keys())
        if len(keys) < 2:
            return nb
        k1, k2 = random.sample(keys, 2)
        nb.assignments[k1], nb.assignments[k2] = nb.assignments[k2], nb.assignments[k1]
        return nb

    # ------------------------ SA mechanics ---------------------------
    def _accept(self, curr: float, nxt: float, temp: float) -> bool:
        return nxt < curr or random.random() < math.exp((curr - nxt) / max(temp, 1e-9))

    def _cool(self, it: int) -> float:
        ratio = it / max(self.iterations - 1, 1)
        return self.init_temp * ((self.final_temp / self.init_temp) ** ratio)

    # --------------- final greedy fill to max_staff ------------------
    def _greedy_fill(self, sol: Solution) -> None:
        weekly = defaultdict(lambda: defaultdict(int))
        for (d, sid), emps in sol.assignments.items():
            hrs = self.shift_by_id[sid].duration
            for eid in emps:
                weekly[eid][d.isocalendar()[:2]] += hrs
        for d in self.days:
            wk_key = d.isocalendar()[:2]
            for sh in self.p.shifts:
                key = (d, sh.id)
                while len(sol.assignments[key]) < sh.max_staff:
                    cand = self._available_emps(d, sh, sol, weekly)
                    if not cand:
                        break
                    eid = random.choice(cand)
                    sol.assignments[key].append(eid)
                    weekly[eid][wk_key] += sh.duration
