import random
import math
from typing import List, Tuple, Dict
from datetime import timedelta, datetime
from enum import Enum
from collections import defaultdict

from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry, Solution
from .utils import (
    get_weeks, is_employee_available, evaluate_solution,
    create_empty_solution,
)

from rostering_app.utils import (is_non_working_day, get_working_days_in_range)
from rostering_app.calculations import calculate_utilization_percentage


class CoolingSchedule(Enum):
    """Types of cooling schedules."""
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    LOGARITHMIC = "logarithmic"


class SimulatedAnnealingScheduler(SchedulingAlgorithm):
    """ SA with focus on high coverage and utilization."""

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

        # Validate solution doesn't exceed max_staff
        self._validate_and_fix_overstaffing(best_solution)

        return best_solution.to_entries()

    def _calculate_employee_capacities(self):
        """Calculate actual capacity for each employee over the schedule period."""
        self.employee_capacity = {}

        for emp in self.problem.employees:
            working_days = 0
            for work_date in self.working_days:
                if work_date not in emp.absence_dates:
                    working_days += 1

            days_per_week = 6 if self.sundays_off else 7
            daily_hours = emp.max_hours_per_week / days_per_week
            self.employee_capacity[emp.id] = working_days * daily_hours

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

        # Assign employees
        for date in self.working_days:
            week_key = date.isocalendar()[:2]

            # Sort shifts by duration (longer first)
            sorted_shifts = sorted(self.problem.shifts, key=lambda s: s.duration, reverse=True)

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
                        remaining_capacity = emp.max_hours_per_week - current_weekly
                        preference_bonus = 10 if shift.name in emp.preferred_shifts else 0
                        score = remaining_capacity + preference_bonus
                        candidates.append((eid, score))

                # Sort by score
                candidates.sort(key=lambda x: x[1], reverse=True)

                # Assign up to max_staff (FIXED: ensure we don't exceed)
                target = min(
                    shift.max_staff,  # Never exceed max_staff
                    max(shift.min_staff, int(shift.max_staff * 0.9)),  # Aim for 90% but respect max
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
        """Evaluation function."""
        penalty = 0

        # Weights
        w_understaff = 10_000_000
        w_overstaff = 1_000_000
        w_weekly_hours = 100_000
        w_rest_period = 100_000
        w_coverage_bonus = -1_000
        w_full_coverage = -5_000
        w_utilization = -2_000
        w_preference = -100

        # Track metrics
        total_positions = 0
        filled_positions = 0
        shifts_at_max = 0

        # 1. Staffing constraints
        for current in self.working_days:
            for shift in self.problem.shifts:
                assigned = solution.assignments.get((current, shift.id), [])
                count = len(assigned)

                total_positions += shift.max_staff
                filled_positions += min(count, shift.max_staff)

                if count < shift.min_staff:
                    penalty += (shift.min_staff - count) * w_understaff
                elif count > shift.max_staff:
                    penalty += (count - shift.max_staff) * w_overstaff
                else:
                    penalty += count * w_coverage_bonus
                    if count == shift.max_staff:
                        penalty += w_full_coverage
                        shifts_at_max += 1

        # 2. One shift per day
        self._check_one_shift_per_day(solution, penalty, w_overstaff)

        # 3. Weekly hours
        self._check_weekly_hours(solution, penalty, w_weekly_hours)

        # 4. Rest periods
        self._check_rest_periods(solution, penalty, w_rest_period)

        # 5. Utilization
        emp_hours = self._calculate_employee_hours(solution)
        for emp in self.problem.employees:
            worked_hours = emp_hours.get(emp.id, 0)
            capacity = self.employee_capacity[emp.id]

            if capacity > 0:
                utilization = worked_hours / capacity
                if 0.85 <= utilization <= 0.95:
                    penalty += w_utilization * utilization
                elif utilization > 0.95:
                    penalty += (utilization - 0.95) * 1000
                else:
                    penalty += (0.85 - utilization) * abs(w_utilization) * 2

        # 6. Preferences
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

    def _check_weekly_hours(self, solution: Solution, penalty: float, weight: float) -> float:
        """Check weekly hours constraints."""
        violations = 0.0
        for emp in self.problem.employees:
            for week_key, week_dates in self.weeks.items():
                weekly_hours = 0.0
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
            utilization = calculate_utilization_percentage(worked, capacity)
            if capacity > 0:
                total_utilization += utilization / 100.0
                count += 1
        return total_utilization / count if count > 0 else 0

    def _get_coverage_focused_neighbor(self, solution: Solution) -> Solution:
        """Generate neighbor with focus on improving coverage."""
        neighbor = solution.copy()

        # Operations with weights
        operations = [
            'fill_gaps',
            'maximize_shift',
            'redistribute',
            'swap_for_coverage',
            'utilization_boost'
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

        # Move from overstaffed
        source_key = random.choice(overstaffed)
        source_date, source_shift_id = source_key
        source_assigned = solution.assignments[source_key]
        source_shift = self.problem.shift_by_id[source_shift_id]

        # Remove excess employees first
        while len(source_assigned) > source_shift.max_staff:
            source_assigned.pop()

        # Now try to redistribute if still have employees
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
                            assigned.append(emp_id)
                            additions += 1

                            if additions >= max_additions:
                                return

    def _get_employee_weekly_hours(self, solution: Solution, emp_id: int, week_key: tuple) -> float:
        """Get total hours for employee in a specific week."""
        hours = 0.0
        for date in self.weeks.get(week_key, []):
            for shift in self.problem.shifts:
                if emp_id in solution.assignments.get((date, shift.id), []):
                    hours += shift.duration
        return hours

    def _greedy_fill_gaps(self, solution: Solution):
        """Final greedy pass - FIXED to respect max_staff."""
        improvements = 0

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

                            if utilization < 0.95:
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

    def _validate_and_fix_overstaffing(self, solution: Solution):
        """Final validation to ensure no shift exceeds max_staff."""
        fixes = 0

        for (date, shift_id), assigned in solution.assignments.items():
            shift = self.problem.shift_by_id[shift_id]

            # Remove excess employees
            while len(assigned) > shift.max_staff:
                # Remove employee with highest utilization (they likely have other shifts)
                emp_hours = self._calculate_employee_hours(solution)

                # Find employee with highest hours among assigned
                max_hours = -1
                remove_emp = None
                for emp_id in assigned:
                    hours = emp_hours.get(emp_id, 0)
                    if hours > max_hours:
                        max_hours = hours
                        remove_emp = emp_id

                if remove_emp:
                    assigned.remove(remove_emp)
                    fixes += 1
                else:
                    # Fallback: remove random
                    assigned.pop()
                    fixes += 1

        if fixes > 0:
            print(f"[SA] Fixed {fixes} overstaffing violations")

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