"""Improved simulated annealing scheduler with aggressive coverage."""
import random
import math
from typing import List, Tuple
from datetime import timedelta, datetime
from enum import Enum
from collections import defaultdict

from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry, Solution
from .utils import (
    get_weeks, is_employee_available, evaluate_solution,
    create_empty_solution,
)

from rostering_app.utils import ( is_non_working_day, get_working_days_in_range)


class CoolingSchedule(Enum):
    """Types of cooling schedules."""
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    LOGARITHMIC = "logarithmic"


class SimulatedAnnealingScheduler(SchedulingAlgorithm):
    """Improved SA with focus on high coverage and utilization."""

    def __init__(self, initial_temp=1000, final_temp=1, max_iterations=2000,
                 cooling_schedule=CoolingSchedule.EXPONENTIAL, sundays_off=False):
        self.initial_temp = initial_temp
        self.final_temp = final_temp
        self.max_iterations = max_iterations
        self.cooling_schedule = cooling_schedule
        self.sundays_off = sundays_off
        self.holidays = set()

    @property
    def name(self) -> str:
        return "Simulated Annealing"

    def _get_holidays_for_year(self, year: int) -> set:
        """Get German national holidays for a specific year as date tuples."""
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
            return set()

    def _is_non_working_day(self, date) -> bool:
        """Check if a date is a non-working day (holiday or Sunday)."""
        if (date.year, date.month, date.day) in self.holidays:
            return True
        if date.weekday() == 6 and self.sundays_off:
            return True
        return False

    def _violates_rest_period(self, shift1, shift2, date1) -> bool:
        """Check if two consecutive shifts violate 11-hour rest period."""
        end1 = datetime.combine(date1, shift1.end)
        if shift1.end < shift1.start:
            end1 += timedelta(days=1)
        start2 = datetime.combine(date1 + timedelta(days=1), shift2.start)
        pause = (start2 - end1).total_seconds() / 3600
        return pause < 11

    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:
        """Solve using improved simulated annealing."""
        self.problem = problem
        self.company = problem.company  # Set company from problem
        self.weeks = get_weeks(problem.start_date, problem.end_date)

        # Get working days using utils
        self.working_days = get_working_days_in_range(
            problem.start_date, problem.end_date, self.company
        )
        self.total_days = (problem.end_date - problem.start_date).days + 1

        print(f"[SA] Schedule period: {problem.start_date} to {problem.end_date}")
        print(f"[SA] Total days: {self.total_days}, Working days: {len(self.working_days)}")

        # Calculate employee capacities for the actual period
        self._calculate_employee_capacities()

        # Create aggressive initial solution
        current_solution = self._create_aggressive_initial_solution()
        current_cost = self._evaluate_aggressive(current_solution)
        current_solution.cost = current_cost

        best_solution = current_solution.copy()
        best_cost = current_cost

        # Initialize temperature
        temperature = self.initial_temp

        # Track improvement metrics
        no_improvement_count = 0
        last_best_cost = best_cost

        # Annealing process
        for iteration in range(self.max_iterations):
            # Get neighbor with bias toward coverage improvement
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
                else:
                    no_improvement_count += 1

            # Cool down
            temperature = self._update_temperature(iteration, temperature)

            # Early termination conditions
            if temperature < self.final_temp:
                break

            # If no improvement for many iterations, try restart
            if no_improvement_count > 200:
                current_solution = self._create_aggressive_initial_solution()
                current_cost = self._evaluate_aggressive(current_solution)
                no_improvement_count = 0
                temperature = self.initial_temp * 0.5  # Restart with lower temp

            # Print progress
            if iteration % 100 == 0:
                coverage_rate = self._calculate_coverage_rate(best_solution)
                utilization_rate = self._calculate_utilization_rate(best_solution)
                print(f"[SA] Iter {iteration}: Cost={best_cost:.0f}, Coverage={coverage_rate:.1%}, "
                      f"Utilization={utilization_rate:.1%}, Temp={temperature:.1f}")

        # Final optimization pass - greedy fill remaining capacity
        self._greedy_fill_gaps(best_solution)

        return best_solution.to_entries()

    def _calculate_employee_capacities(self):
        """Calculate actual capacity for each employee over the schedule period."""
        self.employee_capacity = {}

        for emp in self.problem.employees:
            # Get working days for this employee (excluding their absences)
            working_days = 0

            for work_date in self.working_days:
                if work_date not in emp.absence_dates:
                    working_days += 1

            # Calculate capacity based on actual working days
            # Assuming daily hours = max_hours_per_week / working_days_per_week
            days_per_week = 6 if self.sundays_off else 7
            daily_hours = emp.max_hours_per_week / days_per_week

            # Total capacity = working days * daily hours
            self.employee_capacity[emp.id] = working_days * daily_hours

    def _create_aggressive_initial_solution(self) -> Solution:
        """Create initial solution with very aggressive staffing (90-100% of max)."""
        solution = create_empty_solution(self.problem)

        # Pre-calculate daily availability using working days only
        daily_availability = {}
        for date in self.working_days:
            available = []
            for emp in self.problem.employees:
                if date not in emp.absence_dates:
                    available.append(emp.id)
            daily_availability[date] = available

        # Track weekly hours
        weekly_hours = {emp.id: {week_key: 0 for week_key in self.weeks.keys()}
                       for emp in self.problem.employees}

        # First pass: Fill shifts to 100% capacity where possible
        for date in self.working_days:
            week_key = date.isocalendar()[:2]

            # Sort shifts by duration (longer shifts first for better utilization)
            sorted_shifts = sorted(self.problem.shifts, key=lambda s: s.duration, reverse=True)

            for shift in sorted_shifts:
                key = (date, shift.id)

                # Get all candidates with capacity
                candidates = []
                for eid in daily_availability[date]:
                    emp = self.problem.emp_by_id[eid]
                    current_weekly = weekly_hours[eid][week_key]

                    # Check if employee is already assigned today
                    already_assigned = False
                    for other_shift in self.problem.shifts:
                        if eid in solution.assignments.get((date, other_shift.id), []):
                            already_assigned = True
                            break

                    if (not already_assigned and
                        current_weekly + shift.duration <= emp.max_hours_per_week):
                        # Score based on remaining capacity and preference
                        remaining_capacity = emp.max_hours_per_week - current_weekly
                        preference_bonus = 10 if shift.name in emp.preferred_shifts else 0
                        score = remaining_capacity + preference_bonus
                        candidates.append((eid, score))

                # Sort by score (higher is better)
                candidates.sort(key=lambda x: x[1], reverse=True)

                # Aggressively assign: aim for 95-100% of max_staff
                target = max(shift.min_staff, int(shift.max_staff * (0.95 + random.random() * 0.05)))
                assign_count = min(target, len(candidates))

                if assign_count > 0:
                    selected = [c[0] for c in candidates[:assign_count]]
                    solution.assignments[key] = selected

                    # Update weekly hours
                    for emp_id in selected:
                        weekly_hours[emp_id][week_key] += shift.duration
                else:
                    solution.assignments[key] = []

        return solution

    def _evaluate_aggressive(self, solution: Solution) -> float:
        """Aggressive evaluation function prioritizing coverage and utilization."""
        penalty = 0

        # Adjusted weights for aggressive coverage
        w_understaff = 10_000_000  # Extreme penalty for understaffing
        w_overstaff = 1_000_000    # High penalty for overstaffing
        w_weekly_hours = 100_000   # Penalty for exceeding weekly hours
        w_rest_period = 100_000    # Penalty for rest violations
        w_coverage_bonus = -1_000  # Strong bonus per staffed position
        w_full_coverage = -5_000   # Extra bonus for 100% coverage
        w_utilization = -2_000     # Strong bonus for high utilization
        w_preference = -100        # Bonus for preferences

        # Track metrics
        total_positions = 0
        filled_positions = 0
        shifts_at_max = 0
        total_shifts = 0

        # 1. Staffing constraints and coverage
        for current in self.working_days:
            for shift in self.problem.shifts:
                assigned = solution.assignments.get((current, shift.id), [])
                count = len(assigned)
                total_shifts += 1

                # Track positions
                total_positions += shift.max_staff
                filled_positions += min(count, shift.max_staff)

                if count < shift.min_staff:
                    # Severe penalty for understaffing
                    penalty += (shift.min_staff - count) * w_understaff
                elif count > shift.max_staff:
                    # Penalty for overstaffing
                    penalty += (count - shift.max_staff) * w_overstaff
                else:
                    # Bonus for each filled position
                    penalty += count * w_coverage_bonus

                    # Extra bonus for reaching max capacity
                    if count == shift.max_staff:
                        penalty += w_full_coverage
                        shifts_at_max += 1

        # 2. One shift per day constraint
        self._check_one_shift_per_day(solution, penalty, w_overstaff)

        # 3. Weekly hours constraints
        weekly_violations = self._check_weekly_hours(solution, penalty, w_weekly_hours)

        # 4. Rest period violations
        rest_violations = self._check_rest_periods(solution, penalty, w_rest_period)

        # 5. Employee utilization bonus
        emp_hours = self._calculate_employee_hours(solution)

        for emp in self.problem.employees:
            worked_hours = emp_hours.get(emp.id, 0)
            capacity = self.employee_capacity[emp.id]

            if capacity > 0:
                utilization = worked_hours / capacity

                # Strong bonus for 85-95% utilization
                if 0.85 <= utilization <= 0.95:
                    penalty += w_utilization * utilization
                elif utilization > 0.95:
                    # Small penalty for slight overutilization
                    penalty += (utilization - 0.95) * 1000
                else:
                    # Penalty for underutilization (scaled by how far below 85%)
                    penalty += (0.85 - utilization) * abs(w_utilization) * 2

        # 6. Preference bonus
        for (date, shift_id), emp_ids in solution.assignments.items():
            shift = self.problem.shift_by_id[shift_id]
            for emp_id in emp_ids:
                emp = self.problem.emp_by_id[emp_id]
                if shift.name in emp.preferred_shifts:
                    penalty += w_preference

        return penalty

    def _check_one_shift_per_day(self, solution: Solution, penalty: float, weight: float):
        """Check one shift per day constraint."""
        current = self.problem.start_date
        while current <= self.problem.end_date:
            emp_counts = defaultdict(int)
            for shift in self.problem.shifts:
                for emp_id in solution.assignments.get((current, shift.id), []):
                    emp_counts[emp_id] += 1

            for emp_id, count in emp_counts.items():
                if count > 1:
                    penalty += (count - 1) * weight

            current += timedelta(days=1)

    def _check_weekly_hours(self, solution: Solution, penalty: float, weight: float) -> int:
        """Check weekly hours constraints."""
        violations = 0
        for emp in self.problem.employees:
            for week_key, week_dates in self.weeks.items():
                weekly_hours = 0
                for date in week_dates:
                    for shift in self.problem.shifts:
                        if emp.id in solution.assignments.get((date, shift.id), []):
                            weekly_hours += shift.duration

                if weekly_hours > emp.max_hours_per_week:
                    violation = weekly_hours - emp.max_hours_per_week
                    penalty += violation * weight
                    violations += violation
        return violations

    def _check_rest_periods(self, solution: Solution, penalty: float, weight: float) -> int:
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
                    penalty += weight
                    violations += 1

        return violations

    def _calculate_employee_hours(self, solution: Solution) -> dict:
        """Calculate total hours worked by each employee."""
        emp_hours = defaultdict(float)
        for (date, shift_id), emp_ids in solution.assignments.items():
            shift = self.problem.shift_by_id[shift_id]
            for emp_id in emp_ids:
                emp_hours[emp_id] += shift.duration
        return emp_hours

    def _calculate_coverage_rate(self, solution: Solution) -> float:
        """Calculate overall coverage rate (filled/max positions)."""
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

            if capacity > 0:
                utilization = worked / capacity
                total_utilization += utilization
                count += 1

        return total_utilization / count if count > 0 else 0

    def _get_coverage_focused_neighbor(self, solution: Solution) -> Solution:
        """Generate neighbor with focus on improving coverage."""
        neighbor = solution.copy()

        # Weighted operations focusing on coverage improvement
        operations = [
            'fill_gaps',           # Fill understaffed shifts
            'maximize_shift',      # Bring shifts to max capacity
            'redistribute',        # Move from overstaffed to understaffed
            'swap_for_coverage',   # Swap to improve coverage
            'utilization_boost'    # Increase underutilized employees
        ]
        weights = [0.35, 0.25, 0.20, 0.10, 0.10]

        operation = random.choices(operations, weights=weights)[0]

        if operation == 'fill_gaps':
            self._fill_understaffed_shifts(neighbor)
        elif operation == 'maximize_shift':
            self._maximize_random_shift(neighbor)
        elif operation == 'redistribute':
            self._redistribute_staff(neighbor)
        elif operation == 'swap_for_coverage':
            self._swap_for_better_coverage(neighbor)
        elif operation == 'utilization_boost':
            self._boost_underutilized_employee(neighbor)

        return neighbor

    def _fill_understaffed_shifts(self, solution: Solution):
        """Focus on filling shifts that are below capacity."""
        # Find all understaffed shifts
        understaffed = []

        for (date, shift_id), assigned in solution.assignments.items():
            if date in self.working_days:
                shift = self.problem.shift_by_id[shift_id]
                if len(assigned) < shift.max_staff:
                    gap = shift.max_staff - len(assigned)
                    understaffed.append(((date, shift_id), gap))

        if not understaffed:
            return

        # Sort by gap size (bigger gaps first)
        understaffed.sort(key=lambda x: x[1], reverse=True)

        # Try to fill the most understaffed shift
        (date, shift_id), gap = understaffed[0]
        shift = self.problem.shift_by_id[shift_id]
        assigned = solution.assignments[(date, shift_id)]

        # Find available employees
        week_key = date.isocalendar()[:2]
        candidates = []

        for emp in self.problem.employees:
            if (emp.id not in assigned and
                date not in emp.absence_dates):

                # Check no other shift that day
                has_shift = False
                for other_shift in self.problem.shifts:
                    if other_shift.id != shift_id:
                        if emp.id in solution.assignments.get((date, other_shift.id), []):
                            has_shift = True
                            break

                if not has_shift:
                    # Check weekly capacity
                    weekly_hours = self._get_employee_weekly_hours(solution, emp.id, week_key)
                    if weekly_hours + shift.duration <= emp.max_hours_per_week:
                        candidates.append(emp.id)

        # Add as many as possible
        if candidates:
            add_count = min(gap, len(candidates))
            selected = random.sample(candidates, add_count)
            assigned.extend(selected)

    def _maximize_random_shift(self, solution: Solution):
        """Pick a random shift and try to bring it to max capacity."""
        # Only consider shifts on working days
        working_keys = [(d, s) for (d, s) in solution.assignments.keys() if d in self.working_days]
        if not working_keys:
            return

        key = random.choice(working_keys)
        date, shift_id = key
        shift = self.problem.shift_by_id[shift_id]
        assigned = solution.assignments[key]

        if len(assigned) >= shift.max_staff:
            return

        # Try to fill to max
        week_key = date.isocalendar()[:2]
        candidates = []

        for emp in self.problem.employees:
            if (emp.id not in assigned and
                date not in emp.absence_dates):

                # Check constraints
                has_shift = any(
                    emp.id in solution.assignments.get((date, s.id), [])
                    for s in self.problem.shifts if s.id != shift_id
                )

                if not has_shift:
                    weekly_hours = self._get_employee_weekly_hours(solution, emp.id, week_key)
                    if weekly_hours + shift.duration <= emp.max_hours_per_week:
                        # Prefer employees with lower utilization
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
            need = shift.max_staff - len(assigned)
            selected = [c[0] for c in candidates[:need]]
            assigned.extend(selected)

    def _redistribute_staff(self, solution: Solution):
        """Move staff from overstaffed to understaffed shifts."""
        overstaffed = []
        understaffed = []

        for (date, shift_id), assigned in solution.assignments.items():
            shift = self.problem.shift_by_id[shift_id]
            if len(assigned) > shift.max_staff:
                overstaffed.append((date, shift_id))
            elif len(assigned) < shift.max_staff:
                understaffed.append((date, shift_id))

        if not overstaffed or not understaffed:
            return

        # Try to move someone
        source_key = random.choice(overstaffed)
        source_date, source_shift_id = source_key
        source_assigned = solution.assignments[source_key]

        if not source_assigned:
            return

        emp_id = random.choice(source_assigned)
        emp = self.problem.emp_by_id[emp_id]

        # Find compatible target
        random.shuffle(understaffed)
        for target_key in understaffed:
            target_date, target_shift_id = target_key
            target_shift = self.problem.shift_by_id[target_shift_id]

            # Check if same day (can just reassign)
            if target_date == source_date:
                target_assigned = solution.assignments[target_key]
                if emp_id not in target_assigned:
                    source_assigned.remove(emp_id)
                    target_assigned.append(emp_id)
                    return

    def _swap_for_better_coverage(self, solution: Solution):
        """Swap employees to improve overall coverage."""
        # Find a shift below max and one at/above min
        below_max = []
        at_min_or_above = []

        for (date, shift_id), assigned in solution.assignments.items():
            if date in self.working_days:
                shift = self.problem.shift_by_id[shift_id]
                if len(assigned) < shift.max_staff:
                    below_max.append((date, shift_id))
                if len(assigned) >= shift.min_staff:
                    at_min_or_above.append((date, shift_id))

        if not below_max or not at_min_or_above:
            return

        # Try swapping
        target_key = random.choice(below_max)
        source_key = random.choice(at_min_or_above)

        if target_key == source_key:
            return

        target_date, target_shift_id = target_key
        source_date, source_shift_id = source_key

        source_assigned = solution.assignments[source_key]
        target_assigned = solution.assignments[target_key]

        if not source_assigned:
            return

        # Find employee from source who can work target
        for emp_id in source_assigned:
            emp = self.problem.emp_by_id[emp_id]

            if (target_date not in emp.absence_dates and
                target_date in self.working_days and
                emp_id not in target_assigned):

                # Check constraints
                has_other_shift = any(
                    emp_id in solution.assignments.get((target_date, s.id), [])
                    for s in self.problem.shifts if s.id != target_shift_id
                )

                if not has_other_shift:
                    # Make the move
                    source_assigned.remove(emp_id)
                    target_assigned.append(emp_id)
                    return

    def _boost_underutilized_employee(self, solution: Solution):
        """Find underutilized employee and assign more shifts."""
        emp_hours = self._calculate_employee_hours(solution)

        # Find most underutilized employee
        underutilized = []
        for emp in self.problem.employees:
            worked = emp_hours.get(emp.id, 0)
            capacity = self.employee_capacity[emp.id]
            if capacity > 0:
                utilization = worked / capacity
                if utilization < 0.8:  # Below 80%
                    underutilized.append((emp.id, utilization))

        if not underutilized:
            return

        # Sort by utilization (lowest first)
        underutilized.sort(key=lambda x: x[1])
        emp_id, _ = underutilized[0]
        emp = self.problem.emp_by_id[emp_id]

        # Find shifts where this employee can be added
        additions = 0
        max_additions = 3  # Limit changes per operation

        for (date, shift_id), assigned in solution.assignments.items():
            if date in self.working_days:
                shift = self.problem.shift_by_id[shift_id]

                if (emp_id not in assigned and
                    len(assigned) < shift.max_staff and
                    date not in emp.absence_dates):

                    # Check constraints
                    has_shift = any(
                        emp_id in solution.assignments.get((date, s.id), [])
                        for s in self.problem.shifts
                    )

                    if not has_shift:
                        week_key = date.isocalendar()[:2]
                        weekly_hours = self._get_employee_weekly_hours(solution, emp_id, week_key)

                        if weekly_hours + shift.duration <= emp.max_hours_per_week:
                            assigned.append(emp_id)
                            additions += 1

                            if additions >= max_additions:
                                return

    def _get_employee_weekly_hours(self, solution: Solution, emp_id: str, week_key: Tuple) -> float:
        """Get total hours for employee in a specific week."""
        hours = 0
        for date in self.weeks.get(week_key, []):
            for shift in self.problem.shifts:
                if emp_id in solution.assignments.get((date, shift.id), []):
                    hours += shift.duration
        return hours

    def _greedy_fill_gaps(self, solution: Solution):
        """Final greedy pass to fill any remaining gaps."""
        improvements = 0

        for (date, shift_id), assigned in solution.assignments.items():
            shift = self.problem.shift_by_id[shift_id]

            if len(assigned) < shift.max_staff:
                week_key = date.isocalendar()[:2]

                # Find all eligible employees
                candidates = []
                for emp in self.problem.employees:
                    if (emp.id not in assigned and
                        date not in emp.absence_dates and
                        not self._is_non_working_day(date)):

                        # Check constraints
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

                                # Prioritize underutilized employees
                                if utilization < 0.95:
                                    candidates.append((emp.id, utilization))

                if candidates:
                    # Sort by utilization (lowest first)
                    candidates.sort(key=lambda x: x[1])
                    need = shift.max_staff - len(assigned)

                    for emp_id, _ in candidates[:need]:
                        assigned.append(emp_id)
                        improvements += 1

        if improvements > 0:
            print(f"[SA] Greedy fill added {improvements} assignments")

    def _update_temperature(self, iteration: int, current_temp: float) -> float:
        """Update temperature with adaptive cooling."""
        progress = iteration / self.max_iterations

        if self.cooling_schedule == CoolingSchedule.EXPONENTIAL:
            # Slower cooling for better exploration
            base_temp = self.initial_temp * (self.final_temp / self.initial_temp) ** progress
            # Adaptive factor based on progress
            if progress < 0.3:
                return base_temp  # Full exploration early
            elif progress < 0.7:
                return base_temp * 0.7  # Moderate cooling
            else:
                return base_temp * 0.3  # Aggressive cooling late

        elif self.cooling_schedule == CoolingSchedule.LINEAR:
            return self.initial_temp - (self.initial_temp - self.final_temp) * progress
        elif self.cooling_schedule == CoolingSchedule.LOGARITHMIC:
            return self.initial_temp / (1 + iteration * 0.1)
        else:
            return current_temp