"""Genetic algorithm based scheduling."""
import random
from typing import List, Tuple
from datetime import timedelta, datetime
from collections import defaultdict

from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry, Solution
from .utils import (
    get_weeks, is_employee_available, evaluate_solution,
    create_empty_solution, check_rest_period
)


class GeneticAlgorithmScheduler(SchedulingAlgorithm):
    """Scheduling using genetic algorithm."""

    def __init__(self, population_size=50, generations=100,
                 mutation_rate=0.2, crossover_rate=0.8, elitism_size=2,
                 sundays_off=False):
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elitism_size = elitism_size
        self.sundays_off = sundays_off
        self.holidays = set()

    @property
    def name(self) -> str:
        return "Genetic Algorithm"

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
        # Check holidays using tuple format
        if (date.year, date.month, date.day) in self.holidays:
            return True
        if date.weekday() == 6 and self.sundays_off:  # Sunday
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
        """Solve using genetic algorithm."""
        self.problem = problem
        self.weeks = get_weeks(problem.start_date, problem.end_date)

        # Populate holidays for the date range using tuple format
        self.holidays = set()
        for year in range(problem.start_date.year, problem.end_date.year + 1):
            self.holidays.update(self._get_holidays_for_year(year))

        # Scale down min_staff if demand exceeds capacity (like ILP)
        num_weeks = len(self.weeks)
        total_emp_hours = sum(emp.max_hours_per_week for emp in problem.employees) * num_weeks

        # Calculate total required hours
        total_days = (problem.end_date - problem.start_date).days + 1
        total_req_hours = sum(
            shift.min_staff * shift.duration * total_days
            for shift in problem.shifts
        )

        if total_req_hours > total_emp_hours:
            scale = total_emp_hours / total_req_hours
            for shift in problem.shifts:
                shift.min_staff = max(1, int(round(shift.min_staff * scale)))
            print(f"[GA] Scaled down min_staff by {scale:.2f}× to restore feasibility.")

        # Initialize population
        population = [self._create_random_solution() for _ in range(self.population_size)]

        # Evaluate initial population
        for solution in population:
            solution.cost = self._evaluate_comprehensive(solution)

        # Evolution
        for generation in range(self.generations):
            # Sort by fitness
            population.sort(key=lambda x: x.cost)

            # Elitism: keep best solutions
            new_population = population[:self.elitism_size].copy()

            # Generate new solutions
            while len(new_population) < self.population_size:
                if random.random() < self.crossover_rate:
                    # Crossover
                    parent1 = self._tournament_selection(population)
                    parent2 = self._tournament_selection(population)
                    child = self._crossover(parent1, parent2)
                else:
                    # Mutation
                    parent = self._tournament_selection(population)
                    child = self._mutate(parent.copy())

                child.cost = self._evaluate_comprehensive(child)
                new_population.append(child)

            population = new_population

            # Print progress
            if generation % 20 == 0:
                best_cost = population[0].cost
                print(f"[GA] Generation {generation}: Best cost = {best_cost:.2f}")

        # Final evaluation of best solution
        best_solution = population[0]
        best_solution.cost = evaluate_solution(best_solution, self.problem)
        return best_solution.to_entries()

    def _create_random_solution(self) -> Solution:
        """Create a random valid solution with better staffing."""
        solution = create_empty_solution(self.problem)

        # Build list of all dates
        dates = []
        current = self.problem.start_date
        while current <= self.problem.end_date:
            dates.append(current)
            current += timedelta(days=1)

        # Pre-calculate daily availability
        daily_availability = {}
        for date in dates:
            available = []
            for emp in self.problem.employees:
                # Check if employee is available (not absent, not holiday, not Sunday if sundays_off)
                if (date not in emp.absence_dates and
                    not self._is_non_working_day(date)):
                    available.append(emp.id)
            daily_availability[date] = available

        # Track weekly hours to respect limits
        weekly_hours = {emp.id: {week_key: 0 for week_key in self.weeks.keys()}
                       for emp in self.problem.employees}

        # Assign employees with aggressive staffing approach
        for date in dates:
            available = daily_availability[date].copy()
            random.shuffle(available)
            used_today = set()

            # Get week key for this date
            week_key = date.isocalendar()[:2]

            for shift in self.problem.shifts:
                key = (date, shift.id)
                # Get candidates who aren't already assigned today and have weekly capacity
                candidates = []
                for eid in available:
                    if eid not in used_today:
                        emp = self.problem.emp_by_id[eid]
                        current_weekly = weekly_hours[eid][week_key]
                        if current_weekly + shift.duration <= emp.max_hours_per_week:
                            candidates.append(eid)

                if candidates:
                    # Aggressive staffing: aim for 80-100% of max_staff
                    min_assign = min(shift.min_staff, len(candidates))
                    target_assign = min(
                        int(shift.max_staff * (0.8 + random.random() * 0.2)),  # 80-100% of max
                        len(candidates)
                    )
                    count = max(min_assign, target_assign)

                    if count > 0:
                        selected = random.sample(candidates, min(count, len(candidates)))
                        solution.assignments[key] = selected
                        used_today.update(selected)

                        # Update weekly hours tracking
                        for emp_id in selected:
                            weekly_hours[emp_id][week_key] += shift.duration
                else:
                    solution.assignments[key] = []

        return solution

    def _evaluate_comprehensive(self, solution: Solution) -> float:
        """Comprehensive fitness evaluation matching ILP logic."""
        penalty = 0

        # Weight configuration (adjusted for better coverage)
        w_understaff = 1_000_000
        w_overstaff = 100_000
        w_weekly_hours = 50_000
        w_rest_period = 50_000
        w_overtime = 50
        w_fairness = 20
        w_preference = -5
        w_coverage = -100  # Strong bonus for good coverage
        w_utilization = -50  # Bonus for employee utilization

        # 1. Check min/max staffing
        total_understaffing = 0
        total_overstaffing = 0
        total_coverage = 0
        total_possible_coverage = 0

        current = self.problem.start_date
        while current <= self.problem.end_date:
            for shift in self.problem.shifts:
                assigned = solution.assignments.get((current, shift.id), [])
                count = len(assigned)

                if count < shift.min_staff:
                    understaffing = shift.min_staff - count
                    penalty += understaffing * w_understaff
                    total_understaffing += understaffing
                elif count > shift.max_staff:
                    overstaffing = count - shift.max_staff
                    penalty += overstaffing * w_overstaff
                    total_overstaffing += overstaffing

                # Coverage bonus: reward assignments up to max_staff
                coverage = min(count, shift.max_staff)
                total_coverage += coverage
                total_possible_coverage += shift.max_staff
                penalty += coverage * w_coverage

            current += timedelta(days=1)

        # 2. Check one shift per day constraint
        current = self.problem.start_date
        while current <= self.problem.end_date:
            emp_counts = defaultdict(int)
            for shift in self.problem.shifts:
                for emp_id in solution.assignments.get((current, shift.id), []):
                    emp_counts[emp_id] += 1

            for emp_id, count in emp_counts.items():
                if count > 1:
                    penalty += (count - 1) * w_overstaff

            current += timedelta(days=1)

        # 3. Check weekly hours constraints
        weekly_violations = 0
        for emp in self.problem.employees:
            for week_key, week_dates in self.weeks.items():
                weekly_hours = 0
                for date in week_dates:
                    for shift in self.problem.shifts:
                        if emp.id in solution.assignments.get((date, shift.id), []):
                            weekly_hours += shift.duration

                if weekly_hours > emp.max_hours_per_week:
                    violation = weekly_hours - emp.max_hours_per_week
                    penalty += violation * w_weekly_hours
                    weekly_violations += violation

        # 4. Check rest period violations
        dates = []
        current = self.problem.start_date
        while current <= self.problem.end_date:
            dates.append(current)
            current += timedelta(days=1)

        rest_violations = 0
        for i in range(len(dates) - 1):
            d1, d2 = dates[i], dates[i + 1]
            for emp in self.problem.employees:
                # Find shifts assigned to this employee on consecutive days
                shift1 = None
                shift2 = None

                for shift in self.problem.shifts:
                    if emp.id in solution.assignments.get((d1, shift.id), []):
                        shift1 = shift
                    if emp.id in solution.assignments.get((d2, shift.id), []):
                        shift2 = shift

                if shift1 and shift2 and self._violates_rest_period(shift1, shift2, d1):
                    penalty += w_rest_period
                    rest_violations += 1

        # 5. Calculate fairness and utilization
        emp_hours = defaultdict(float)
        for (date, shift_id), emp_ids in solution.assignments.items():
            shift = self.problem.shift_by_id[shift_id]
            for emp_id in emp_ids:
                emp_hours[emp_id] += shift.duration

        if emp_hours:
            hours_list = list(emp_hours.values())
            avg_hours = sum(hours_list) / len(hours_list)

            # Fairness penalty
            for hours in hours_list:
                penalty += abs(hours - avg_hours) * w_fairness

            # Utilization bonus: reward employees working closer to their capacity
            total_utilization = 0
            for emp in self.problem.employees:
                worked_hours = emp_hours.get(emp.id, 0)
                # Calculate yearly capacity (simplified)
                yearly_capacity = emp.max_hours_per_week * 52
                utilization = worked_hours / yearly_capacity if yearly_capacity > 0 else 0

                # Bonus for utilization between 70-95%
                if 0.7 <= utilization <= 0.95:
                    penalty += utilization * w_utilization * 100
                elif utilization < 0.7:
                    # Penalty for underutilization
                    penalty += (0.7 - utilization) * 1000

                total_utilization += utilization

        # 6. Preference bonus
        preference_matches = 0
        for (date, shift_id), emp_ids in solution.assignments.items():
            shift = self.problem.shift_by_id[shift_id]
            for emp_id in emp_ids:
                emp = self.problem.emp_by_id[emp_id]
                if shift.name in emp.preferred_shifts:
                    penalty += w_preference
                    preference_matches += 1

        # 7. Monthly overtime penalty (simplified)
        overtime_penalty = 0
        for emp in self.problem.employees:
            monthly_hours = emp_hours.get(emp.id, 0)
            expected_monthly = emp.max_hours_per_week * 4.33
            if monthly_hours > expected_monthly:
                overtime = monthly_hours - expected_monthly
                penalty += overtime * w_overtime
                overtime_penalty += overtime

        return penalty

    def _tournament_selection(self, population: List[Solution], tournament_size: int = 3) -> Solution:
        """Tournament selection."""
        tournament = random.sample(population, min(tournament_size, len(population)))
        return min(tournament, key=lambda x: x.cost)

    def _crossover(self, parent1: Solution, parent2: Solution) -> Solution:
        """Date-based crossover preserving daily constraints."""
        child = Solution()

        # Get all dates
        dates = set()
        for (date, shift_id) in parent1.assignments.keys():
            dates.add(date)
        dates = sorted(list(dates))

        if not dates:
            return child

        # Choose crossover point by date
        crossover_date = random.choice(dates)

        # Copy assignments
        for (date, shift_id) in parent1.assignments.keys():
            if date <= crossover_date:
                # Use parent1
                child.assignments[(date, shift_id)] = parent1.assignments[(date, shift_id)].copy()
            else:
                # Use parent2
                child.assignments[(date, shift_id)] = parent2.assignments.get((date, shift_id), []).copy()

        return child

    def _mutate(self, solution: Solution) -> Solution:
        """Improved mutation with multiple operations."""
        mutation_ops = ['swap_employee', 'reassign_shift', 'adjust_staffing']

        for _ in range(random.randint(1, 3)):  # Multiple mutations
            operation = random.choice(mutation_ops)

            if operation == 'swap_employee':
                self._mutate_swap_employee(solution)
            elif operation == 'reassign_shift':
                self._mutate_reassign_shift(solution)
            elif operation == 'adjust_staffing':
                self._mutate_adjust_staffing(solution)

        return solution

    def _mutate_swap_employee(self, solution: Solution):
        """Swap employees between two shifts."""
        keys = list(solution.assignments.keys())
        if len(keys) < 2:
            return

        key1, key2 = random.sample(keys, 2)
        staff1 = solution.assignments[key1]
        staff2 = solution.assignments[key2]

        if staff1 and staff2:
            emp1 = random.choice(staff1)
            emp2 = random.choice(staff2)

            # Check if swap is valid
            date1, shift_id1 = key1
            date2, shift_id2 = key2

            emp1_obj = self.problem.emp_by_id[emp1]
            emp2_obj = self.problem.emp_by_id[emp2]

            # Validate swap
            if (date2 not in emp1_obj.absence_dates and
                date1 not in emp2_obj.absence_dates and
                not self._is_non_working_day(date1) and
                not self._is_non_working_day(date2)):

                staff1.remove(emp1)
                staff2.remove(emp2)
                staff1.append(emp2)
                staff2.append(emp1)

    def _mutate_reassign_shift(self, solution: Solution):
        """Reassign an employee to a different available shift."""
        keys = list(solution.assignments.keys())
        if not keys:
            return

        # Pick a random assignment
        date, shift_id = random.choice(keys)
        assigned = solution.assignments[(date, shift_id)]

        if assigned:
            emp_id = random.choice(assigned)
            emp = self.problem.emp_by_id[emp_id]

            # Remove from current shift
            assigned.remove(emp_id)

            # Try to assign to different shift on same day
            other_shifts = [s for s in self.problem.shifts if s.id != shift_id]
            random.shuffle(other_shifts)

            for other_shift in other_shifts:
                other_key = (date, other_shift.id)
                other_assigned = solution.assignments.get(other_key, [])

                if (len(other_assigned) < other_shift.max_staff and
                    emp_id not in other_assigned):
                    other_assigned.append(emp_id)
                    return

            # If no reassignment possible, put back
            assigned.append(emp_id)

    def _mutate_adjust_staffing(self, solution: Solution):
        """Add or remove employees from shifts."""
        keys = list(solution.assignments.keys())
        if not keys:
            return

        date, shift_id = random.choice(keys)
        shift = self.problem.shift_by_id[shift_id]
        assigned = solution.assignments[(date, shift_id)]

        if random.random() < 0.5 and len(assigned) < shift.max_staff:
            # Try to add employee
            available = [
                emp.id for emp in self.problem.employees
                if (emp.id not in assigned and
                    date not in emp.absence_dates and
                    not self._is_non_working_day(date))
            ]

            # Check if employee is not assigned to another shift on same day
            for other_shift in self.problem.shifts:
                if other_shift.id != shift_id:
                    other_assigned = solution.assignments.get((date, other_shift.id), [])
                    available = [eid for eid in available if eid not in other_assigned]

            if available:
                assigned.append(random.choice(available))

        elif len(assigned) > shift.min_staff:
            # Remove employee
            assigned.remove(random.choice(assigned))