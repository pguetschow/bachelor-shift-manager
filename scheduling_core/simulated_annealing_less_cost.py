import math
import random
from collections import defaultdict
from datetime import timedelta, date
from enum import Enum
from typing import List, Dict

from rostering_app.services.kpi_calculator import KPICalculator
from rostering_app.utils import (get_working_days_in_range)
from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry, Solution
from .utils import (
    get_weeks, create_empty_solution,
)


class CoolingSchedule(Enum):
    """Types of cooling schedules."""
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    LOGARITHMIC = "logarithmic"


class NewSimulatedAnnealingScheduler(SchedulingAlgorithm):
    """ SA with focus on high coverage and utilization."""

    def __init__(self, initial_temp=2000, final_temp=1, max_iterations=2000,
                 cooling_schedule=CoolingSchedule.EXPONENTIAL, sundays_off=False):
        self.initial_temp = initial_temp
        self.final_temp = final_temp
        self.max_iterations = max_iterations
        self.cooling_schedule = cooling_schedule
        self.sundays_off = sundays_off
        self.holidays = set()
        self.company = None  # Will be set in solve method

    @property
    def name(self) -> str:
        return "Simulated Annealing less cost"

    def _get_holidays_for_year(self, year: int) -> set:
        """Get holidays as (month, day) tuples using utils function."""
        from rostering_app.utils import get_holidays_for_year
        return get_holidays_for_year(year)

    def _is_non_working_day(self, date) -> bool:
        """Check if a date is a non-working day (holiday or Sunday)."""
        if (date.month, date.day) in self.holidays:
            return True
        if date.weekday() == 6 and self.sundays_off:
            return True
        return False

    def _violates_rest_period(self, shift1, shift2, date1) -> bool:
        """Check if two consecutive shifts violate 11-hour rest period."""
        # Use KPI Calculator for consistent rest period validation
        from rostering_app.services.kpi_calculator import KPICalculator
        kpi_calculator = KPICalculator(self.company)
        return kpi_calculator.violates_rest_period(shift1, shift2, date1)

    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:
        """Solve using simulated annealing with proper constraints."""
        self.problem = problem
        self.company = problem.company
        self.weeks = get_weeks(problem.start_date, problem.end_date)

        # Get working days using utils
        self.working_days = get_working_days_in_range(
            problem.start_date, problem.end_date, self.company
        )
        self.total_days = (problem.end_date - problem.start_date).days + 1

        print(f"[SA] Schedule period: {problem.start_date} to {problem.end_date}")
        print(f"[SA] Total days: {self.total_days}, Working days: {len(self.working_days)}")

        # Calculate employee capacities
        self._calculate_employee_capacities()

        # Create initial solution
        current_solution = self._create_aggressive_initial_solution()
        current_cost = self._evaluate_aggressive(current_solution)
        current_solution.cost = current_cost

        best_solution = current_solution.copy()
        best_cost = current_cost

        # Initialize temperature
        temperature = self.initial_temp

        # Track improvement
        no_improvement_count = 0
        last_improvement_iteration = 0

        # Annealing process
        for iteration in range(self.max_iterations):
            # Get neighbor
            neighbor = self._get_coverage_focused_neighbor(current_solution)
            neighbor_cost = self._evaluate_aggressive(neighbor)

            # Calculate acceptance probability
            delta = neighbor_cost - current_cost

            if delta < 0 or random.random() < math.exp(-delta / temperature):
                current_solution = neighbor
                current_cost = neighbor_cost

                if current_cost < best_cost:
                    best_solution = current_solution.copy()
                    best_cost = current_cost
                    no_improvement_count = 0
                    last_improvement_iteration = iteration
                else:
                    no_improvement_count += 1

            # Cool down
            temperature = self._update_temperature(iteration, temperature)

            # Early termination
            if temperature < self.final_temp:
                break

            # Restart if stuck
            if no_improvement_count > 300:
                current_solution = self._create_aggressive_initial_solution()
                current_cost = self._evaluate_aggressive(current_solution)
                no_improvement_count = 0
                temperature = self.initial_temp * 0.3

            # Progress reporting
            if iteration % 100 == 0:
                coverage_rate = self._calculate_coverage_rate(best_solution)
                utilization_rate = self._calculate_utilization_rate(best_solution)
                print(f"[SA] Iter {iteration}: Cost={best_cost:.0f}, Coverage={coverage_rate:.1%}, "
                      f"Utilization={utilization_rate:.1%}, Temp={temperature:.1f}")

        # Final optimization
        self._greedy_fill_gaps(best_solution)

        # Rest period violations should be handled during optimization, not in cleanup

        # REMOVED: _validate_and_fix_overstaffing - no longer needed since neighborhood functions enforce max_staff

        return best_solution.to_entries()

    def _calculate_employee_capacities(self):
        """Calculate actual capacity for each employee over the schedule period using KPI Calculator."""
        self.employee_capacity = {}

        for emp in self.problem.employees:
            # Use KPI Calculator to get expected yearly hours, then scale to the problem period
            kpi_calculator = KPICalculator(self.company)
            yearly_capacity = kpi_calculator.calculate_expected_yearly_hours(emp, self.problem.start_date.year)
            
            # Calculate total working days in the year using the same logic as KPI Calculator
            year = self.problem.start_date.year
            start = date(year, 1, 1)
            end = date(year, 12, 31)
            day = start
            total_working_days_in_year = 0
            
            while day <= end:
                if not self._is_non_working_day(day) and day not in emp.absence_dates:
                    total_working_days_in_year += 1
                day += timedelta(days=1)
            
            # Scale capacity to the problem period
            working_days_in_period = len(self.working_days)
            period_capacity = yearly_capacity * (working_days_in_period / total_working_days_in_year)
            
            self.employee_capacity[emp.id] = period_capacity

    def _create_aggressive_initial_solution(self) -> Solution:
        """Create initial solution with aggressive but valid staffing."""
        solution = create_empty_solution(self.problem)

        # Pre-calculate daily availability
        daily_availability = {}
        for date in self.working_days:
            available = []
            for emp in self.problem.employees:
                if date not in emp.absence_dates:
                    available.append(emp.id)
            daily_availability[date] = available

        # Track weekly hours
        weekly_hours = defaultdict(lambda: defaultdict(float))

        # Assign employees with better initial balance
        for date in self.working_days:
            week_key = date.isocalendar()[:2]

            # Sort shifts by priority: consider overlap constraints and staffing needs
            shift_priorities = []
            for shift in self.problem.shifts:
                # Calculate current month average for this shift
                month_start = date.replace(day=1)
                month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                shift_total = 0
                shift_count = 0
                
                for d in self.working_days:
                    if month_start <= d <= month_end:
                        shift_total += len(solution.assignments.get((d, shift.id), []))
                        shift_count += 1
                
                avg_staffing = shift_total / max(shift_count, 1)
                coverage_ratio = avg_staffing / shift.max_staff if shift.max_staff > 0 else 0
                
                # Calculate overlap penalty - shifts that overlap with others get higher priority
                overlap_penalty = 0
                for other_shift in self.problem.shifts:
                    if other_shift.id != shift.id:
                        # Check if shifts overlap
                        if (shift.start < other_shift.end and shift.end > other_shift.start):
                            overlap_penalty += 1
                
                # Priority: aim for balanced distribution like ILP
                # Lower coverage ratio gets higher priority (fill understaffed shifts first)
                # Then consider overlap constraints
                priority = (1 - coverage_ratio, overlap_penalty, -shift.duration)
                shift_priorities.append((shift, priority))
            
            # Sort by priority
            sorted_shifts = [s[0] for s in sorted(shift_priorities, key=lambda x: x[1])]

            for shift in sorted_shifts:
                key = (date, shift.id)

                # Get candidates
                candidates = []
                for eid in daily_availability[date]:
                    emp = self.problem.emp_by_id[eid]
                    current_weekly = weekly_hours[eid][week_key]

                    # Check if already assigned today
                    already_assigned = any(
                        eid in solution.assignments.get((date, s.id), [])
                        for s in self.problem.shifts
                    )

                    if (not already_assigned and
                        current_weekly + shift.duration <= emp.max_hours_per_week):
                        
                        # Check rest period violations before adding
                        if not self._check_rest_period_violation_for_employee(solution, eid, date, shift):
                            remaining_capacity = emp.max_hours_per_week - current_weekly
                            preference_bonus = 10 if shift.name in emp.preferred_shifts else 0
                            score = remaining_capacity + preference_bonus
                            candidates.append((eid, score))

                # Sort by score
                candidates.sort(key=lambda x: x[1], reverse=True)

                # Assign with balanced approach like ILP
                # Aim for max_staff but ensure at least min_staff
                target = min(
                    shift.max_staff,  # Never exceed max_staff
                    max(shift.min_staff, len(candidates)),  # At least min_staff if possible
                    len(candidates)  # Can't assign more than available
                )

                if target > 0:
                    selected = [c[0] for c in candidates[:target]]
                    solution.assignments[key] = selected

                    # Update weekly hours
                    for emp_id in selected:
                        weekly_hours[emp_id][week_key] += shift.duration
                else:
                    solution.assignments[key] = []

        return solution

    def _evaluate_aggressive(self, solution: Solution) -> float:
        """Evaluation function - optimized to remove redundant constraints already enforced by neighborhood functions."""
        penalty = 0

        # Weights - removed redundant constraint weights
        w_understaff = 5_000_000
        w_rest_period = 50_000_000  # Increased penalty for rest period violations
        w_utilization = -25_000
        w_coverage_bonus = -10_000
        w_full_coverage = -5_000
        w_preference = -100
        w_shift_balance = 500_000  # Increased penalty for uneven shift distribution

        # Track metrics
        total_positions = 0
        filled_positions = 0
        shifts_at_max = 0

        # 1. Staffing constraints - only check understaffing since overstaffing is enforced by neighborhood
        for current in self.working_days:
            for shift in self.problem.shifts:
                assigned = solution.assignments.get((current, shift.id), [])
                count = len(assigned)

                total_positions += shift.max_staff
                filled_positions += min(count, shift.max_staff)

                if count < shift.min_staff:
                    penalty += (shift.min_staff - count) * w_understaff
                else:
                    penalty += count * w_coverage_bonus
                    if count == shift.max_staff:
                        penalty += w_full_coverage
                        shifts_at_max += 1

        # 2. Rest periods - added back as violations can still occur from initial solution
        rest_violations = self._check_rest_periods(solution)
        penalty += rest_violations * w_rest_period

        # 3. Utilization - keep this as it's not directly enforced by neighborhood
        emp_hours = self._calculate_employee_hours(solution)
        for emp in self.problem.employees:
            worked_hours = emp_hours.get(emp.id, 0)
            capacity = self.employee_capacity[emp.id]

            if capacity > 0:
                kpi_calculator = KPICalculator(self.company)
                utilization = kpi_calculator.calculate_utilization_percentage(worked_hours, capacity)
                if 0.85 <= utilization <= 0.95:
                    penalty += w_utilization * utilization
                elif utilization > 0.95:
                    penalty += (utilization - 0.95) * 1000
                else:
                    penalty += (0.85 - utilization) * abs(w_utilization) * 2

        # 4. Shift balance penalty - penalize uneven distribution across shifts
        shift_balance_penalty = self._calculate_shift_balance_penalty(solution)
        penalty += shift_balance_penalty * w_shift_balance

        # 5. Preferences - keep this as it's a soft constraint
        for (date, shift_id), emp_ids in solution.assignments.items():
            shift = self.problem.shift_by_id[shift_id]
            for emp_id in emp_ids:
                emp = self.problem.emp_by_id[emp_id]
                if shift.name in emp.preferred_shifts:
                    penalty += w_preference

        return penalty

    def _calculate_shift_balance_penalty(self, solution: Solution) -> float:
        """Calculate penalty for uneven shift distribution using aggressive quadratic approach."""
        penalty = 0.0
        
        # Calculate daily penalties for each shift
        for current in self.working_days:
            for shift in self.problem.shifts:
                assigned = len(solution.assignments.get((current, shift.id), []))
                
                # Quadratic penalty: penalize deviation from max_staff more aggressively
                # This strongly encourages shifts to reach their maximum staffing levels
                if shift.max_staff > 0:
                    # Quadratic penalty increases more aggressively as we get further from max_staff
                    deviation_ratio = (shift.max_staff - assigned) / shift.max_staff
                    deviation_penalty = deviation_ratio ** 2  # Quadratic penalty
                    penalty += deviation_penalty
                
                # Additional penalty for understaffing (below min_staff)
                if assigned < shift.min_staff:
                    understaff_penalty = (shift.min_staff - assigned) ** 2  # Quadratic understaffing penalty
                    penalty += understaff_penalty
        
        return penalty

    def _check_rest_periods(self, solution: Solution) -> int:
        """Check 11-hour rest period constraints."""
        violations = 0
        dates = []
        current = self.problem.start_date
        while current <= self.problem.end_date:
            dates.append(current)
            current += timedelta(days=1)

        for i in range(len(dates) - 1):
            d1, d2 = dates[i], dates[i + 1]
            for emp in self.problem.employees:
                shift1 = None
                shift2 = None

                for shift in self.problem.shifts:
                    if emp.id in solution.assignments.get((d1, shift.id), []):
                        shift1 = shift
                    if emp.id in solution.assignments.get((d2, shift.id), []):
                        shift2 = shift

                if shift1 and shift2 and self._violates_rest_period(shift1, shift2, d1):
                    violations += 1

        return violations

    def _calculate_employee_hours(self, solution: Solution) -> Dict[int, float]:
        """Calculate total hours worked by each employee."""
        emp_hours: Dict[int, float] = defaultdict(float)
        for (date, shift_id), emp_ids in solution.assignments.items():
            shift = self.problem.shift_by_id[shift_id]
            for emp_id in emp_ids:
                emp_hours[emp_id] += shift.duration
        return emp_hours

    def _calculate_coverage_rate(self, solution: Solution) -> float:
        """Calculate overall coverage rate."""
        total_positions = 0
        filled_positions = 0
        for current in self.working_days:
            for shift in self.problem.shifts:
                assigned = len(solution.assignments.get((current, shift.id), []))
                total_positions += shift.max_staff
                filled_positions += min(assigned, shift.max_staff)
        return filled_positions / total_positions if total_positions > 0 else 0

    def _calculate_utilization_rate(self, solution: Solution) -> float:
        """Calculate average employee utilization rate."""
        emp_hours = self._calculate_employee_hours(solution)
        total_utilization = 0
        count = 0
        for emp in self.problem.employees:
            worked = emp_hours.get(emp.id, 0)
            capacity = self.employee_capacity[emp.id]
            kpi_calculator = KPICalculator(self.company)
            utilization = kpi_calculator.calculate_utilization_percentage(worked, capacity)
            if capacity > 0:
                total_utilization += utilization / 100.0
                count += 1
        return total_utilization / count if count > 0 else 0

    def _get_coverage_focused_neighbor(self, solution: Solution) -> Solution:
        """Generate neighbor with focus on improving coverage."""
        neighbor = solution.copy()

        # Operations with weights - consolidated into 5 focused operations
        operations = [
            'fill_and_balance',      # Combines fill_gaps, maximize_shift, and balance operations
            'rest_period_management', # Combines fix_rest_violations and prevent_rest_violations
            'redistribute_staff',     # Staff redistribution and swapping
            'utilization_optimization', # Utilization boosting and optimization
            'coverage_improvement'    # Coverage-focused improvements
        ]
        weights = [0.30, 0.30, 0.20, 0.10, 0.10]  # Balanced weights for core operations

        operation = random.choices(operations, weights=weights)[0]

        if operation == 'fill_and_balance':
            # Combined operation: fill gaps, maximize shifts, and balance distribution
            if random.random() < 0.4:
                self._fill_understaffed_shifts(neighbor)
            elif random.random() < 0.7:
                self._maximize_random_shift(neighbor)
            else:
                self._aggressive_balance_shifts(neighbor)
                
        elif operation == 'rest_period_management':
            # Combined operation: fix and prevent rest period violations
            if random.random() < 0.6:
                self._fix_rest_period_violations(neighbor)
            else:
                self._prevent_rest_period_violations(neighbor)
                
        elif operation == 'redistribute_staff':
            # Combined operation: redistribute staff and swap for better coverage
            if random.random() < 0.7:
                self._redistribute_staff(neighbor)
            else:
                self._swap_for_better_coverage(neighbor)
                
        elif operation == 'utilization_optimization':
            # Focus on utilization improvements
            self._boost_underutilized_employee(neighbor)
            
        elif operation == 'coverage_improvement':
            # Focus on general coverage improvements
            self._balance_shift_distribution(neighbor)

        return neighbor

    def _fill_understaffed_shifts(self, solution: Solution):
        """Fill shifts that are below capacity - FIXED to respect max_staff."""
        understaffed = []

        for (date, shift_id), assigned in solution.assignments.items():
            if date in self.working_days:
                shift = self.problem.shift_by_id[shift_id]
                if len(assigned) < shift.max_staff:
                    gap = shift.max_staff - len(assigned)
                    understaffed.append(((date, shift_id), gap, len(assigned)))

        if not understaffed:
            return

        # Sort by current staffing level (fill emptiest first)
        understaffed.sort(key=lambda x: x[2])

        # Try to fill the most understaffed shift
        (date, shift_id), gap, current_count = understaffed[0]
        shift = self.problem.shift_by_id[shift_id]
        assigned = solution.assignments[(date, shift_id)]

        # Double-check we don't exceed max_staff
        actual_gap = shift.max_staff - len(assigned)
        if actual_gap <= 0:
            return

        # Find available employees
        week_key = date.isocalendar()[:2]
        candidates = []

        for emp in self.problem.employees:
            if (emp.id not in assigned and
                date not in emp.absence_dates):

                # Check no other shift that day
                has_shift = any(
                    emp.id in solution.assignments.get((date, s.id), [])
                    for s in self.problem.shifts if s.id != shift_id
                )

                if not has_shift:
                    # Check weekly capacity
                    weekly_hours = self._get_employee_weekly_hours(solution, emp.id, week_key)
                    if weekly_hours + shift.duration <= emp.max_hours_per_week:
                        # Check rest period violations
                        if not self._check_rest_period_violation_for_employee(solution, emp.id, date, shift):
                            candidates.append(emp.id)

        # Add employees - ENSURE we don't exceed max_staff
        if candidates:
            add_count = min(actual_gap, len(candidates))
            selected = random.sample(candidates, add_count)

            # Final safety check
            new_total = len(assigned) + len(selected)
            if new_total <= shift.max_staff:
                assigned.extend(selected)

    def _maximize_random_shift(self, solution: Solution):
        """Bring a random shift to max capacity - FIXED."""
        working_keys = [(d, s) for (d, s) in solution.assignments.keys() if d in self.working_days]
        if not working_keys:
            return

        key = random.choice(working_keys)
        date, shift_id = key
        shift = self.problem.shift_by_id[shift_id]
        assigned = solution.assignments[key]

        # Check current staffing
        current_count = len(assigned)
        if current_count >= shift.max_staff:
            return

        # Calculate actual gap
        gap = shift.max_staff - current_count

        week_key = date.isocalendar()[:2]
        candidates = []

        for emp in self.problem.employees:
            if (emp.id not in assigned and
                date not in emp.absence_dates):

                has_shift = any(
                    emp.id in solution.assignments.get((date, s.id), [])
                    for s in self.problem.shifts if s.id != shift_id
                )

                if not has_shift:
                    weekly_hours = self._get_employee_weekly_hours(solution, emp.id, week_key)
                    if weekly_hours + shift.duration <= emp.max_hours_per_week:
                        # Check rest period violations
                        if not self._check_rest_period_violation_for_employee(solution, emp.id, date, shift):
                            worked = sum(
                                s.duration for (d, sid), emps in solution.assignments.items()
                                if emp.id in emps for s in [self.problem.shift_by_id[sid]]
                            )
                            capacity = self.employee_capacity[emp.id]
                            utilization = worked / capacity if capacity > 0 else 1
                            candidates.append((emp.id, utilization))

        if candidates:
            # Sort by utilization (lower first)
            candidates.sort(key=lambda x: x[1])

            # Add up to the gap
            add_count = min(gap, len(candidates))
            selected = [c[0] for c in candidates[:add_count]]

            # Final check
            if len(assigned) + len(selected) <= shift.max_staff:
                assigned.extend(selected)

    def _redistribute_staff(self, solution: Solution):
        """Move staff from shifts at max capacity to understaffed shifts."""
        at_max = []
        understaffed = []

        for (date, shift_id), assigned in solution.assignments.items():
            shift = self.problem.shift_by_id[shift_id]
            if len(assigned) == shift.max_staff:
                at_max.append((date, shift_id))
            elif len(assigned) < shift.min_staff:
                understaffed.append((date, shift_id))

        if not at_max or not understaffed:
            return

        # Move from shift at max capacity
        source_key = random.choice(at_max)
        source_date, source_shift_id = source_key
        source_assigned = solution.assignments[source_key]

        # Try to redistribute one employee
        if source_assigned:
            emp_id = random.choice(source_assigned)
            emp = self.problem.emp_by_id[emp_id]

            # Find compatible target
            random.shuffle(understaffed)
            for target_key in understaffed:
                target_date, target_shift_id = target_key
                target_shift = self.problem.shift_by_id[target_shift_id]
                target_assigned = solution.assignments[target_key]

                # Check if can move
                if (target_date == source_date and
                    emp_id not in target_assigned and
                    len(target_assigned) < target_shift.max_staff):
                    # Check rest period violations
                    if not self._check_rest_period_violation_for_employee(solution, emp_id, target_date, target_shift):
                        source_assigned.remove(emp_id)
                        target_assigned.append(emp_id)
                        return

    def _swap_for_better_coverage(self, solution: Solution):
        """Swap employees to improve coverage."""
        below_max = []
        at_min_or_above = []

        for (date, shift_id), assigned in solution.assignments.items():
            if date in self.working_days:
                shift = self.problem.shift_by_id[shift_id]
                if len(assigned) < shift.max_staff:
                    below_max.append((date, shift_id))
                if shift.min_staff < len(assigned) <= shift.max_staff:
                    at_min_or_above.append((date, shift_id))

        if not below_max or not at_min_or_above:
            return

        target_key = random.choice(below_max)
        source_key = random.choice(at_min_or_above)

        if target_key == source_key:
            return

        target_date, target_shift_id = target_key
        source_date, source_shift_id = source_key
        target_shift = self.problem.shift_by_id[target_shift_id]

        source_assigned = solution.assignments[source_key]
        target_assigned = solution.assignments[target_key]

        if not source_assigned or len(target_assigned) >= target_shift.max_staff:
            return

        # Find employee to move
        for emp_id in source_assigned:
            emp = self.problem.emp_by_id[emp_id]

            if (target_date not in emp.absence_dates and
                target_date in self.working_days and
                emp_id not in target_assigned):

                has_other_shift = any(
                    emp_id in solution.assignments.get((target_date, s.id), [])
                    for s in self.problem.shifts if s.id != target_shift_id
                )

                if not has_other_shift:
                    # Check rest period violations
                    if not self._check_rest_period_violation_for_employee(solution, emp_id, target_date, target_shift):
                        source_assigned.remove(emp_id)
                        target_assigned.append(emp_id)
                        return

    def _boost_underutilized_employee(self, solution: Solution):
        """Assign more shifts to underutilized employees - FIXED."""
        emp_hours = self._calculate_employee_hours(solution)

        # Find underutilized employees
        underutilized = []
        for emp in self.problem.employees:
            worked = emp_hours.get(emp.id, 0)
            capacity = self.employee_capacity[emp.id]
            if capacity > 0:
                utilization = worked / capacity
                if utilization < 0.8:
                    underutilized.append((emp.id, utilization))

        if not underutilized:
            return

        # Sort by utilization
        underutilized.sort(key=lambda x: x[1])
        emp_id, _ = underutilized[0]
        emp = self.problem.emp_by_id[emp_id]

        # Find shifts where employee can be added
        additions = 0
        max_additions = 3

        for (date, shift_id), assigned in solution.assignments.items():
            if date in self.working_days:
                shift = self.problem.shift_by_id[shift_id]

                # Check if can add
                if (emp_id not in assigned and
                    len(assigned) < shift.max_staff and  # FIXED: check max_staff
                    date not in emp.absence_dates):

                    has_shift = any(
                        emp_id in solution.assignments.get((date, s.id), [])
                        for s in self.problem.shifts
                    )

                    if not has_shift:
                        week_key = date.isocalendar()[:2]
                        weekly_hours = self._get_employee_weekly_hours(solution, emp_id, week_key)

                        if weekly_hours + shift.duration <= emp.max_hours_per_week:
                            # Check rest period violations
                            if not self._check_rest_period_violation_for_employee(solution, emp_id, date, shift):
                                assigned.append(emp_id)
                                additions += 1

                                if additions >= max_additions:
                                    return

    def _fix_rest_period_violations(self, solution: Solution):
        """Fix rest period violations aggressively by trying multiple strategies."""
        violations = self._find_rest_period_violations(solution)
        
        if not violations:
            return
        
        # Try to fix multiple violations (up to 3)
        violations_to_fix = min(3, len(violations))
        fixed_count = 0
        
        for _ in range(violations_to_fix):
            if not violations:
                break
                
            # Try to fix a random violation
            emp_id, date1, date2, shift1, shift2 = random.choice(violations)
            
            # Strategy 1: Try to move the employee from one of the violating shifts to a different shift on the same day
            if self._try_move_to_different_shift(solution, emp_id, date1, shift1):
                violations.remove((emp_id, date1, date2, shift1, shift2))
                fixed_count += 1
                continue
            if self._try_move_to_different_shift(solution, emp_id, date2, shift2):
                violations.remove((emp_id, date1, date2, shift1, shift2))
                fixed_count += 1
                continue
            
            # Strategy 2: Try to swap with another employee who doesn't have rest period issues
            if self._try_swap_employee_for_rest_period(solution, emp_id, date1, date2, shift1, shift2):
                violations.remove((emp_id, date1, date2, shift1, shift2))
                fixed_count += 1
                continue
            
            # Strategy 3: Remove employee from one of the shifts (prefer the one with more staff)
            shift1_count = len(solution.assignments.get((date1, shift1.id), []))
            shift2_count = len(solution.assignments.get((date2, shift2.id), []))
            
            if shift1_count > shift2_count:
                # Remove from first shift (more staff)
                if emp_id in solution.assignments.get((date1, shift1.id), []):
                    solution.assignments[(date1, shift1.id)].remove(emp_id)
            else:
                # Remove from second shift
                if emp_id in solution.assignments.get((date2, shift2.id), []):
                    solution.assignments[(date2, shift2.id)].remove(emp_id)
            
            violations.remove((emp_id, date1, date2, shift1, shift2))
            fixed_count += 1

    def _find_rest_period_violations(self, solution: Solution) -> List[tuple]:
        """Find all rest period violations in the solution."""
        violations = []
        dates = []
        current = self.problem.start_date
        while current <= self.problem.end_date:
            dates.append(current)
            current += timedelta(days=1)

        for i in range(len(dates) - 1):
            d1, d2 = dates[i], dates[i + 1]
            for emp in self.problem.employees:
                shift1 = None
                shift2 = None

                for shift in self.problem.shifts:
                    if emp.id in solution.assignments.get((d1, shift.id), []):
                        shift1 = shift
                    if emp.id in solution.assignments.get((d2, shift.id), []):
                        shift2 = shift

                if shift1 and shift2 and self._violates_rest_period(shift1, shift2, d1):
                    violations.append((emp.id, d1, d2, shift1, shift2))

        return violations

    def _try_move_to_different_shift(self, solution: Solution, emp_id: int, date: date, current_shift) -> bool:
        """Try to move employee to a different shift on the same day to fix rest period violation."""
        emp = self.problem.emp_by_id[emp_id]
        
        # Find other shifts on the same day
        for shift in self.problem.shifts:
            if shift.id == current_shift.id:
                continue
                
            assigned = solution.assignments.get((date, shift.id), [])
            
            # Check if we can add to this shift
            if (emp_id not in assigned and 
                len(assigned) < shift.max_staff and
                date not in emp.absence_dates):
                
                # Check weekly hours
                week_key = date.isocalendar()[:2]
                weekly_hours = self._get_employee_weekly_hours(solution, emp_id, week_key)
                if weekly_hours + shift.duration <= emp.max_hours_per_week:
                    
                    # Check rest period violations for the new assignment
                    if not self._check_rest_period_violation_for_employee(solution, emp_id, date, shift):
                        # Remove from current shift and add to new shift
                        if emp_id in solution.assignments.get((date, current_shift.id), []):
                            solution.assignments[(date, current_shift.id)].remove(emp_id)
                        assigned.append(emp_id)
                        return True
        
        return False

    def _try_swap_employee_for_rest_period(self, solution: Solution, emp_id: int, date1: date, date2: date, shift1, shift2) -> bool:
        """Try to swap the violating employee with another employee who doesn't have rest period issues."""
        emp = self.problem.emp_by_id[emp_id]
        
        # Find other employees who could work these shifts without rest period violations
        for other_emp in self.problem.employees:
            if other_emp.id == emp_id:
                continue
                
            # Check if other employee is available on both dates
            if (date1 in other_emp.absence_dates or date2 in other_emp.absence_dates):
                continue
                
            # Check if other employee is already assigned to these shifts
            other_in_shift1 = other_emp.id in solution.assignments.get((date1, shift1.id), [])
            other_in_shift2 = other_emp.id in solution.assignments.get((date2, shift2.id), [])
            
            # Check if other employee is available (not assigned to other shifts on these dates)
            other_available_date1 = not any(
                other_emp.id in solution.assignments.get((date1, s.id), [])
                for s in self.problem.shifts
            )
            other_available_date2 = not any(
                other_emp.id in solution.assignments.get((date2, s.id), [])
                for s in self.problem.shifts
            )
            
            # Check if other employee would have rest period violations
            other_has_violation = False
            if other_in_shift1 and other_in_shift2:
                other_has_violation = self._violates_rest_period(shift1, shift2, date1)
            
            # If other employee is available and doesn't have violations, try the swap
            if (other_available_date1 and other_available_date2 and not other_has_violation):
                # Check weekly hours for both employees
                week_key1 = date1.isocalendar()[:2]
                week_key2 = date2.isocalendar()[:2]
                
                other_weekly1 = self._get_employee_weekly_hours(solution, other_emp.id, week_key1)
                other_weekly2 = self._get_employee_weekly_hours(solution, other_emp.id, week_key2)
                emp_weekly1 = self._get_employee_weekly_hours(solution, emp_id, week_key1)
                emp_weekly2 = self._get_employee_weekly_hours(solution, emp_id, week_key2)
                
                # Check if swap is feasible
                if (other_weekly1 + shift1.duration <= other_emp.max_hours_per_week and
                    other_weekly2 + shift2.duration <= other_emp.max_hours_per_week and
                    emp_weekly1 + shift1.duration <= emp.max_hours_per_week and
                    emp_weekly2 + shift2.duration <= emp.max_hours_per_week):
                    
                    # Perform the swap
                    # Remove both employees from their current assignments
                    if emp_id in solution.assignments.get((date1, shift1.id), []):
                        solution.assignments[(date1, shift1.id)].remove(emp_id)
                    if emp_id in solution.assignments.get((date2, shift2.id), []):
                        solution.assignments[(date2, shift2.id)].remove(emp_id)
                    
                    # Add other employee to the shifts
                    solution.assignments[(date1, shift1.id)].append(other_emp.id)
                    solution.assignments[(date2, shift2.id)].append(other_emp.id)
                    
                    return True
        
        return False

    def _get_employee_weekly_hours(self, solution: Solution, emp_id: int, week_key: tuple) -> float:
        """Get total hours for employee in a specific week."""
        hours = 0.0
        for date in self.weeks.get(week_key, []):
            for shift in self.problem.shifts:
                if emp_id in solution.assignments.get((date, shift.id), []):
                    hours += shift.duration
        return hours

    def _check_rest_period_violation_for_employee(self, solution: Solution, emp_id: int, date: date, shift) -> bool:
        """Check if adding employee to shift on date would cause rest period violations."""
        kpi_calculator = KPICalculator(self.company)
        
        # Check previous day
        prev_date = date - timedelta(days=1)
        for s in self.problem.shifts:
            if emp_id in solution.assignments.get((prev_date, s.id), []):
                if kpi_calculator.violates_rest_period(s, shift, prev_date):
                    return True
        
        # Check next day
        next_date = date + timedelta(days=1)
        for s in self.problem.shifts:
            if emp_id in solution.assignments.get((next_date, s.id), []):
                if kpi_calculator.violates_rest_period(shift, s, date):
                    return True
        
        return False

    def _greedy_fill_gaps(self, solution: Solution):
        """Final greedy pass - FIXED to respect max_staff and rest period violations."""
        improvements = 0
        kpi_calculator = KPICalculator(self.company)

        for (date, shift_id), assigned in solution.assignments.items():
            if date not in self.working_days:
                continue

            shift = self.problem.shift_by_id[shift_id]
            current_count = len(assigned)

            # Skip if already at max
            if current_count >= shift.max_staff:
                continue

            gap = shift.max_staff - current_count
            week_key = date.isocalendar()[:2]

            # Find eligible employees
            candidates = []
            for emp in self.problem.employees:
                if (emp.id not in assigned and
                    date not in emp.absence_dates):

                    has_shift = any(
                        emp.id in solution.assignments.get((date, s.id), [])
                        for s in self.problem.shifts
                    )

                    if not has_shift:
                        weekly_hours = self._get_employee_weekly_hours(solution, emp.id, week_key)
                        if weekly_hours + shift.duration <= emp.max_hours_per_week:
                            worked = sum(
                                s.duration for (d, sid), emps in solution.assignments.items()
                                if emp.id in emps for s in [self.problem.shift_by_id[sid]]
                            )
                            capacity = self.employee_capacity[emp.id]
                            utilization = worked / capacity if capacity > 0 else 1

                            # --- REST PERIOD CHECKS ---
                            prev_date = date - timedelta(days=1)
                            next_date = date + timedelta(days=1)
                            prev_shift = None
                            next_shift = None
                            # Find previous day's shift (if any)
                            for s in self.problem.shifts:
                                if emp.id in solution.assignments.get((prev_date, s.id), []):
                                    prev_shift = s
                                    break
                            # Find next day's shift (if any)
                            for s in self.problem.shifts:
                                if emp.id in solution.assignments.get((next_date, s.id), []):
                                    next_shift = s
                                    break
                            rest_ok = True
                            if prev_shift:
                                if kpi_calculator.violates_rest_period(prev_shift, shift, prev_date):
                                    rest_ok = False
                            if next_shift:
                                if kpi_calculator.violates_rest_period(shift, next_shift, date):
                                    rest_ok = False
                            if rest_ok and utilization < 0.95:
                                candidates.append((emp.id, utilization))

            if candidates:
                # Sort by utilization
                candidates.sort(key=lambda x: x[1])

                # Add up to gap
                for emp_id, _ in candidates[:gap]:
                    # Final safety check
                    if len(assigned) < shift.max_staff:
                        assigned.append(emp_id)
                        improvements += 1

        if improvements > 0:
            print(f"[SA] Greedy fill added {improvements} assignments")

    def _final_rest_period_cleanup(self, solution: Solution):
        """Final cleanup to remove any remaining rest period violations."""
        violations = self._find_rest_period_violations(solution)
        
        if not violations:
            return
            
        print(f"[SA] Final cleanup: found {len(violations)} rest period violations")
        
        # Try to fix violations by removing employees from one of the violating shifts
        for emp_id, date1, date2, shift1, shift2 in violations:
            # Remove from the shift that would cause less understaffing
            count1 = len(solution.assignments.get((date1, shift1.id), []))
            count2 = len(solution.assignments.get((date2, shift2.id), []))
            
            if count1 > shift1.min_staff and count2 > shift2.min_staff:
                # Both shifts are above minimum, remove from the one with more staff
                if count1 >= count2:
                    if emp_id in solution.assignments.get((date1, shift1.id), []):
                        solution.assignments[(date1, shift1.id)].remove(emp_id)
                else:
                    if emp_id in solution.assignments.get((date2, shift2.id), []):
                        solution.assignments[(date2, shift2.id)].remove(emp_id)
            elif count1 > shift1.min_staff:
                # Only first shift is above minimum
                if emp_id in solution.assignments.get((date1, shift1.id), []):
                    solution.assignments[(date1, shift1.id)].remove(emp_id)
            elif count2 > shift2.min_staff:
                # Only second shift is above minimum
                if emp_id in solution.assignments.get((date2, shift2.id), []):
                    solution.assignments[(date2, shift2.id)].remove(emp_id)
            else:
                # Both shifts are at minimum, remove from the one with more staff
                if count1 >= count2:
                    if emp_id in solution.assignments.get((date1, shift1.id), []):
                        solution.assignments[(date1, shift1.id)].remove(emp_id)
                else:
                    if emp_id in solution.assignments.get((date2, shift2.id), []):
                        solution.assignments[(date2, shift2.id)].remove(emp_id)

    def _balance_shift_distribution(self, solution: Solution):
        """Balance employee distribution across shifts to improve coverage."""
        # Calculate current shift averages
        shift_totals = defaultdict(int)
        shift_counts = defaultdict(int)
        
        for current in self.working_days:
            for shift in self.problem.shifts:
                assigned = solution.assignments.get((current, shift.id), [])
                shift_totals[shift.id] += len(assigned)
                shift_counts[shift.id] += 1
        
        # Calculate average staffing per shift
        shift_averages = {}
        for shift_id in shift_totals:
            if shift_counts[shift_id] > 0:
                shift_averages[shift_id] = shift_totals[shift_id] / shift_counts[shift_id]
        
        if not shift_averages:
            return
        
        # Find overstaffed and understaffed shifts
        avg_staffing = sum(shift_averages.values()) / len(shift_averages)
        overstaffed_shifts = []
        understaffed_shifts = []
        
        for shift in self.problem.shifts:
            current_avg = shift_averages.get(shift.id, 0)
            if current_avg > avg_staffing + 0.5:  # Overstaffed
                overstaffed_shifts.append((shift.id, current_avg - avg_staffing))
            elif current_avg < avg_staffing - 0.5:  # Understaffed
                understaffed_shifts.append((shift.id, avg_staffing - current_avg))
        
        # Sort by imbalance severity (most imbalanced first)
        overstaffed_shifts.sort(key=lambda x: x[1], reverse=True)
        understaffed_shifts.sort(key=lambda x: x[1], reverse=True)
        
        # Try to move employees from overstaffed to understaffed shifts (more aggressive)
        transfers_made = 0
        max_transfers = 3  # Allow multiple transfers per iteration
        
        for over_shift_id, over_amount in overstaffed_shifts[:3]:  # Top 3 overstaffed
            for under_shift_id, under_amount in understaffed_shifts[:3]:  # Top 3 understaffed
                if over_shift_id == under_shift_id or transfers_made >= max_transfers:
                    continue
                
                # Find days where we can make transfers
                for current in self.working_days:
                    if transfers_made >= max_transfers:
                        break
                        
                    over_assigned = solution.assignments.get((current, over_shift_id), [])
                    under_assigned = solution.assignments.get((current, under_shift_id), [])
                    
                    if len(over_assigned) > 0 and len(under_assigned) < self.problem.shift_by_id[under_shift_id].max_staff:
                        # Try to move employees (more aggressive)
                        for emp_id in over_assigned[:]:  # Copy list to avoid modification during iteration
                            emp = self.problem.emp_by_id[emp_id]
                            
                            # Check if employee can work the understaffed shift
                            if (current not in emp.absence_dates and
                                emp_id not in under_assigned):
                                
                                # Check rest period constraints
                                if not self._check_rest_period_violation_for_employee(solution, emp_id, current, self.problem.shift_by_id[under_shift_id]):
                                    
                                    # Check weekly hours
                                    week_key = current.isocalendar()[:2]
                                    weekly_hours = self._get_employee_weekly_hours(solution, emp_id, week_key)
                                    new_shift = self.problem.shift_by_id[under_shift_id]
                                    
                                    if weekly_hours + new_shift.duration <= emp.max_hours_per_week:
                                        # Make the transfer
                                        over_assigned.remove(emp_id)
                                        under_assigned.append(emp_id)
                                        transfers_made += 1

                                        if transfers_made >= max_transfers:
                                            return  # Stop after max transfers

    def _aggressive_balance_shifts(self, solution: Solution):
        """Aggressive shift balancing that targets the most imbalanced shifts."""
        # Calculate current staffing levels for each shift
        shift_staffing = defaultdict(list)
        
        for current in self.working_days:
            for shift in self.problem.shifts:
                assigned = len(solution.assignments.get((current, shift.id), []))
                shift_staffing[shift.id].append(assigned)
        
        # Calculate average staffing and identify most imbalanced shifts
        shift_averages = {}
        for shift_id, staffing_list in shift_staffing.items():
            shift_averages[shift_id] = sum(staffing_list) / len(staffing_list)
        
        # Find the most overstaffed and understaffed shifts
        target_staffing = {}
        for shift in self.problem.shifts:
            current_avg = shift_averages.get(shift.id, 0)
            target_staffing[shift.id] = shift.max_staff  # Target max_staff for all shifts
        
        # Sort shifts by how far they are from target
        shift_deviations = []
        for shift in self.problem.shifts:
            current_avg = shift_averages.get(shift.id, 0)
            target = target_staffing[shift.id]
            deviation = abs(current_avg - target)
            shift_deviations.append((shift.id, current_avg, target, deviation))
        
        # Sort by deviation (most imbalanced first)
        shift_deviations.sort(key=lambda x: x[3], reverse=True)
        
        # Focus on the most imbalanced shifts
        for shift_id, current_avg, target, deviation in shift_deviations[:2]:  # Top 2 most imbalanced
            shift = self.problem.shift_by_id[shift_id]
            
            if current_avg > target:  # Overstaffed
                # Try to move employees away from this shift
                for current in self.working_days:
                    assigned = solution.assignments.get((current, shift_id), [])
                    if len(assigned) > target:
                        # Find another shift that needs staff
                        for other_shift in self.problem.shifts:
                            if other_shift.id == shift_id:
                                continue
                            other_assigned = solution.assignments.get((current, other_shift.id), [])
                            if len(other_assigned) < other_shift.max_staff:
                                # Try to move an employee
                                for emp_id in assigned[:]:
                                    emp = self.problem.emp_by_id[emp_id]
                                    if (current not in emp.absence_dates and
                                        emp_id not in other_assigned):
                                        if not self._check_rest_period_violation_for_employee(solution, emp_id, current, other_shift):
                                            week_key = current.isocalendar()[:2]
                                            weekly_hours = self._get_employee_weekly_hours(solution, emp_id, week_key)
                                            if weekly_hours + other_shift.duration <= emp.max_hours_per_week:
                                                assigned.remove(emp_id)
                                                other_assigned.append(emp_id)
                                                return  # One transfer is enough
            
            elif current_avg < target:  # Understaffed
                # Try to move employees to this shift
                for current in self.working_days:
                    assigned = solution.assignments.get((current, shift_id), [])
                    if len(assigned) < target:
                        # Find another shift that has excess staff
                        for other_shift in self.problem.shifts:
                            if other_shift.id == shift_id:
                                continue
                            other_assigned = solution.assignments.get((current, other_shift.id), [])
                            if len(other_assigned) > other_shift.max_staff * 0.8:  # Has excess staff
                                # Try to move an employee
                                for emp_id in other_assigned[:]:
                                    emp = self.problem.emp_by_id[emp_id]
                                    if (current not in emp.absence_dates and
                                        emp_id not in assigned):
                                        if not self._check_rest_period_violation_for_employee(solution, emp_id, current, shift):
                                            week_key = current.isocalendar()[:2]
                                            weekly_hours = self._get_employee_weekly_hours(solution, emp_id, week_key)
                                            if weekly_hours + shift.duration <= emp.max_hours_per_week:
                                                other_assigned.remove(emp_id)
                                                assigned.append(emp_id)
                                                return  # One transfer is enough

    def _prevent_rest_period_violations(self, solution: Solution):
        """Proactively prevent rest period violations by checking and adjusting assignments."""
        # Find employees who have consecutive day assignments
        for emp in self.problem.employees:
            for i in range(len(self.working_days) - 1):
                date1 = self.working_days[i]
                date2 = self.working_days[i + 1]
                
                # Check if employee is assigned to both days
                shift1 = None
                shift2 = None
                
                for shift in self.problem.shifts:
                    if emp.id in solution.assignments.get((date1, shift.id), []):
                        shift1 = shift
                    if emp.id in solution.assignments.get((date2, shift.id), []):
                        shift2 = shift
                
                # If employee has shifts on consecutive days, check for rest period violations
                if shift1 and shift2 and self._violates_rest_period(shift1, shift2, date1):
                    # Try to fix this violation proactively
                    if self._try_move_to_different_shift(solution, emp.id, date1, shift1):
                        return  # Fixed one violation
                    if self._try_move_to_different_shift(solution, emp.id, date2, shift2):
                        return  # Fixed one violation
                    
                    # If can't move, remove from the shift with more staff
                    shift1_count = len(solution.assignments.get((date1, shift1.id), []))
                    shift2_count = len(solution.assignments.get((date2, shift2.id), []))
                    
                    if shift1_count > shift2_count:
                        if emp.id in solution.assignments.get((date1, shift1.id), []):
                            solution.assignments[(date1, shift1.id)].remove(emp.id)
                            return
                    else:
                        if emp.id in solution.assignments.get((date2, shift2.id), []):
                            solution.assignments[(date2, shift2.id)].remove(emp.id)
                            return

    def _update_temperature(self, iteration: int, current_temp: float) -> float:
        """Update temperature with adaptive cooling."""
        progress = iteration / self.max_iterations

        if self.cooling_schedule == CoolingSchedule.EXPONENTIAL:
            base_temp = self.initial_temp * (self.final_temp / self.initial_temp) ** progress
            # Adaptive factor
            if progress < 0.3:
                return base_temp
            elif progress < 0.7:
                return base_temp * 0.7
            else:
                return base_temp * 0.3

        elif self.cooling_schedule == CoolingSchedule.LINEAR:
            return self.initial_temp - (self.initial_temp - self.final_temp) * progress
        elif self.cooling_schedule == CoolingSchedule.LOGARITHMIC:
            return self.initial_temp / (1 + iteration * 0.1)
        else:
            return current_temp