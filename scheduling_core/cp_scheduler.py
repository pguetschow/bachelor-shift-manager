import math
import os
from collections import defaultdict
from datetime import timedelta, date
from typing import List, Set, Tuple, Dict

from ortools.sat.python import cp_model

# --- KPI Calculator ----------------------------------------------------------
from rostering_app.services.kpi_calculator import KPICalculator
from rostering_app.utils import is_non_working_day
from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry


class CPScheduler(SchedulingAlgorithm):
    """
    Constraint Programming scheduler using OR-Tools CP-SAT solver.

    Features:
    - Efficient handling of complex scheduling constraints
    - Built-in fairness optimization through utilization balancing
    - Advanced constraint propagation for faster solving
    - Flexible objective weighting system
    """

    # ------------------------------------------------------------------
    # Construction / meta
    # ------------------------------------------------------------------
    def __init__(
            self,
            *,
            sundays_off: bool = False,
            min_util_factor: float = 0.9,
            monthly_ot_cap: float = 0.05,
            yearly_ot_cap: float = 0.00,
            time_limit_seconds: int = 3600,
            fairness_weight: int = 100_000,
            use_symmetry_breaking: bool = True,
    ):
        self.sundays_off = sundays_off
        self.MIN_UTIL_FACTOR = min_util_factor
        self.MONTHLY_OT_CAP = monthly_ot_cap
        self.YEARLY_OT_CAP = yearly_ot_cap
        self.time_limit_seconds = time_limit_seconds
        self.fairness_weight = fairness_weight
        self.use_symmetry_breaking = use_symmetry_breaking
        self.holidays: Set[Tuple[int, int, int]] = set()
        self.company = None  # injected in ``solve``

    @property
    def name(self) -> str:
        return "Constraint Programming (OR-Tools CP-SAT)"

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:
        self.company = problem.company
        self.problem = problem
        kpi_calc = KPICalculator(self.company)

        print(f"[CP] Starting CP-SAT solver for {len(problem.employees)} employees, "
              f"{len(problem.shifts)} shifts")

        # ------------------------------------------------------------------
        # 0) Preprocessing: forbidden shift pairs & working days
        # ------------------------------------------------------------------
        from itertools import product

        forbidden_pairs = {
            (s1.id, s2.id)
            for s1, s2 in product(problem.shifts, repeat=2)
            if kpi_calc.violates_rest_period(s1, s2, problem.start_date)
        }

        # Working days only
        dates: List[date] = []
        current = problem.start_date
        while current <= problem.end_date:
            if not is_non_working_day(current, self.company):
                dates.append(current)
            current += timedelta(days=1)

        # Month buckets for constraints
        months = defaultdict(list)
        for d in dates:
            months[(d.year, d.month)].append(d)

        # Shift lookup
        shift_by_id = {sh.id: sh for sh in problem.shifts}

        print(f"[CP] Planning horizon: {len(dates)} working days, "
              f"{len(months)} months")

        # ------------------------------------------------------------------
        # 1) Create CP-SAT model
        # ------------------------------------------------------------------
        model = cp_model.CpModel()

        # ------------------------------------------------------------------
        # 2) Decision variables
        # ------------------------------------------------------------------
        # Main assignment variables: x[emp_id][date_idx][shift_id] = 1 if assigned
        x = {}
        feasible_assignments = []
        self.blocked_assignments = set()

        for emp in problem.employees:
            x[emp.id] = {}
            for d_idx, d in enumerate(dates):
                x[emp.id][d_idx] = {}
                for sh in problem.shifts:
                    var_name = f"x_{emp.id}_{d_idx}_{sh.id}"
                    x[emp.id][d_idx][sh.id] = model.NewBoolVar(var_name)

                    if not kpi_calc.is_date_blocked(emp, d):
                        feasible_assignments.append((emp.id, d_idx, sh.id))
                    else:
                        # Employee unavailable - fix variable to 0
                        model.Add(x[emp.id][d_idx][sh.id] == 0)
                        self.blocked_assignments.add((emp.id, d_idx, sh.id))

        print(f"[CP] Created {len(feasible_assignments)} feasible assignment variables")

        # Coverage variables for penalty calculation
        coverage = {}
        under_staffed = {}
        over_staffed = {}

        for d_idx, d in enumerate(dates):
            coverage[d_idx] = {}
            under_staffed[d_idx] = {}
            over_staffed[d_idx] = {}
            for sh in problem.shifts:
                # Actual coverage
                coverage[d_idx][sh.id] = model.NewIntVar(
                    0, len(problem.employees), f"cov_{d_idx}_{sh.id}"
                )

                # Understaffing penalty
                under_staffed[d_idx][sh.id] = model.NewIntVar(
                    0, sh.min_staff, f"under_{d_idx}_{sh.id}"
                )

                # Overstaffing penalty
                over_staffed[d_idx][sh.id] = model.NewIntVar(
                    0, len(problem.employees), f"over_{d_idx}_{sh.id}"
                )

        # Employee monthly/yearly hour variables
        monthly_hours = {}
        monthly_overtime = {}
        monthly_undertime = {}
        yearly_hours = {}

        for emp in problem.employees:
            yearly_hours[emp.id] = model.NewIntVar(
                0, 10000, f"yearly_{emp.id}"
            )

            monthly_hours[emp.id] = {}
            monthly_overtime[emp.id] = {}
            monthly_undertime[emp.id] = {}

            for ym in months:
                exp_hours = kpi_calc.calculate_expected_month_hours(
                    emp, *ym, self.company
                )
                max_hours = int(exp_hours * (1 + self.MONTHLY_OT_CAP))

                monthly_hours[emp.id][ym] = model.NewIntVar(
                    0, max_hours, f"month_{emp.id}_{ym}"
                )
                monthly_overtime[emp.id][ym] = model.NewIntVar(
                    0, 8, f"ot_{emp.id}_{ym}" # max 1 shift extra
                    # 0, max_hours - exp_hours, f"ot_{emp.id}_{ym}"
                )
                monthly_undertime[emp.id][ym] = model.NewIntVar(
                    0, exp_hours, f"ut_{emp.id}_{ym}"
                )

        # Fairness variables - utilization ratios scaled by 1000 for integer arithmetic
        possible_hours = self._compute_possible_hours(
            problem, dates, kpi_calc, shift_by_id
        )

        utilization_ratio = {}  # scaled by 1000
        min_utilization = model.NewIntVar(0, 1000, "min_util")
        max_utilization = model.NewIntVar(0, 1000, "max_util")

        for emp in problem.employees:
            if possible_hours[emp.id] > 0:
                utilization_ratio[emp.id] = model.NewIntVar(
                    0, 1000, f"util_{emp.id}"
                )

        print(f"[CP] Created auxiliary variables for {len(problem.employees)} employees")

        # ------------------------------------------------------------------
        # 3) Constraints
        # ------------------------------------------------------------------

        # Coverage constraints
        for d_idx, d in enumerate(dates):
            for sh in problem.shifts:
                # Define coverage as sum of assignments
                assigned_employees = []
                for emp in problem.employees:
                    if (emp.id, d_idx, sh.id) not in self.blocked_assignments:
                        assigned_employees.append(x[emp.id][d_idx][sh.id])

                if assigned_employees:
                    model.Add(coverage[d_idx][sh.id] == sum(assigned_employees))
                else:
                    model.Add(coverage[d_idx][sh.id] == 0)

                # Understaffing constraint
                model.Add(
                    coverage[d_idx][sh.id] + under_staffed[d_idx][sh.id] >= sh.min_staff
                )

                # Overstaffing constraint
                model.Add(
                    coverage[d_idx][sh.id] <= sh.max_staff + over_staffed[d_idx][sh.id]
                )

        # One shift per employee per day constraint
        for emp in problem.employees:
            for d_idx in range(len(dates)):
                shifts_assigned = []
                for sh in problem.shifts:
                    if (emp.id, d_idx, sh.id) not in self.blocked_assignments:
                        shifts_assigned.append(x[emp.id][d_idx][sh.id])

                if shifts_assigned:
                    model.Add(sum(shifts_assigned) <= 1)

        # Rest period constraints (11-hour rule)
        for emp in problem.employees:
            for d_idx in range(len(dates) - 1):
                for sid1, sid2 in forbidden_pairs:
                    # Only add constraint if both variables are feasible
                    if ((emp.id, d_idx, sid1) not in self.blocked_assignments and
                            (emp.id, d_idx + 1, sid2) not in self.blocked_assignments):
                        var1 = x[emp.id][d_idx][sid1]
                        var2 = x[emp.id][d_idx + 1][sid2]
                        model.Add(var1 + var2 <= 1)

        # Monthly hour constraints
        for emp in problem.employees:
            yearly_total = []

            for ym, month_dates in months.items():
                exp_hours = kpi_calc.calculate_expected_month_hours(
                    emp, *ym, self.company
                )

                # Calculate monthly worked hours
                month_assignments = []
                for d in month_dates:
                    d_idx = dates.index(d)
                    for sh in problem.shifts:
                        if (emp.id, d_idx, sh.id) not in self.blocked_assignments:
                            month_assignments.append(
                                x[emp.id][d_idx][sh.id] * int(sh.duration)
                            )

                if month_assignments:
                    model.Add(monthly_hours[emp.id][ym] == sum(month_assignments))
                else:
                    model.Add(monthly_hours[emp.id][ym] == 0)

                # Monthly overtime/undertime relationship
                model.Add(
                    monthly_hours[emp.id][ym] ==
                    exp_hours - monthly_undertime[emp.id][ym] + monthly_overtime[emp.id][ym]
                )

                # Minimum utilization constraint
                model.Add(
                    monthly_hours[emp.id][ym] >= int(exp_hours * self.MIN_UTIL_FACTOR)
                )

                yearly_total.append(monthly_hours[emp.id][ym])

            # Yearly hours constraint
            if yearly_total:
                model.Add(yearly_hours[emp.id] == sum(yearly_total))
            else:
                model.Add(yearly_hours[emp.id] == 0)

            # Yearly limits
            yearly_cap = kpi_calc.calculate_expected_yearly_hours(
                emp, problem.start_date.year
            )
            model.Add(yearly_hours[emp.id] <= yearly_cap)
            model.Add(yearly_hours[emp.id] >= int(yearly_cap * 0.85))

        # Fairness constraints - utilization ratio calculation
        active_employees = []
        for emp in problem.employees:
            ph = possible_hours[emp.id]
            if ph > 0:
                # utilization_ratio = (yearly_hours * 1000) / possible_hours
                model.AddDivisionEquality(
                    utilization_ratio[emp.id],
                    yearly_hours[emp.id] * 1000,
                    ph
                )
                active_employees.append(emp.id)

        if active_employees:
            # Min/max utilization constraints
            for emp_id in active_employees:
                model.Add(utilization_ratio[emp_id] >= min_utilization)
                model.Add(utilization_ratio[emp_id] <= max_utilization)

        # Symmetry breaking (optional)
        if self.use_symmetry_breaking and len(problem.employees) > 1:
            self._add_symmetry_breaking_constraints(model, x, problem, dates)

        print(f"[CP] Added all constraints")

        # ------------------------------------------------------------------
        # 4) Objective function
        # ------------------------------------------------------------------
        objective_terms = []

        # Coverage penalties
        W_UNDER = 5_000_000
        W_OVER = 500_000

        for d_idx in range(len(dates)):
            for sh in problem.shifts:
                objective_terms.append(W_UNDER * under_staffed[d_idx][sh.id])
                objective_terms.append(W_OVER * over_staffed[d_idx][sh.id])

        # Employee-related penalties
        W_OT = 250_000
        W_UT = 15_500

        for emp in problem.employees:
            for ym in months:
                objective_terms.append(W_OT * monthly_overtime[emp.id][ym])
                objective_terms.append(W_UT * monthly_undertime[emp.id][ym])

        # Fairness objective - minimize utilization spread
        if active_employees:
            utilization_spread = model.NewIntVar(0, 1000, "util_spread")
            model.Add(utilization_spread == max_utilization - min_utilization)
            objective_terms.append(self.fairness_weight * utilization_spread)

        # Preference bonus (if available)
        W_PREF = -5
        for emp in problem.employees:
            prefs = set(getattr(emp, "preferred_shifts", []))
            if prefs:
                for d_idx in range(len(dates)):
                    for sh in problem.shifts:
                        if (sh.name in prefs and
                                (emp.id, d_idx, sh.id) not in self.blocked_assignments):
                            objective_terms.append(W_PREF * x[emp.id][d_idx][sh.id])

        # Set objective
        if objective_terms:
            model.Minimize(sum(objective_terms))

        print(f"[CP] Objective function created with {len(objective_terms)} terms")

        # ------------------------------------------------------------------
        # 5) Solve
        # ------------------------------------------------------------------
        solver = cp_model.CpSolver()

        # Solver parameters
        solver.parameters.max_time_in_seconds = self.time_limit_seconds
        solver.parameters.num_search_workers = max(1, os.cpu_count() - 1)
        solver.parameters.log_search_progress = True

        # Adjust strategy based on problem size
        if len(problem.employees) * len(dates) > 10000:
            solver.parameters.search_branching = cp_model.PORTFOLIO_SEARCH
            solver.parameters.cp_model_presolve = True

        print(f"[CP] Starting solver with {solver.parameters.num_search_workers} workers, "
              f"{self.time_limit_seconds}s time limit")

        # Create solution callback for progress tracking
        class SolutionCallback(cp_model.CpSolverSolutionCallback):
            def __init__(self):
                cp_model.CpSolverSolutionCallback.__init__(self)
                self.solution_count = 0

            def on_solution_callback(self):
                self.solution_count += 1
                if self.solution_count % 10 == 0:
                    print(f"[CP] Found {self.solution_count} solutions, "
                          f"best objective: {self.ObjectiveValue()}")

        solution_callback = SolutionCallback()
        status = solver.Solve(model, solution_callback)

        # ------------------------------------------------------------------
        # 6) Extract results
        # ------------------------------------------------------------------
        print(f"[CP] Solver status: {solver.StatusName(status)}")
        print(f"[CP] Solutions found: {solution_callback.solution_count}")

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            print(f"[CP] Best objective value: {solver.ObjectiveValue()}")
            print(f"[CP] Solve time: {solver.WallTime():.2f}s")

            # Extract schedule
            schedule = []
            for emp_id, d_idx, sh_id in feasible_assignments:
                if solver.Value(x[emp_id][d_idx][sh_id]) == 1:
                    schedule.append(ScheduleEntry(emp_id, dates[d_idx], sh_id))

            print(f"[CP] Generated schedule with {len(schedule)} assignments")

            # Print utilization statistics
            if active_employees:
                min_util = solver.Value(min_utilization) / 1000.0
                max_util = solver.Value(max_utilization) / 1000.0
                print(f"[CP] Utilization range: {min_util:.1%} - {max_util:.1%} "
                      f"(spread: {max_util - min_util:.1%})")

            return schedule
        else:
            print(f"[CP] No solution found. Status: {solver.StatusName(status)}")
            return []

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _compute_possible_hours(
            self,
            problem: SchedulingProblem,
            dates: List[date],
            kpi_calc: KPICalculator,
            shift_by_id: Dict[int, any]
    ) -> Dict[int, int]:
        """Compute maximum possible working hours for each employee."""
        possible_hours = defaultdict(int)

        for emp in problem.employees:
            for d in dates:
                if not kpi_calc.is_date_blocked(emp, d):
                    # Add hours from all shifts they could work
                    for sh in problem.shifts:
                        possible_hours[emp.id] += int(sh.duration)

        return possible_hours

    def _add_symmetry_breaking_constraints(
            self,
            model: cp_model.CpModel,
            x: Dict,
            problem: SchedulingProblem,
            dates: List[date]
    ):
        """Add symmetry breaking constraints to speed up solving."""

        # Sort employees by ID for consistent ordering
        sorted_employees = sorted(problem.employees, key=lambda e: e.id)

        # For employees with identical constraints, enforce lexicographic ordering
        for i in range(len(sorted_employees) - 1):
            emp1, emp2 = sorted_employees[i], sorted_employees[i + 1]

            # Check if employees have similar availability (simplified check)
            if (emp1.max_hours_per_week == emp2.max_hours_per_week and
                    len(emp1.absence_dates) == len(emp2.absence_dates)):

                # Add lexicographic constraint for first few days
                for d_idx in range(min(7, len(dates))):
                    constraint_added = False
                    for sh in problem.shifts:
                        if ((emp1.id, d_idx, sh.id) not in self.blocked_assignments and
                                (emp2.id, d_idx, sh.id) not in self.blocked_assignments):
                            model.Add(
                                x[emp1.id][d_idx][sh.id] >= x[emp2.id][d_idx][sh.id]
                            )
                            constraint_added = True
                            break  # Only first constraint per day pair
                    if constraint_added:
                        break  # Only first day with valid constraint