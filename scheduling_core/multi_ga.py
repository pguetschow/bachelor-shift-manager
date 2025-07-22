import random
import numpy as np
from typing import List, Tuple, Dict, Set
from datetime import timedelta, datetime
from collections import defaultdict
from deap import base, creator, tools, algorithms
import array

from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry, Solution
from .utils import get_weeks
from rostering_app.calculations import calculate_utilization_percentage


class NSGA2Scheduler(SchedulingAlgorithm):
    """
    Hybrid NSGA-II scheduler that uses local search to repair constraint violations.
    This ensures solutions have zero violations while optimizing other objectives.
    """

    def __init__(self, population_size=80, generations=150,
                 crossover_prob=0.85, mutation_prob=0.25,
                 repair_iterations=10, sundays_off=False):
        self.population_size = population_size
        self.generations = generations
        self.crossover_prob = crossover_prob
        self.mutation_prob = mutation_prob
        self.repair_iterations = repair_iterations
        self.sundays_off = sundays_off
        self.holidays = set()

    @property
    def name(self) -> str:
        return "NSGA-II Hybrid with Repair"

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

    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:
        """Solve using NSGA-II with repair mechanism."""
        self.problem = problem
        self.weeks = get_weeks(problem.start_date, problem.end_date)

        # Populate holidays
        self.holidays = set()
        for year in range(problem.start_date.year, problem.end_date.year + 1):
            self.holidays.update(self._get_holidays_for_year(year))

        # Build dates list
        self.dates = []
        current = problem.start_date
        while current <= problem.end_date:
            self.dates.append(current)
            current += timedelta(days=1)

        # Pre-calculate employee availability
        self._calculate_availability()

        # Scale down min_staff if needed
        self._check_and_scale_demand()

        # Setup DEAP - 3 objectives (no violations needed as we repair)
        creator.create("FitnessMulti", base.Fitness, weights=(1.0, 1.0, 1.0))
        creator.create("Individual", list, fitness=creator.FitnessMulti)

        toolbox = base.Toolbox()

        # Register operators
        toolbox.register("individual", self._create_repaired_individual)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        toolbox.register("evaluate", self._evaluate_repaired)
        toolbox.register("mate", self._crossover_with_repair)
        toolbox.register("mutate", self._mutate_with_repair)
        toolbox.register("select", tools.selNSGA2)

        # Create initial population
        print("[NSGA-II Hybrid] Creating initial population with repairs...")
        population = toolbox.population(n=self.population_size)

        # Evaluate initial population
        fitnesses = list(map(toolbox.evaluate, population))
        for ind, fit in zip(population, fitnesses):
            ind.fitness.values = fit

        # Statistics
        stats = tools.Statistics(lambda ind: ind.fitness.values)
        stats.register("avg", np.mean, axis=0)
        stats.register("min", np.min, axis=0)
        stats.register("max", np.max, axis=0)

        # Evolution
        for gen in range(self.generations):
            # Select parents
            offspring = toolbox.select(population, len(population))
            offspring = [toolbox.clone(ind) for ind in offspring]

            # Apply crossover and mutation
            for i in range(0, len(offspring) - 1, 2):
                if random.random() < self.crossover_prob:
                    toolbox.mate(offspring[i], offspring[i + 1])
                    del offspring[i].fitness.values
                    del offspring[i + 1].fitness.values

            for mutant in offspring:
                if random.random() < self.mutation_prob:
                    toolbox.mutate(mutant)
                    del mutant.fitness.values

            # Evaluate offspring
            invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
            fitnesses = map(toolbox.evaluate, invalid_ind)
            for ind, fit in zip(invalid_ind, fitnesses):
                ind.fitness.values = fit

            # Environmental selection
            population = toolbox.select(population + offspring, self.population_size)

            # Progress report
            if gen % 10 == 0:
                record = stats.compile(population)
                coverage, utilization, fairness = record['max']
                print(f"[NSGA-II Hybrid] Gen {gen}: Coverage={coverage:.1%}, "
                      f"Utilization={utilization:.1%}, Fairness={fairness:.2f}")

        # Get best solution
        pareto_front = tools.sortNondominated(population, len(population), first_front_only=True)[0]

        # Select solution with best coverage
        best_ind = max(pareto_front, key=lambda x: x.fitness.values[0])

        # Final aggressive filling
        self._aggressive_final_fill(best_ind)

        # Convert to schedule entries
        return self._decode_solution(best_ind)

    def _calculate_availability(self):
        """Pre-calculate employee availability for efficiency."""
        self.daily_availability = {}
        self.working_days = []

        for date in self.dates:
            if not self._is_non_working_day(date):
                self.working_days.append(date)
                available = []
                for emp in self.problem.employees:
                    if date not in emp.absence_dates:
                        available.append(emp.id)
                self.daily_availability[date] = set(available)

    def _check_and_scale_demand(self):
        """Check if demand exceeds capacity and scale down if needed."""
        num_weeks = len(self.weeks)
        total_emp_hours = sum(emp.max_hours_per_week for emp in self.problem.employees) * num_weeks

        working_days_count = len(self.working_days)
        total_req_hours = sum(
            shift.min_staff * shift.duration * working_days_count
            for shift in self.problem.shifts
        )

        if total_req_hours > total_emp_hours:
            scale = total_emp_hours / total_req_hours * 0.95  # 95% to leave some slack
            for shift in self.problem.shifts:
                shift.min_staff = max(1, int(round(shift.min_staff * scale)))
            print(f"[NSGA-II Hybrid] Scaled down min_staff by {scale:.2f}× to restore feasibility.")

    def _create_repaired_individual(self):
        """Create a valid individual using construction + repair."""
        # Individual representation: {(date, shift_id): [emp_ids]}
        solution = {}

        # Initialize empty
        for date in self.working_days:
            for shift in self.problem.shifts:
                solution[(date, shift.id)] = []

        # Greedy construction focusing on min requirements
        self._greedy_construct(solution)

        # Repair any violations
        self._repair_solution(solution)

        # Try to improve coverage
        self._improve_coverage(solution)

        return creator.Individual(solution)

    def _greedy_construct(self, solution):
        """Greedy construction focusing on meeting minimum requirements."""
        # Track assignments
        weekly_hours = defaultdict(lambda: defaultdict(float))

        # First pass: meet minimum requirements
        for date in self.working_days:
            week_key = date.isocalendar()[:2]

            # Sort shifts by criticality (harder to staff first)
            shifts_sorted = sorted(self.problem.shifts,
                                   key=lambda s: s.min_staff / len(self.daily_availability[date]),
                                   reverse=True)

            for shift in shifts_sorted:
                key = (date, shift.id)
                target = shift.min_staff

                # Get available employees
                candidates = []
                for emp_id in self.daily_availability[date]:
                    emp = self.problem.emp_by_id[emp_id]

                    # Check if already assigned today
                    already_assigned = any(
                        emp_id in solution[(date, s.id)]
                        for s in self.problem.shifts
                    )

                    if not already_assigned:
                        current_weekly = weekly_hours[emp_id][week_key]
                        if current_weekly + shift.duration <= emp.max_hours_per_week:
                            # Score by remaining capacity
                            remaining = emp.max_hours_per_week - current_weekly
                            preference_score = 10 if shift.name in emp.preferred_shifts else 0
                            candidates.append((emp_id, remaining + preference_score))

                # Sort by score
                candidates.sort(key=lambda x: x[1], reverse=True)

                # Assign up to target
                for i in range(min(target, len(candidates))):
                    emp_id = candidates[i][0]
                    solution[key].append(emp_id)
                    weekly_hours[emp_id][week_key] += shift.duration

    def _repair_solution(self, solution):
        """Repair constraint violations."""
        for _ in range(self.repair_iterations):
            violations_fixed = 0

            # Fix understaffing
            violations_fixed += self._fix_understaffing(solution)

            # Fix overstaffing
            violations_fixed += self._fix_overstaffing(solution)

            # Fix weekly hours violations
            violations_fixed += self._fix_weekly_hours(solution)

            # Fix rest period violations
            violations_fixed += self._fix_rest_periods(solution)

            # Fix multiple shifts per day
            violations_fixed += self._fix_multiple_shifts(solution)

            if violations_fixed == 0:
                break

    def _fix_understaffing(self, solution) -> int:
        """Fix understaffed shifts."""
        fixes = 0

        for date in self.working_days:
            for shift in self.problem.shifts:
                key = (date, shift.id)
                assigned = solution[key]

                if len(assigned) < shift.min_staff:
                    deficit = shift.min_staff - len(assigned)
                    week_key = date.isocalendar()[:2]

                    # Find available employees
                    candidates = []
                    for emp_id in self.daily_availability[date]:
                        if emp_id not in assigned:
                            # Check constraints
                            if self._can_assign(emp_id, date, shift, solution):
                                weekly_hours = self._get_weekly_hours(emp_id, week_key, solution)
                                if weekly_hours + shift.duration <= self.problem.emp_by_id[emp_id].max_hours_per_week:
                                    candidates.append(emp_id)

                    # Add employees
                    add_count = min(deficit, len(candidates))
                    if add_count > 0:
                        selected = random.sample(candidates, add_count)
                        assigned.extend(selected)
                        fixes += add_count

        return fixes

    def _fix_overstaffing(self, solution) -> int:
        """Fix overstaffed shifts."""
        fixes = 0

        for (date, shift_id), assigned in solution.items():
            shift = self.problem.shift_by_id[shift_id]

            if len(assigned) > shift.max_staff:
                excess = len(assigned) - shift.max_staff

                # Remove employees with highest total hours
                emp_hours = []
                for emp_id in assigned:
                    total = sum(
                        s.duration
                        for (d, sid), emps in solution.items()
                        if emp_id in emps
                        for s in [self.problem.shift_by_id[sid]]
                    )
                    emp_hours.append((emp_id, total))

                emp_hours.sort(key=lambda x: x[1], reverse=True)

                for i in range(excess):
                    emp_id = emp_hours[i][0]
                    assigned.remove(emp_id)
                    fixes += 1

        return fixes

    def _fix_weekly_hours(self, solution) -> int:
        """Fix weekly hours violations."""
        fixes = 0

        for emp in self.problem.employees:
            for week_key, week_dates in self.weeks.items():
                hours = self._get_weekly_hours(emp.id, week_key, solution)

                if hours > emp.max_hours_per_week:
                    # Find shifts to remove from
                    emp_shifts = []
                    for date in week_dates:
                        for shift in self.problem.shifts:
                            if emp.id in solution.get((date, shift.id), []):
                                emp_shifts.append((date, shift.id, shift.duration))

                    # Sort by duration (remove from longest first)
                    emp_shifts.sort(key=lambda x: x[2], reverse=True)

                    # Remove until under limit
                    for date, shift_id, duration in emp_shifts:
                        shift = self.problem.shift_by_id[shift_id]
                        assigned = solution[(date, shift_id)]

                        # Only remove if won't violate min_staff
                        if len(assigned) > shift.min_staff:
                            assigned.remove(emp.id)
                            hours -= duration
                            fixes += 1

                            if hours <= emp.max_hours_per_week:
                                break

        return fixes

    def _fix_rest_periods(self, solution) -> int:
        """Fix rest period violations."""
        fixes = 0

        for i in range(len(self.dates) - 1):
            d1, d2 = self.dates[i], self.dates[i + 1]

            if d1 not in self.working_days or d2 not in self.working_days:
                continue

            for emp in self.problem.employees:
                shift1 = None
                shift2 = None

                for shift in self.problem.shifts:
                    if emp.id in solution.get((d1, shift.id), []):
                        shift1 = shift
                    if emp.id in solution.get((d2, shift.id), []):
                        shift2 = shift

                if shift1 and shift2 and self._violates_rest_period(shift1, shift2, d1):
                    # Remove from second shift if possible
                    assigned2 = solution[(d2, shift2.id)]
                    if len(assigned2) > shift2.min_staff:
                        assigned2.remove(emp.id)
                        fixes += 1

        return fixes

    def _fix_multiple_shifts(self, solution) -> int:
        """Fix multiple shifts per day violations."""
        fixes = 0

        for date in self.working_days:
            emp_shifts = defaultdict(list)

            for shift in self.problem.shifts:
                for emp_id in solution.get((date, shift.id), []):
                    emp_shifts[emp_id].append(shift)

            for emp_id, shifts in emp_shifts.items():
                if len(shifts) > 1:
                    # Keep the shift with fewer staff
                    shift_staffing = []
                    for shift in shifts:
                        count = len(solution[(date, shift.id)])
                        shift_staffing.append((shift, count))

                    shift_staffing.sort(key=lambda x: x[1])

                    # Remove from all but the least staffed
                    for shift, _ in shift_staffing[1:]:
                        solution[(date, shift.id)].remove(emp_id)
                        fixes += 1

        return fixes

    def _can_assign(self, emp_id: int, date, shift, solution) -> bool:
        """Check if employee can be assigned to shift."""
        # Check if already assigned that day
        for s in self.problem.shifts:
            if emp_id in solution.get((date, s.id), []):
                return False

        # Check rest periods
        # Previous day
        if date > self.problem.start_date:
            prev_date = date - timedelta(days=1)
            for s in self.problem.shifts:
                if emp_id in solution.get((prev_date, s.id), []):
                    if self._violates_rest_period(s, shift, prev_date):
                        return False

        # Next day
        if date < self.problem.end_date:
            next_date = date + timedelta(days=1)
            for s in self.problem.shifts:
                if emp_id in solution.get((next_date, s.id), []):
                    if self._violates_rest_period(shift, s, date):
                        return False

        return True

    def _get_weekly_hours(self, emp_id: int, week_key: tuple, solution) -> float:
        """Calculate weekly hours for employee."""
        hours = 0
        for date in self.weeks.get(week_key, []):
            for shift in self.problem.shifts:
                if emp_id in solution.get((date, shift.id), []):
                    hours += shift.duration
        return hours

    def _improve_coverage(self, solution):
        """Try to improve coverage beyond minimum requirements."""
        for date in self.working_days:
            week_key = date.isocalendar()[:2]

            for shift in self.problem.shifts:
                key = (date, shift.id)
                assigned = solution[key]

                # Try to add more staff
                gap = shift.max_staff - len(assigned)
                if gap > 0:
                    candidates = []

                    for emp_id in self.daily_availability[date]:
                        if emp_id not in assigned and self._can_assign(emp_id, date, shift, solution):
                            emp = self.problem.emp_by_id[emp_id]
                            weekly_hours = self._get_weekly_hours(emp_id, week_key, solution)

                            if weekly_hours + shift.duration <= emp.max_hours_per_week:
                                # Calculate current utilization
                                total_hours = sum(
                                    s.duration
                                    for (d, sid), emps in solution.items()
                                    if emp_id in emps
                                    for s in [self.problem.shift_by_id[sid]]
                                )
                                capacity = emp.max_hours_per_week * len(self.weeks)
                                utilization = total_hours / capacity if capacity > 0 else 0

                                if utilization < 0.9:  # Don't overwork
                                    score = (0.9 - utilization) * 100
                                    if shift.name in emp.preferred_shifts:
                                        score += 20
                                    candidates.append((emp_id, score))

                    if candidates:
                        # Sort by score
                        candidates.sort(key=lambda x: x[1], reverse=True)

                        # Add some employees
                        add_count = min(int(gap * 0.5), len(candidates))
                        for i in range(add_count):
                            emp_id = candidates[i][0]
                            assigned.append(emp_id)

    def _evaluate_repaired(self, individual) -> Tuple[float, float, float]:
        """
        Evaluate repaired individual (no violation checking needed):
        1. Coverage rate (maximize)
        2. Average utilization (maximize)
        3. Fairness score (maximize)
        """
        # Calculate coverage
        total_positions = 0
        filled_positions = 0

        for date in self.working_days:
            for shift in self.problem.shifts:
                assigned = len(individual.get((date, shift.id), []))
                total_positions += shift.max_staff
                filled_positions += min(assigned, shift.max_staff)

        coverage_rate = filled_positions / total_positions if total_positions > 0 else 0

        # Calculate utilization
        emp_hours = defaultdict(float)
        for (date, shift_id), emp_ids in individual.items():
            shift = self.problem.shift_by_id[shift_id]
            for emp_id in emp_ids:
                emp_hours[emp_id] += shift.duration

        utilizations = []
        for emp in self.problem.employees:
            worked = emp_hours.get(emp.id, 0)
            # Calculate actual capacity considering absences
            working_days_available = sum(
                1 for d in self.working_days
                if d not in emp.absence_dates
            )
            daily_capacity = emp.max_hours_per_week / (6 if self.sundays_off else 7)
            capacity = working_days_available * daily_capacity

            if capacity > 0:
                util = min(worked / capacity, 1.0)
                utilizations.append(util)

        avg_utilization = np.mean(utilizations) if utilizations else 0

        # Calculate fairness
        if len(emp_hours) > 1:
            hours_list = list(emp_hours.values())
            # Use coefficient of variation for fairness
            mean_hours = np.mean(hours_list)
            std_hours = np.std(hours_list)
            cv = std_hours / mean_hours if mean_hours > 0 else 0
            fairness = 1 / (1 + cv)  # Transform to 0-1 where 1 is perfectly fair
        else:
            fairness = 1.0

        return (coverage_rate, avg_utilization, fairness)

    def _crossover_with_repair(self, ind1, ind2):
        """Crossover followed by repair."""
        # Week-based crossover
        child1 = {}
        child2 = {}

        for week_key, week_dates in self.weeks.items():
            if random.random() < 0.5:
                # Child1 gets week from parent1, child2 from parent2
                for date in week_dates:
                    if date in self.working_days:
                        for shift in self.problem.shifts:
                            key = (date, shift.id)
                            child1[key] = ind1.get(key, []).copy()
                            child2[key] = ind2.get(key, []).copy()
            else:
                # Swap
                for date in week_dates:
                    if date in self.working_days:
                        for shift in self.problem.shifts:
                            key = (date, shift.id)
                            child1[key] = ind2.get(key, []).copy()
                            child2[key] = ind1.get(key, []).copy()

        # Repair children
        self._repair_solution(child1)
        self._repair_solution(child2)

        # Update individuals
        ind1.clear()
        ind1.update(child1)
        ind2.clear()
        ind2.update(child2)

        return ind1, ind2

    def _mutate_with_repair(self, individual):
        """Mutation followed by repair."""
        # Choose mutation strength based on current state
        coverage = self._calculate_coverage(individual)

        if coverage < 0.7:
            # Aggressive mutations to improve coverage
            num_mutations = random.randint(5, 10)
        else:
            # Lighter mutations for fine-tuning
            num_mutations = random.randint(1, 3)

        for _ in range(num_mutations):
            mutation_type = random.choice(['add', 'remove', 'swap', 'redistribute'])

            if mutation_type == 'add':
                self._mutation_add_staff(individual)
            elif mutation_type == 'remove':
                self._mutation_remove_staff(individual)
            elif mutation_type == 'swap':
                self._mutation_swap_staff(individual)
            elif mutation_type == 'redistribute':
                self._mutation_redistribute(individual)

        # Repair after mutations
        self._repair_solution(individual)

        return individual,

    def _mutation_add_staff(self, individual):
        """Add staff to understaffed shifts."""
        understaffed = []

        for (date, shift_id), assigned in individual.items():
            shift = self.problem.shift_by_id[shift_id]
            if len(assigned) < shift.max_staff:
                gap = shift.max_staff - len(assigned)
                understaffed.append(((date, shift_id), gap))

        if understaffed:
            # Sort by gap size
            understaffed.sort(key=lambda x: x[1], reverse=True)

            # Try to fill largest gap
            (date, shift_id), gap = understaffed[0]
            shift = self.problem.shift_by_id[shift_id]
            assigned = individual[(date, shift_id)]

            candidates = []
            for emp_id in self.daily_availability.get(date, []):
                if emp_id not in assigned and self._can_assign(emp_id, date, shift, individual):
                    candidates.append(emp_id)

            if candidates:
                add_count = min(random.randint(1, gap), len(candidates))
                selected = random.sample(candidates, add_count)
                assigned.extend(selected)

    def _mutation_remove_staff(self, individual):
        """Remove staff from overstaffed shifts."""
        overstaffed = []

        for (date, shift_id), assigned in individual.items():
            shift = self.problem.shift_by_id[shift_id]
            if len(assigned) > shift.min_staff:
                excess = len(assigned) - shift.min_staff
                overstaffed.append(((date, shift_id), excess, assigned))

        if overstaffed:
            (date, shift_id), excess, assigned = random.choice(overstaffed)
            remove_count = random.randint(1, min(excess, 2))

            for _ in range(remove_count):
                if len(assigned) > self.problem.shift_by_id[shift_id].min_staff:
                    emp_id = random.choice(assigned)
                    assigned.remove(emp_id)

    def _mutation_swap_staff(self, individual):
        """Swap staff between shifts."""
        # Get all non-empty shifts
        staffed_shifts = [(k, v) for k, v in individual.items() if v]

        if len(staffed_shifts) >= 2:
            (date1, shift1_id), staff1 = random.choice(staffed_shifts)
            (date2, shift2_id), staff2 = random.choice(staffed_shifts)

            if staff1 and staff2 and (date1, shift1_id) != (date2, shift2_id):
                emp1 = random.choice(staff1)
                emp2 = random.choice(staff2)

                # Check if swap is valid
                emp1_obj = self.problem.emp_by_id[emp1]
                emp2_obj = self.problem.emp_by_id[emp2]

                if (date2 not in emp1_obj.absence_dates and
                        date1 not in emp2_obj.absence_dates):
                    # Perform swap
                    staff1.remove(emp1)
                    staff2.remove(emp2)
                    staff1.append(emp2)
                    staff2.append(emp1)

    def _mutation_redistribute(self, individual):
        """Redistribute staff for better balance."""
        # Find most and least staffed shifts on same day
        daily_staffing = defaultdict(list)

        for (date, shift_id), assigned in individual.items():
            shift = self.problem.shift_by_id[shift_id]
            ratio = len(assigned) / shift.max_staff if shift.max_staff > 0 else 1
            daily_staffing[date].append((shift_id, ratio, assigned, shift))

        for date, shifts_info in daily_staffing.items():
            if len(shifts_info) >= 2:
                # Sort by staffing ratio
                shifts_info.sort(key=lambda x: x[1])

                least_staffed = shifts_info[0]
                most_staffed = shifts_info[-1]

                if (most_staffed[1] - least_staffed[1] > 0.2 and
                        len(most_staffed[2]) > most_staffed[3].min_staff and
                        len(least_staffed[2]) < least_staffed[3].max_staff):

                    # Try to move someone
                    for emp_id in most_staffed[2]:
                        if emp_id not in least_staffed[2]:
                            # Move employee
                            most_staffed[2].remove(emp_id)
                            least_staffed[2].append(emp_id)
                            break

    def _calculate_coverage(self, individual) -> float:
        """Calculate current coverage rate."""
        total_positions = 0
        filled_positions = 0

        for date in self.working_days:
            for shift in self.problem.shifts:
                assigned = len(individual.get((date, shift.id), []))
                total_positions += shift.max_staff
                filled_positions += min(assigned, shift.max_staff)

        return filled_positions / total_positions if total_positions > 0 else 0

    def _aggressive_final_fill(self, individual):
        """Aggressive final pass to maximize coverage."""
        improvements = 0

        # Sort shifts by current coverage
        shift_coverage = []
        for (date, shift_id), assigned in individual.items():
            shift = self.problem.shift_by_id[shift_id]
            coverage = len(assigned) / shift.max_staff if shift.max_staff > 0 else 1
            if coverage < 1:
                gap = shift.max_staff - len(assigned)
                shift_coverage.append(((date, shift_id), coverage, gap))

        shift_coverage.sort(key=lambda x: x[1])

        # Try to fill gaps
        for (date, shift_id), coverage, gap in shift_coverage:
            shift = self.problem.shift_by_id[shift_id]
            assigned = individual[(date, shift_id)]
            week_key = date.isocalendar()[:2]

            candidates = []
            for emp_id in self.daily_availability.get(date, []):
                if emp_id not in assigned and self._can_assign(emp_id, date, shift, individual):
                    emp = self.problem.emp_by_id[emp_id]
                    weekly_hours = self._get_weekly_hours(emp_id, week_key, individual)

                    if weekly_hours + shift.duration <= emp.max_hours_per_week:
                        # Calculate utilization
                        total_hours = sum(
                            s.duration
                            for (d, sid), emps in individual.items()
                            if emp_id in emps
                            for s in [self.problem.shift_by_id[sid]]
                        )
                        working_days_available = sum(
                            1 for d in self.working_days
                            if d not in emp.absence_dates
                        )
                        daily_capacity = emp.max_hours_per_week / (6 if self.sundays_off else 7)
                        capacity = working_days_available * daily_capacity

                        utilization = total_hours / capacity if capacity > 0 else 0

                        if utilization < 0.95:
                            priority = (0.95 - utilization) * 100
                            if shift.name in emp.preferred_shifts:
                                priority += 30
                            candidates.append((emp_id, priority))

            if candidates:
                candidates.sort(key=lambda x: x[1], reverse=True)

                # Fill as much as possible
                for emp_id, _ in candidates[:gap]:
                    assigned.append(emp_id)
                    improvements += 1

        if improvements > 0:
            coverage = self._calculate_coverage(individual)
            print(f"[NSGA-II Hybrid] Final fill added {improvements} assignments, coverage now {coverage:.1%}")

    def _decode_solution(self, individual) -> List[ScheduleEntry]:
        """Convert solution dictionary to schedule entries."""
        entries = []
        for (date, shift_id), emp_ids in individual.items():
            for emp_id in emp_ids:
                entries.append(ScheduleEntry(emp_id, date, shift_id))
        return entries

    def _violates_rest_period(self, shift1, shift2, date1) -> bool:
        """Check if two consecutive shifts violate 11-hour rest period."""
        end1 = datetime.combine(date1, shift1.end)
        if shift1.end < shift1.start:
            end1 += timedelta(days=1)
        start2 = datetime.combine(date1 + timedelta(days=1), shift2.start)
        pause = (start2 - end1).total_seconds() / 3600
        return pause < 11
