import random
from collections import defaultdict
from datetime import timedelta
from typing import List, Tuple

import numpy as np
from deap import base, creator, tools

from rostering_app.services.kpi_calculator import KPICalculator
from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry
from .utils import get_weeks


class NSGA2Scheduler(SchedulingAlgorithm):
    """
    Optimized NSGA-II scheduler with simplified repair mechanism for better performance.
    """

    def __init__(self, population_size=50, generations=75,
                 crossover_prob=0.8, mutation_prob=0.4,
                 repair_iterations=3, sundays_off=False,
                 coverage_weight=1.2, utilization_weight=2.0, fairness_weight=0.3):
        self.population_size = population_size
        self.generations = generations
        self.crossover_prob = crossover_prob
        self.mutation_prob = mutation_prob
        self.repair_iterations = repair_iterations
        self.sundays_off = sundays_off
        self.coverage_weight = coverage_weight
        self.utilization_weight = utilization_weight
        self.fairness_weight = fairness_weight
        self.holidays = set()
        self.company = None  # Will be set in solve method

    @property
    def name(self) -> str:
        return "NSGA-II Optimized"

    def _get_holidays_for_year(self, year: int) -> set:
        """Get holidays as (year, month, day) tuples using utils function."""
        from rostering_app.utils import get_holidays_for_year_as_full_tuples
        return get_holidays_for_year_as_full_tuples(year)

    def _is_non_working_day(self, date) -> bool:
        """Check if a date is a non-working day (holiday or Sunday)."""
        if (date.year, date.month, date.day) in self.holidays:
            return True
        if date.weekday() == 6 and self.sundays_off:
            return True
        return False

    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:
        """Solve using optimized NSGA-II with simplified repair."""
        self.problem = problem
        self.company = problem.company
        self.weeks = get_weeks(problem.start_date, problem.end_date)

        # Clean up any existing DEAP creator classes to avoid warnings
        if hasattr(creator, "FitnessMulti"):
            del creator.FitnessMulti
        if hasattr(creator, "Individual"):
            del creator.Individual

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

        # Check if we have any working days
        if not self.working_days:
            print("[NSGA-II Optimized] No working days with available employees found. Returning empty solution.")
            return []

        # Scale down min_staff if needed
        self._check_and_scale_demand()

        # Setup DEAP - 3 objectives (coverage, utilization, fairness)
        creator.create("FitnessMulti", base.Fitness, weights=(self.coverage_weight, self.utilization_weight, self.fairness_weight))
        creator.create("Individual", dict, fitness=creator.FitnessMulti)

        toolbox = base.Toolbox()

        # Register operators
        toolbox.register("individual", self._create_fast_individual)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        toolbox.register("evaluate", self._evaluate_fast)
        toolbox.register("mate", self._fast_crossover)
        toolbox.register("mutate", self._fast_mutate)
        toolbox.register("select", tools.selNSGA2)

        # Create initial population
        print("[NSGA-II Optimized] Creating initial population...")
        population = toolbox.population(n=self.population_size)

        # Evaluate initial population
        fitnesses = list(map(toolbox.evaluate, population))
        for ind, fit in zip(population, fitnesses):
            ind.fitness.values = fit

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
                best_fitness = max(population, key=lambda x: x.fitness.values[0]).fitness.values
                print(f"[NSGA-II Optimized] Gen {gen}: Coverage={best_fitness[0]:.1%}, "
                      f"Utilization={best_fitness[1]:.1%}, Fairness={best_fitness[2]:.2f}")

        # Get best solution
        pareto_front = tools.sortNondominated(population, len(population), first_front_only=True)[0]
        best_ind = max(pareto_front, key=lambda x: x.fitness.values[0])

        # Convert to schedule entries
        return self._decode_solution(best_ind)

    def _calculate_availability(self):
        """Pre-calculate employee availability for efficiency."""
        self.daily_availability = {}
        self.working_days = []

        for date in self.dates:
            if not self._is_non_working_day(date):
                available = []
                for emp in self.problem.employees:
                    if date not in emp.absence_dates:
                        available.append(emp.id)
                
                # Only add date as working day if there are available employees
                if available:
                    self.working_days.append(date)
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
            scale = total_emp_hours / total_req_hours * 0.95
            for shift in self.problem.shifts:
                shift.min_staff = max(1, int(round(shift.min_staff * scale)))
            print(f"[NSGA-II Optimized] Scaled down min_staff by {scale:.2f}× to restore feasibility.")

    def _create_fast_individual(self):
        """Create a valid individual using fast construction."""
        solution = {}

        # Initialize empty
        for date in self.working_days:
            for shift in self.problem.shifts:
                solution[(date, shift.id)] = []

        # Fast greedy construction
        self._fast_construct(solution)

        # Quick repair
        self._quick_repair(solution)

        return creator.Individual(solution)

    def _fast_construct(self, solution):
        """Fast greedy construction focusing on meeting minimum requirements."""
        weekly_hours = defaultdict(lambda: defaultdict(float))

        for date in self.working_days:
            week_key = date.isocalendar()[:2]

            # Skip dates with no available employees
            if len(self.daily_availability[date]) == 0:
                continue

            for shift in self.problem.shifts:
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
                            candidates.append(emp_id)

                # Assign up to target
                for i in range(min(target, len(candidates))):
                    emp_id = candidates[i]
                    solution[key].append(emp_id)
                    weekly_hours[emp_id][week_key] += shift.duration

        # Aggressive filling to improve coverage and utilization
        self._aggressive_fill(solution, weekly_hours)

    def _quick_repair(self, solution):
        """Quick repair of major violations only."""
        for _ in range(self.repair_iterations):
            violations_fixed = 0

            # Fix understaffing
            violations_fixed += self._fix_understaffing_fast(solution)

            # Fix overstaffing
            violations_fixed += self._fix_overstaffing_fast(solution)

            if violations_fixed == 0:
                break

    def _fix_understaffing_fast(self, solution) -> int:
        """Fast fix for understaffed shifts."""
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
                            emp = self.problem.emp_by_id[emp_id]
                            weekly_hours = self._get_weekly_hours_fast(emp_id, week_key, solution)
                            if weekly_hours + shift.duration <= emp.max_hours_per_week:
                                candidates.append(emp_id)

                    # Add employees
                    add_count = min(deficit, len(candidates))
                    if add_count > 0:
                        selected = random.sample(candidates, add_count)
                        assigned.extend(selected)
                        fixes += add_count

        return fixes

    def _fix_overstaffing_fast(self, solution) -> int:
        """Fast fix for overstaffed shifts."""
        fixes = 0

        for (date, shift_id), assigned in solution.items():
            shift = self.problem.shift_by_id[shift_id]

            if len(assigned) > shift.max_staff:
                excess = len(assigned) - shift.max_staff
                # Remove random employees
                for _ in range(excess):
                    if len(assigned) > shift.min_staff:
                        emp_id = random.choice(assigned)
                        assigned.remove(emp_id)
                        fixes += 1

        return fixes

    def _aggressive_fill(self, solution, weekly_hours):
        """Aggressively fill shifts to improve coverage and utilization with fairness."""
        # Scale capacity limit based on problem size (more aggressive for larger problems)
        num_employees = len(self.problem.employees)
        capacity_scale = 0.95 if num_employees > 50 else 0.90  # More aggressive for large companies
        
        for date in self.working_days:
            week_key = date.isocalendar()[:2]

            for shift in self.problem.shifts:
                key = (date, shift.id)
                assigned = solution[key]

                # Try to fill up to max_staff
                gap = shift.max_staff - len(assigned)
                if gap > 0:
                    candidates = []

                    for emp_id in self.daily_availability[date]:
                        if emp_id not in assigned:
                            emp = self.problem.emp_by_id[emp_id]
                            current_weekly = weekly_hours[emp_id][week_key]
                            
                            # Calculate capacity like ILP
                            employee_absences = len(emp.absence_dates)
                            yearly_capacity = emp.max_hours_per_week * 52 - (employee_absences * 8)
                            weekly_capacity = yearly_capacity / 52
                            
                            # Allow up to capacity_scale of weekly capacity
                            max_allowed = weekly_capacity * capacity_scale
                            if current_weekly + shift.duration <= max_allowed:
                                # Calculate current utilization percentage
                                current_util = current_weekly / weekly_capacity
                                
                                # Prefer employees with lower current utilization (more fair)
                                # This ensures work is distributed more evenly
                                fairness_score = 1.0 - current_util  # Lower util = higher score
                                candidates.append((emp_id, fairness_score))

                    if candidates:
                        # Sort by fairness score (lowest utilization first)
                        candidates.sort(key=lambda x: x[1], reverse=True)
                        
                        # Fill as much as possible
                        fill_count = min(gap, len(candidates))
                        for i in range(fill_count):
                            emp_id = candidates[i][0]
                            solution[key].append(emp_id)
                            weekly_hours[emp_id][week_key] += shift.duration

    def _get_weekly_hours_fast(self, emp_id: int, week_key: tuple, solution) -> float:
        """Fast calculation of weekly hours for employee."""
        hours = 0
        for date in self.weeks.get(week_key, []):
            for shift in self.problem.shifts:
                if emp_id in solution.get((date, shift.id), []):
                    hours += shift.duration
        return hours

    def _evaluate_fast(self, individual) -> Tuple[float, float, float]:
        """
        Fast evaluation of individual:
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

        # Calculate utilization using ILP-inspired approach
        emp_hours = defaultdict(float)
        for (date, shift_id), emp_ids in individual.items():
            shift = self.problem.shift_by_id[shift_id]
            for emp_id in emp_ids:
                emp_hours[emp_id] += shift.duration

        utilizations = []
        for emp in self.problem.employees:
            worked = emp_hours.get(emp.id, 0)
            
            # Calculate capacity like ILP: yearly capacity minus absences
            employee_absences = len(emp.absence_dates)
            yearly_capacity = emp.max_hours_per_week * 52 - (employee_absences * 8)
            
            # Calculate working days in the problem period
            working_days_in_period = len(self.working_days)
            total_working_days_in_year = 52 * (6 if self.sundays_off else 7)
            
            # Scale capacity to the problem period
            period_capacity = yearly_capacity * (working_days_in_period / total_working_days_in_year)
            
            if period_capacity > 0:
                util = min(worked / period_capacity, 1.0)
                utilizations.append(util)

        avg_utilization = np.mean(utilizations) if utilizations else 0
        
        # Boost utilization score if it's below target (85%)
        if avg_utilization < 0.85:
            avg_utilization = avg_utilization * 0.7  # Penalize low utilization more

        # Calculate fairness
        if len(emp_hours) > 1:
            hours_list = list(emp_hours.values())
            mean_hours = np.mean(hours_list)
            std_hours = np.std(hours_list)
            cv = std_hours / mean_hours if mean_hours > 0 else 0
            fairness = 1 / (1 + cv)
        else:
            fairness = 1.0

        return (coverage_rate, avg_utilization, fairness)

    def _fast_crossover(self, ind1, ind2):
        """Fast crossover operation."""
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

        # Quick repair
        self._quick_repair(child1)
        self._quick_repair(child2)

        # Update individuals
        ind1.clear()
        ind1.update(child1)
        ind2.clear()
        ind2.update(child2)

        return ind1, ind2

    def _fast_mutate(self, individual):
        """Fast mutation operation."""
        # More aggressive mutations
        num_mutations = random.randint(2, 5)

        for _ in range(num_mutations):
            # Bias towards adding staff and redistributing (60% add, 20% remove, 20% redistribute)
            mutation_type = random.choices(['add', 'remove', 'redistribute'], weights=[0.6, 0.2, 0.2])[0]

            if mutation_type == 'add':
                self._mutation_add_staff_fast(individual)
            elif mutation_type == 'remove':
                self._mutation_remove_staff_fast(individual)
            elif mutation_type == 'redistribute':
                self._mutation_redistribute_fair(individual)

        # Quick repair
        self._quick_repair(individual)

        return individual,

    def _mutation_add_staff_fast(self, individual):
        """Fast add staff mutation."""
        understaffed = []

        for (date, shift_id), assigned in individual.items():
            shift = self.problem.shift_by_id[shift_id]
            if len(assigned) < shift.max_staff:
                gap = shift.max_staff - len(assigned)
                understaffed.append(((date, shift_id), gap))

        if understaffed:
            # Sort by gap size (largest gaps first)
            understaffed.sort(key=lambda x: x[1], reverse=True)
            
            # Try to fill multiple understaffed shifts
            for (date, shift_id), gap in understaffed[:3]:  # Try top 3
                shift = self.problem.shift_by_id[shift_id]
                assigned = individual[(date, shift_id)]
                week_key = date.isocalendar()[:2]

                candidates = []
                for emp_id in self.daily_availability.get(date, []):
                    if emp_id not in assigned:
                        emp = self.problem.emp_by_id[emp_id]
                        weekly_hours = self._get_weekly_hours_fast(emp_id, week_key, individual)
                        
                        # Calculate capacity like ILP
                        employee_absences = len(emp.absence_dates)
                        yearly_capacity = emp.max_hours_per_week * 52 - (employee_absences * 8)
                        weekly_capacity = yearly_capacity / 52
                        
                        # Scale capacity limit based on problem size
                        num_employees = len(self.problem.employees)
                        capacity_scale = 0.95 if num_employees > 50 else 0.90
                        
                        # Allow up to capacity_scale of weekly capacity
                        if weekly_hours + shift.duration <= weekly_capacity * capacity_scale:
                            # Calculate current utilization
                            current_util = weekly_hours / weekly_capacity
                            # Prefer employees with lower utilization
                            fairness_score = 1.0 - current_util
                            candidates.append((emp_id, fairness_score))

                if candidates:
                    # Sort by fairness score and select best candidates
                    candidates.sort(key=lambda x: x[1], reverse=True)
                    add_count = min(gap, len(candidates))
                    selected = [candidates[i][0] for i in range(add_count)]
                    assigned.extend(selected)

    def _mutation_remove_staff_fast(self, individual):
        """Fast remove staff mutation."""
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

    def _mutation_redistribute_fair(self, individual):
        """Redistribute work to improve fairness."""
        # Calculate current utilization for all employees
        emp_hours = defaultdict(float)
        for (date, shift_id), emp_ids in individual.items():
            shift = self.problem.shift_by_id[shift_id]
            for emp_id in emp_ids:
                emp_hours[emp_id] += shift.duration

        # Find most and least utilized employees
        utilizations = []
        for emp in self.problem.employees:
            worked = emp_hours.get(emp.id, 0)
            
            # Calculate capacity like ILP
            employee_absences = len(emp.absence_dates)
            yearly_capacity = emp.max_hours_per_week * 52 - (employee_absences * 8)
            working_days_in_period = len(self.working_days)
            total_working_days_in_year = 52 * (6 if self.sundays_off else 7)
            period_capacity = yearly_capacity * (working_days_in_period / total_working_days_in_year)
            
            util = worked / period_capacity if period_capacity > 0 else 0
            utilizations.append((emp.id, util))

        utilizations.sort(key=lambda x: x[1], reverse=True)
        
        if len(utilizations) >= 2:
            most_utilized = utilizations[0]  # Highest utilization
            least_utilized = utilizations[-1]  # Lowest utilization
            
            # If there's a significant gap (>10%), try to redistribute
            if most_utilized[1] - least_utilized[1] > 0.1:
                # Find a shift where most_utilized is assigned
                for (date, shift_id), assigned in individual.items():
                    if most_utilized[0] in assigned:
                        shift = self.problem.shift_by_id[shift_id]
                        
                        # Check if least_utilized can take this shift
                        if (least_utilized[0] in self.daily_availability.get(date, []) and
                            least_utilized[0] not in assigned):
                            
                            # Check if least_utilized has capacity
                            current_hours = emp_hours.get(least_utilized[0], 0)
                            emp = self.problem.emp_by_id[least_utilized[0]]
                            employee_absences = len(emp.absence_dates)
                            yearly_capacity = emp.max_hours_per_week * 52 - (employee_absences * 8)
                            weekly_capacity = yearly_capacity / 52
                            
                            # Scale capacity limit based on problem size
                            num_employees = len(self.problem.employees)
                            capacity_scale = 0.95 if num_employees > 50 else 0.90
                            
                            if current_hours + shift.duration <= weekly_capacity * capacity_scale:
                                # Redistribute: remove from most_utilized, add to least_utilized
                                assigned.remove(most_utilized[0])
                                assigned.append(least_utilized[0])
                                break

    def _decode_solution(self, individual) -> List[ScheduleEntry]:
        """Convert solution dictionary to schedule entries."""
        entries = []
        for (date, shift_id), emp_ids in individual.items():
            for emp_id in emp_ids:
                entries.append(ScheduleEntry(emp_id, date, shift_id))
        return entries
