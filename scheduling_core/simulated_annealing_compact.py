from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import timedelta, date
from typing import List, Dict, Tuple, Optional

from rostering_app.services.kpi_calculator import KPICalculator
from rostering_app.utils import get_working_days_in_range

from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry, Solution
from .utils import create_empty_solution, get_weeks  # `get_weeks` kept for potential debugging use


class SimulatedAnnealingScheduler(SchedulingAlgorithm):

    # ---------------------------------------------------------------------
    def __init__(
            self,
            *,
            iterations: int = 2_000,
            init_temp: float = 800.0,
            final_temp: float = 1.0,
            fairness_weight: int = 75_000,
            preference_weight: int = 50,  # bonus points for preferred shifts
            sundays_off: bool = False,
    ) -> None:
        self.iterations = iterations
        self.init_temp = init_temp
        self.final_temp = final_temp
        self.fairness_weight = fairness_weight
        self.preference_weight = preference_weight

    # public ----------------------------------------------------------------
    @property
    def name(self) -> str:
        return "Simulated Annealing"

    # ---------------------------------------------------------------------
    #                               SOLVE
    # ---------------------------------------------------------------------
    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:  # noqa: C901
        self.p = problem
        self.kpi = KPICalculator(problem.company)

        # 1) Day list (working days only) -----------------------------------
        self.days: List[date] = list(
            get_working_days_in_range(problem.start_date, problem.end_date, problem.company)
        )
        self.day_idx = {d: i for i, d in enumerate(self.days)}
        self.emp_index = {e.id: idx for idx, e in enumerate(problem.employees)}
        self.shift_index = {s.id: idx for idx, s in enumerate(problem.shifts)}
        self.shift_by_id = problem.shift_by_id

        # 2) Pre‑compute expected monthly / yearly hours --------------------
        self._compute_expected_hours()

        # 3) Pre‑compute "possible" hours (for fairness term) --------------
        self._compute_possible_hours()

        # 4) Build preference mapping ---------------------------------------
        self._build_preference_mapping()

        # 5) Greedy seed ----------------------------------------------------
        sol = self._initial_solution()
        best = sol.copy()
        best.cost = self._evaluate(best)

        # 6) Main SA loop ---------------------------------------------------
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

        # 7) Final greedy fill to max_staff --------------------------------
        self._greedy_fill(best)
        return best.to_entries()

    # ───────────────────────── internal helpers ───────────────────────────

    # ---------------------------------------------------------------------
    # Expectation helpers (monthly / yearly)
    # ---------------------------------------------------------------------
    def _compute_expected_hours(self) -> None:
        """Store expected hours per employee per (year, month) and per year."""
        # Months & years in planning horizon
        months_seen: Dict[Tuple[int, int], None] = {}
        years_seen: Dict[int, None] = {}
        for d in self.days:
            months_seen[(d.year, d.month)] = None
            years_seen[d.year] = None

        self.exp_month_hrs: Dict[int, Dict[Tuple[int, int], int]] = defaultdict(dict)
        self.exp_year_hrs: Dict[int, Dict[int, int]] = defaultdict(dict)
        for emp in self.p.employees:
            # monthly expectations
            for (y, m) in months_seen.keys():
                self.exp_month_hrs[emp.id][(y, m)] = self.kpi.calculate_expected_month_hours(
                    emp, y, m, self.p.company
                )
            # yearly expectations (could cover >1 year for multi‑year horizons)
            for y in years_seen.keys():
                self.exp_year_hrs[emp.id][y] = self.kpi.calculate_expected_yearly_hours(emp, y)

    # ---------------------------------------------------------------------
    # Possible hours (unchanged from v2.1) – for fairness evaluation only
    # ---------------------------------------------------------------------
    def _compute_possible_hours(self) -> None:
        self.possible_hours: Dict[int, int] = {e.id: 0 for e in self.p.employees}
        for d in self.days:
            for sh in self.p.shifts:
                for emp in self.p.employees:
                    if d not in emp.absence_dates:
                        self.possible_hours[emp.id] += sh.duration

    # ---------------------------------------------------------------------
    # Build preference mapping
    # ---------------------------------------------------------------------
    def _build_preference_mapping(self) -> None:
        """Build mapping of employee preferences for shifts."""
        self.employee_preferences: Dict[int, set] = {}
        for emp in self.p.employees:
            # Get preferred shifts - check for various possible attribute names
            prefs = set()
            if hasattr(emp, 'preferred_shifts') and emp.preferred_shifts:
                prefs = set(emp.preferred_shifts)
            elif hasattr(emp, 'preferences') and emp.preferences:
                prefs = set(emp.preferences)
            self.employee_preferences[emp.id] = prefs

    # ---------------------------------------------------------------------
    # Greedy seed construction
    # ---------------------------------------------------------------------
    def _initial_solution(self) -> Solution:
        sol = create_empty_solution(self.p)
        # Track currently assigned hours per employee per month & per year
        monthly = defaultdict(lambda: defaultdict(int))  # eid -> (y,m) -> hrs
        yearly = defaultdict(int)  # eid -> hrs

        for d in self.days:
            ym, yr = (d.year, d.month), d.year
            for sh in self.p.shifts:
                key = (d, sh.id)
                # First fill to *min_staff*
                cand = self._available_emps(d, sh, sol, monthly, yearly, need=sh.min_staff)
                sol.assignments[key] = cand
                for eid in cand:
                    monthly[eid][ym] += sh.duration
                    yearly[eid] += sh.duration

        # Second pass – fill up to *max_staff*
        for d in self.days:
            ym, yr = (d.year, d.month), d.year
            for sh in self.p.shifts:
                key = (d, sh.id)
                while len(sol.assignments[key]) < sh.max_staff:
                    cand = self._available_emps(d, sh, sol, monthly, yearly)
                    if not cand:
                        break

                    # Prefer employees who like this shift
                    preferred = [eid for eid in cand if sh.name in self.employee_preferences.get(eid, set())]
                    chosen = random.choice(preferred) if preferred else random.choice(cand)

                    sol.assignments[key].append(chosen)
                    monthly[chosen][ym] += sh.duration
                    yearly[chosen] += sh.duration
        return sol

    # ---------------------------------------------------------------------
    # Candidate employee filter (ABSENCE + REST + MONTH/YEAR caps)
    # ---------------------------------------------------------------------
    def _available_emps(
            self,
            day: date,
            shift,
            sol: Solution,
            monthly: Dict[int, Dict[Tuple[int, int], int]],
            yearly: Dict[int, int],
            *,
            need: Optional[int] = None,
    ) -> List[int]:
        ym = (day.year, day.month)
        candidates: List[int] = []
        for emp in self.p.employees:
            if day in emp.absence_dates:
                continue

            # Already working some shift that day?
            if any(emp.id in sol.assignments.get((day, s.id), []) for s in self.p.shifts):
                continue

            # Monthly cap (hard)
            exp_m = self.exp_month_hrs[emp.id][ym]
            if monthly[emp.id][ym] + shift.duration > exp_m:
                continue

            # Yearly cap (hard – sum over all relevant years)
            exp_y = self.exp_year_hrs[emp.id][day.year]
            if yearly[emp.id] + shift.duration > exp_y:
                continue

            # Rest‑period check (11h) – unchanged
            if self._rest_violation(emp.id, day, shift, sol):
                continue

            candidates.append(emp.id)

        # If we need a specific number, prioritize preferred employees
        if need is not None:
            preferred = [eid for eid in candidates if shift.name in self.employee_preferences.get(eid, set())]
            non_preferred = [eid for eid in candidates if shift.name not in self.employee_preferences.get(eid, set())]

            # Take preferred first, then non-preferred
            result = preferred[:need]
            if len(result) < need:
                result.extend(non_preferred[:need - len(result)])
            return result[:need]

        return candidates

    # ---------------------------------------------------------------------
    # Rest‑period helper (unchanged)
    # ---------------------------------------------------------------------
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

    # ---------------------------------------------------------------------
    # Evaluation (monthly/yearly penalties instead of weekly)
    # ---------------------------------------------------------------------
    def _evaluate(self, sol: Solution) -> float:  # lower is better
        pen, bonus = 0, 0
        monthly_hrs = defaultdict(lambda: defaultdict(int))
        yearly_hrs = defaultdict(int)
        worked_hrs = defaultdict(int)  # used for fairness metric

        for (d, sid), emps in sol.assignments.items():
            sh = self.shift_by_id[sid]
            staff = len(emps)

            # Coverage penalties & bonus
            if staff < sh.min_staff:
                pen += (sh.min_staff - staff) * 5_000_000
            elif staff > sh.max_staff:
                pen += (staff - sh.max_staff) * 500_000
            else:
                bonus -= staff * 10_000  # Encourage fully staffed shifts

            for eid in emps:
                ym = (d.year, d.month)
                monthly_hrs[eid][ym] += sh.duration
                yearly_hrs[eid] += sh.duration
                worked_hrs[eid] += sh.duration

        # Calculate preference bonus
        pref_bonus = self._calculate_preference_bonus(sol)
        bonus += pref_bonus

        # Monthly & yearly caps -------------------------------------------
        for emp in self.p.employees:
            for ym, hrs in monthly_hrs[emp.id].items():
                exp_m = self.exp_month_hrs[emp.id][ym]
                if hrs > exp_m:
                    pen += (hrs - exp_m) * 2_000_000
            for y, exp_y in self.exp_year_hrs[emp.id].items():
                hrs_y = yearly_hrs[emp.id] if y == list(self.exp_year_hrs[emp.id].keys())[0] else 0
                if hrs_y > exp_y:
                    pen += (hrs_y - exp_y) * 5_000_000

        # Rest‑period penalty (unchanged) -----------------------------------
        pen += self._rest_violations(sol) * 50_000_000

        # Fairness penalty (unchanged) --------------------------------------
        ratios = [worked_hrs[eid] / ph for eid, ph in self.possible_hours.items() if ph > 0]
        fair_pen = 0
        if ratios:
            fair_pen = (max(ratios) - min(ratios)) * self.fairness_weight

        return pen + bonus + fair_pen

    def _calculate_preference_bonus(self, sol: Solution) -> int:
        """Calculate bonus points for assigning employees to preferred shifts."""
        bonus = 0
        for (day, sh_id), emp_ids in sol.assignments.items():
            shift = self.shift_by_id[sh_id]
            for emp_id in emp_ids:
                if shift.name in self.employee_preferences.get(emp_id, set()):
                    bonus += self.preference_weight
        return bonus

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

    # ---------------------------------------------------------------------
    # Neighbour generation --------------------------------------------------
    # ---------------------------------------------------------------------
    def _neighbor(self, sol: Solution) -> Solution:
        nb = sol.copy()
        day = random.choice(self.days)
        shift = random.choice(self.p.shifts)
        key = (day, shift.id)
        assigned = nb.assignments.get(key, [])

        # Build hour‑maps for current solution --------------------------------
        monthly = defaultdict(lambda: defaultdict(int))
        yearly = defaultdict(int)
        for (d, sid), emps in nb.assignments.items():
            s = self.shift_by_id[sid]
            for eid in emps:
                monthly[eid][(d.year, d.month)] += s.duration
                yearly[eid] += s.duration

        if assigned and (random.random() < 0.5):  # remove one
            eid = assigned.pop(random.randrange(len(assigned)))
            ym = (day.year, day.month)
            monthly[eid][ym] -= shift.duration
            yearly[eid] -= shift.duration
        else:  # try to add
            cand = self._available_emps(day, shift, nb, monthly, yearly)
            if cand:
                # Bias towards preferred employees
                preferred = [eid for eid in cand if shift.name in self.employee_preferences.get(eid, set())]
                if preferred and random.random() < 0.7:  # 70% chance to pick preferred
                    chosen = random.choice(preferred)
                else:
                    chosen = random.choice(cand)

                assigned.append(chosen)
                ym = (day.year, day.month)
                monthly[chosen][ym] += shift.duration
                yearly[chosen] += shift.duration

        nb.assignments[key] = assigned
        return nb

    # ---------------------------------------------------------------------
    # Final greedy fill (mirrors _initial_solution logic)
    # ---------------------------------------------------------------------
    def _greedy_fill(self, sol: Solution) -> None:
        monthly = defaultdict(lambda: defaultdict(int))
        yearly = defaultdict(int)
        for (d, sid), emps in sol.assignments.items():
            hrs = self.shift_by_id[sid].duration
            for eid in emps:
                monthly[eid][(d.year, d.month)] += hrs
                yearly[eid] += hrs

        for d in self.days:
            ym = (d.year, d.month)
            for sh in self.p.shifts:
                key = (d, sh.id)
                while len(sol.assignments[key]) < sh.max_staff:
                    cand = self._available_emps(d, sh, sol, monthly, yearly)
                    if not cand:
                        break

                    # Prefer employees who like this shift
                    preferred = [eid for eid in cand if sh.name in self.employee_preferences.get(eid, set())]
                    eid = random.choice(preferred) if preferred else random.choice(cand)

                    sol.assignments[key].append(eid)
                    monthly[eid][ym] += sh.duration
                    yearly[eid] += sh.duration

    # ---------------------------------------------------------------------
    # SA helpers (unchanged apart from docstring)
    # ---------------------------------------------------------------------
    def _accept(self, curr: float, nxt: float, temp: float) -> bool:
        return nxt < curr or random.random() < math.exp((curr - nxt) / max(temp, 1e-9))

    def _cool(self, it: int) -> float:
        ratio = it / max(self.iterations - 1, 1)
        base = self.init_temp * (self.final_temp / self.init_temp) ** ratio
        # aggressive cooling mid‑run
        if ratio < 0.3:
            return base
        elif ratio < 0.7:
            return base * 0.7
        return base * 0.3
