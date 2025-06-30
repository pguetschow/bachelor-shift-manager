import random
from typing import List, Tuple
from datetime import timedelta, datetime
from collections import defaultdict

from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry, Solution
from .utils import (
    get_weeks, is_employee_available, evaluate_solution,
    create_empty_solution, check_rest_period
)
from rostering_app.calculations import calculate_utilization_percentage


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

        # Initialize population with better diversity
        population = []
        # Create 70% aggressive solutions, 30% conservative
        aggressive_count = int(self.population_size * 0.7)
        for i in range(self.population_size):
            if i < aggressive_count:
                solution = self._create_aggressive_random_solution()
            else:
                solution = self._create_conservative_random_solution()
            population.append(solution)

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
                    # Mutation - use adaptive mutation
                    parent = self._tournament_selection(population)
                    child = self._adaptive_mutate(parent.copy(), generation)

                child.cost = self._evaluate_comprehensive(child)
                new_population.append(child)

            population = new_population

            # Print progress
            if generation % 20 == 0:
                best_cost = population[0].cost
                coverage = self._calculate_coverage_rate(population[0])
                print(f"[GA] Generation {generation}: Best cost = {best_cost:.2f}, Coverage = {coverage:.1%}")

        # Final evaluation of best solution
        best_solution = population[0]

        # Apply final improvement pass
        self._final_improvement_pass(best_solution)

        best_solution.cost = evaluate_solution(best_solution, self.problem)
        return best_solution.to_entries()

    def _create_aggressive_random_solution(self) -> Solution:
        """Create a random solution with aggressive staffing (90-100% of max)."""
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
                if (date not in emp.absence_dates and
                    not self._is_non_working_day(date)):
                    available.append(emp.id)
            daily_availability[date] = available

        # Track weekly hours
        weekly_hours = defaultdict(lambda: defaultdict(float))

        # Assign employees with very aggressive staffing
        for date in dates:
            available = daily_availability[date].copy()

            # Get week key for this date
            week_key = date.isocalendar()[:2]

            # Sort shifts by duration (prioritize longer shifts for better utilization)
            sorted_shifts = sorted(self.problem.shifts, key=lambda s: s.duration, reverse=True)

            for shift in sorted_shifts:
                key = (date, shift.id)

                # Get candidates considering all constraints
                candidates = []
                for eid in available:
                    emp = self.problem.emp_by_id[eid]
                    current_weekly = weekly_hours[eid][week_key]

                    # Check if already assigned today
                    already_assigned = any(
                        eid in solution.assignments.get((date, s.id), [])
                        for s in self.problem.shifts
                    )

                    if (not already_assigned and
                        current_weekly + shift.duration <= emp.max_hours_per_week):
                        # Score based on utilization potential
                        remaining_weekly = emp.max_hours_per_week - current_weekly
                        preference_bonus = 20 if shift.name in emp.preferred_shifts else 0
                        score = remaining_weekly + preference_bonus
                        candidates.append((eid, score))

                if candidates:
                    # Sort by score (higher is better)
                    candidates.sort(key=lambda x: x[1], reverse=True)

                    # Very aggressive: aim for 90-100% of max_staff
                    target_percent = 0.9 + random.random() * 0.1
                    target_assign = max(
                        shift.min_staff,
                        min(int(shift.max_staff * target_percent), len(candidates))
                    )

                    selected = [c[0] for c in candidates[:target_assign]]
                    solution.assignments[key] = selected

                    # Update weekly hours
                    for emp_id in selected:
                        weekly_hours[emp_id][week_key] += shift.duration
                else:
                    solution.assignments[key] = []

        return solution

    def _create_conservative_random_solution(self) -> Solution:
        """Create a more conservative solution (70-85% of max)."""
        solution = create_empty_solution(self.problem)

        dates = []
        current = self.problem.start_date
        while current <= self.problem.end_date:
            dates.append(current)
            current += timedelta(days=1)

        # Similar to aggressive but with lower targets
        daily_availability = {}
        for date in dates:
            available = []
            for emp in self.problem.employees:
                if (date not in emp.absence_dates and
                    not self._is_non_working_day(date)):
                    available.append(emp.id)
            daily_availability[date] = available

        weekly_hours = defaultdict(lambda: defaultdict(float))

        for date in dates:
            available = daily_availability[date].copy()
            random.shuffle(available)
            week_key = date.isocalendar()[:2]

            for shift in self.problem.shifts:
                key = (date, shift.id)
                candidates = []

                for eid in available:
                    emp = self.problem.emp_by_id[eid]
                    current_weekly = weekly_hours[eid][week_key]

                    already_assigned = any(
                        eid in solution.assignments.get((date, s.id), [])
                        for s in self.problem.shifts
                    )

                    if (not already_assigned and
                        current_weekly + shift.duration <= emp.max_hours_per_week):
                        candidates.append(eid)

                if candidates:
                    # Conservative: 70-85% of max_staff
                    target_percent = 0.7 + random.random() * 0.15
                    target_assign = max(
                        shift.min_staff,
                        min(int(shift.max_staff * target_percent), len(candidates))
                    )

                    selected = random.sample(candidates, min(target_assign, len(candidates)))
                    solution.assignments[key] = selected

                    for emp_id in selected:
                        weekly_hours[emp_id][week_key] += shift.duration
                else:
                    solution.assignments[key] = []

        return solution

    def _evaluate_comprehensive(self, solution: Solution) -> float:
        """Comprehensive fitness evaluation with stronger coverage incentives."""
        penalty = 0

        # Adjusted weights for better coverage
        w_understaff = 10_000_000  # Extreme penalty for understaffing
        w_overstaff = 1_000_000    # High penalty for overstaffing
        w_weekly_hours = 100_000    # Penalty for exceeding weekly hours
        w_rest_period = 100_000     # Penalty for rest violations
        w_overtime = 100            # Small penalty for overtime
        w_fairness = 50             # Moderate fairness weight
        w_preference = -50          # Preference bonus
        w_coverage = -500           # Strong bonus per staffed position
        w_full_shift = -2000        # Extra bonus for fully staffed shifts
        w_utilization = -100        # Bonus for good utilization

        # Track metrics
        total_positions = 0
        filled_positions = 0
        fully_staffed_shifts = 0

        # 1. Check staffing levels
        current = self.problem.start_date
        while current <= self.problem.end_date:
            for shift in self.problem.shifts:
                assigned = solution.assignments.get((current, shift.id), [])
                count = len(assigned)

                # Count positions
                total_positions += shift.max_staff
                filled_positions += min(count, shift.max_staff)

                if count < shift.min_staff:
                    penalty += (shift.min_staff - count) * w_understaff
                elif count > shift.max_staff:
                    penalty += (count - shift.max_staff) * w_overstaff
                else:
                    # Coverage bonus
                    penalty += count * w_coverage

                    # Extra bonus for fully staffed shifts
                    if count == shift.max_staff:
                        penalty += w_full_shift
                        fully_staffed_shifts += 1

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
        for emp in self.problem.employees:
            for week_key, week_dates in self.weeks.items():
                weekly_hours = 0.0
                for date in week_dates:
                    for shift in self.problem.shifts:
                        if emp.id in solution.assignments.get((date, shift.id), []):
                            weekly_hours += shift.duration

                if weekly_hours > emp.max_hours_per_week:
                    violation = weekly_hours - emp.max_hours_per_week
                    penalty += violation * w_weekly_hours

        # 4. Check rest period violations
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
                    penalty += w_rest_period

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

            # Utilization bonus
            for emp in self.problem.employees:
                worked_hours = emp_hours.get(emp.id, 0)
                yearly_capacity = emp.max_hours_per_week * 52
                utilization = calculate_utilization_percentage(worked_hours, yearly_capacity) / 100.0

                # Bonus for good utilization (70-95%)
                if 0.7 <= utilization <= 0.95:
                    penalty += utilization * w_utilization
                elif utilization < 0.7:
                    # Penalty for underutilization
                    penalty += (0.7 - utilization) * 5000

        # 6. Preference bonus
        for (date, shift_id), emp_ids in solution.assignments.items():
            shift = self.problem.shift_by_id[shift_id]
            for emp_id in emp_ids:
                emp = self.problem.emp_by_id[emp_id]
                if shift.name in emp.preferred_shifts:
                    penalty += w_preference

        # 7. Coverage rate bonus (additional incentive)
        coverage_rate = filled_positions / total_positions if total_positions > 0 else 0
        if coverage_rate < 0.8:
            # Heavy penalty for low coverage
            penalty += (0.8 - coverage_rate) * 1_000_000
        elif coverage_rate > 0.9:
            # Bonus for high coverage
            penalty += (coverage_rate - 0.9) * -500_000

        return penalty

    def _calculate_coverage_rate(self, solution: Solution) -> float:
        """Calculate overall coverage rate."""
        total_positions = 0
        filled_positions = 0

        current = self.problem.start_date
        while current <= self.problem.end_date:
            if not self._is_non_working_day(current):
                for shift in self.problem.shifts:
                    assigned = len(solution.assignments.get((current, shift.id), []))
                    total_positions += shift.max_staff
                    filled_positions += min(assigned, shift.max_staff)
            current += timedelta(days=1)

        return filled_positions / total_positions if total_positions > 0 else 0

    def _tournament_selection(self, population: List[Solution], tournament_size: int = 3) -> Solution:
        """Tournament selection."""
        tournament = random.sample(population, min(tournament_size, len(population)))
        return min(tournament, key=lambda x: x.cost)

    def _crossover(self, parent1: Solution, parent2: Solution) -> Solution:
        """Improved crossover that preserves good partial solutions."""
        child = Solution()

        # Get all date-shift pairs
        all_keys = set(parent1.assignments.keys()) | set(parent2.assignments.keys())

        # Use uniform crossover with bias toward better staffed shifts
        for key in all_keys:
            p1_staff = parent1.assignments.get(key, [])
            p2_staff = parent2.assignments.get(key, [])

            date, shift_id = key
            shift = self.problem.shift_by_id[shift_id]

            # Prefer the parent with better coverage for this shift
            p1_coverage = min(len(p1_staff), shift.max_staff) / shift.max_staff if shift.max_staff > 0 else 0
            p2_coverage = min(len(p2_staff), shift.max_staff) / shift.max_staff if shift.max_staff > 0 else 0

            # Weighted selection based on coverage
            if p1_coverage + p2_coverage > 0:
                prob_p1 = p1_coverage / (p1_coverage + p2_coverage)
            else:
                prob_p1 = 0.5

            if random.random() < prob_p1:
                child.assignments[key] = p1_staff.copy()
            else:
                child.assignments[key] = p2_staff.copy()

        return child

    def _adaptive_mutate(self, solution: Solution, generation: int) -> Solution:
        """Adaptive mutation that focuses more on coverage as generations progress."""
        # Increase coverage-focused mutations as we progress
        progress = generation / self.generations

        # Early: explore more, Late: focus on coverage
        if progress < 0.3:
            operations = ['swap', 'reassign', 'adjust', 'fill_gaps']
            weights = [0.3, 0.3, 0.3, 0.1]
        elif progress < 0.7:
            operations = ['swap', 'reassign', 'adjust', 'fill_gaps']
            weights = [0.2, 0.2, 0.3, 0.3]
        else:
            operations = ['swap', 'reassign', 'adjust', 'fill_gaps']
            weights = [0.1, 0.1, 0.3, 0.5]

        # Multiple mutations with decreasing probability
        num_mutations = 1
        if random.random() < 0.3:
            num_mutations += 1
        if random.random() < 0.1:
            num_mutations += 1

        for _ in range(num_mutations):
            operation = random.choices(operations, weights=weights)[0]

            if operation == 'swap':
                self._mutate_swap_employee(solution)
            elif operation == 'reassign':
                self._mutate_reassign_shift(solution)
            elif operation == 'adjust':
                self._mutate_adjust_staffing_improved(solution)
            elif operation == 'fill_gaps':
                self._mutate_fill_gaps(solution)

        return solution

    def _mutate_adjust_staffing_improved(self, solution: Solution):
        """Improved staffing adjustment with bias toward adding employees."""
        keys = list(solution.assignments.keys())
        if not keys:
            return

        # Pick multiple shifts to adjust
        num_adjustments = min(3, len(keys))
        selected_keys = random.sample(keys, num_adjustments)

        for key in selected_keys:
            date, shift_id = key
            shift = self.problem.shift_by_id[shift_id]
            assigned = solution.assignments[key]

            # 70% chance to add, 30% to remove (if possible)
            if random.random() < 0.7 and len(assigned) < shift.max_staff:
                # Try to add employee
                week_key = date.isocalendar()[:2]
                candidates = []

                for emp in self.problem.employees:
                    if (emp.id not in assigned and
                        date not in emp.absence_dates and
                        not self._is_non_working_day(date)):

                        # Check constraints
                        already_assigned = any(
                            emp.id in solution.assignments.get((date, s.id), [])
                            for s in self.problem.shifts
                        )

                        if not already_assigned:
                            # Check weekly hours
                            weekly_hours = 0.0
                            for d in self.weeks[week_key]:
                                for s in self.problem.shifts:
                                    if emp.id in solution.assignments.get((d, s.id), []):
                                        weekly_hours += s.duration

                            if weekly_hours + shift.duration <= emp.max_hours_per_week:
                                candidates.append(emp.id)

                if candidates:
                    # Add multiple if far from max
                    gap = shift.max_staff - len(assigned)
                    add_count = min(random.randint(1, max(1, gap // 2)), len(candidates))
                    selected = random.sample(candidates, add_count)
                    assigned.extend(selected)

            elif len(assigned) > shift.min_staff:
                # Remove employee (less frequently)
                remove_count = min(random.randint(1, 2), len(assigned) - shift.min_staff)
                for _ in range(remove_count):
                    if len(assigned) > shift.min_staff:
                        assigned.remove(random.choice(assigned))

    def _mutate_fill_gaps(self, solution: Solution):
        """Specifically target understaffed shifts."""
        # Find all understaffed shifts
        understaffed = []
        for (date, shift_id), assigned in solution.assignments.items():
            shift = self.problem.shift_by_id[shift_id]
            if len(assigned) < shift.max_staff:
                gap = shift.max_staff - len(assigned)
                understaffed.append(((date, shift_id), gap))

        if not understaffed:
            return

        # Sort by gap size
        understaffed.sort(key=lambda x: x[1], reverse=True)

        # Try to fill top 3 gaps
        for (date, shift_id), gap in understaffed[:3]:
            shift = self.problem.shift_by_id[shift_id]
            assigned = solution.assignments[(date, shift_id)]
            week_key = date.isocalendar()[:2]

            candidates = []
            for emp in self.problem.employees:
                if (emp.id not in assigned and
                    date not in emp.absence_dates and
                    not self._is_non_working_day(date)):

                    # Check if already assigned
                    already_assigned = any(
                        emp.id in solution.assignments.get((date, s.id), [])
                        for s in self.problem.shifts
                    )

                    if not already_assigned:
                        # Check weekly hours
                        weekly_hours = 0.0
                        for d in self.weeks[week_key]:
                            for s in self.problem.shifts:
                                if emp.id in solution.assignments.get((d, s.id), []):
                                    weekly_hours += s.duration

                        if weekly_hours + shift.duration <= emp.max_hours_per_week:
                            remaining = emp.max_hours_per_week - weekly_hours
                            candidates.append((emp.id, remaining))

            if candidates:
                # Sort by remaining capacity
                candidates.sort(key=lambda x: x[1], reverse=True)
                add_count = min(gap, len(candidates))
                selected = [c[0] for c in candidates[:add_count]]
                assigned.extend(selected)

    def _mutate_swap_employee(self, solution: Solution):
        """Original swap mutation."""
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
        """Original reassign mutation."""
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

    def _final_improvement_pass(self, solution: Solution):
        """Final greedy improvement to maximize coverage."""
        improvements = 0

        # Get all dates and shifts
        all_keys = []
        current = self.problem.start_date
        while current <= self.problem.end_date:
            if not self._is_non_working_day(current):
                for shift in self.problem.shifts:
                    all_keys.append((current, shift.id))
            current += timedelta(days=1)

        # Sort by current coverage (lowest first)
        coverage_data = []
        for key in all_keys:
            date, shift_id = key
            shift = self.problem.shift_by_id[shift_id]
            assigned = solution.assignments.get(key, [])
            coverage = len(assigned) / shift.max_staff if shift.max_staff > 0 else 1
            if coverage < 1:
                coverage_data.append((key, coverage, shift.max_staff - len(assigned)))

        coverage_data.sort(key=lambda x: x[1])

        # Try to improve each understaffed shift
        for key, coverage, gap in coverage_data:
            date, shift_id = key
            shift = self.problem.shift_by_id[shift_id]
            assigned = solution.assignments[key]
            week_key = date.isocalendar()[:2]

            # Find all eligible employees
            candidates = []
            for emp in self.problem.employees:
                if (emp.id not in assigned and
                    date not in emp.absence_dates):

                    # Check constraints
                    already_assigned = any(
                        emp.id in solution.assignments.get((date, s.id), [])
                        for s in self.problem.shifts
                    )

                    if not already_assigned:
                        # Check weekly hours
                        weekly_hours = 0.0
                        for d in self.weeks[week_key]:
                            for s in self.problem.shifts:
                                if emp.id in solution.assignments.get((d, s.id), []):
                                    weekly_hours += s.duration

                        if weekly_hours + shift.duration <= emp.max_hours_per_week:
                            # Calculate employee utilization
                            total_hours = sum(
                                s.duration for (d, sid), emps in solution.assignments.items()
                                if emp.id in emps for s in [self.problem.shift_by_id[sid]]
                            )
                            yearly_capacity = emp.max_hours_per_week * 52
                            utilization = calculate_utilization_percentage(total_hours, yearly_capacity) / 100.0

                            # Prioritize underutilized employees
                            if utilization < 0.95:
                                priority = (0.95 - utilization) * 100
                                if shift.name in emp.preferred_shifts:
                                    priority += 10
                                candidates.append((emp.id, priority))

            if candidates:
                # Sort by priority (higher is better)
                candidates.sort(key=lambda x: x[1], reverse=True)

                # Add as many as possible
                for emp_id, _ in candidates[:gap]:
                    assigned.append(emp_id)
                    improvements += 1

        if improvements > 0:
            coverage = self._calculate_coverage_rate(solution)
            print(f"[GA] Final improvement pass added {improvements} assignments, coverage now {coverage:.1%}")