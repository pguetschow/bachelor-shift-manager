"""Genetic algorithm based scheduling."""
import random
from typing import List, Tuple
from datetime import timedelta

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
        """Get German national holidays for a specific year."""
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
        if date in self.holidays:
            return True
        if date.weekday() == 6 and self.sundays_off:  # Sunday
            return True
        return False

    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:
        """Solve using genetic algorithm."""
        self.problem = problem
        self.weeks = get_weeks(problem.start_date, problem.end_date)
        
        # Populate holidays for the date range
        self.holidays = set()
        for year in range(problem.start_date.year, problem.end_date.year + 1):
            year_holidays = self._get_holidays_for_year(year)
            for holiday_tuple in year_holidays:
                holiday_date = problem.start_date.replace(year=holiday_tuple[0], month=holiday_tuple[1], day=holiday_tuple[2])
                if problem.start_date <= holiday_date <= problem.end_date:
                    self.holidays.add(holiday_date)

        # Initialize population
        population = [self._create_random_solution() for _ in range(self.population_size)]
        
        # Evaluate initial population
        for solution in population:
            solution.cost = self._evaluate_fast(solution)
        
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
                
                child.cost = self._evaluate_fast(child)
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
        """Create a random valid solution."""
        solution = create_empty_solution(self.problem)
        
        # Pre-calculate daily availability
        daily_availability = {}
        current = self.problem.start_date
        max_iterations = 1000  # Safety check
        iteration_count = 0
        
        while current <= self.problem.end_date and iteration_count < max_iterations:
            available = []
            for emp in self.problem.employees:
                # Check if employee is available (not absent, not holiday, not Sunday if sundays_off)
                if (current not in emp.absence_dates and 
                    not self._is_non_working_day(current)):
                    available.append(emp.id)
            daily_availability[current] = available
            current += timedelta(days=1)
            iteration_count += 1
        
        # Assign employees randomly
        current = self.problem.start_date
        iteration_count = 0
        
        while current <= self.problem.end_date and iteration_count < max_iterations:
            available = daily_availability[current].copy()
            random.shuffle(available)
            used = set()
            
            for shift in self.problem.shifts:
                key = (current, shift.id)
                candidates = [eid for eid in available if eid not in used]
                
                if candidates:
                    count = random.randint(
                        min(shift.min_staff, len(candidates)),
                        min(shift.max_staff, len(candidates))
                    )
                    selected = random.sample(candidates, count)
                    solution.assignments[key] = selected
                    used.update(selected)
            
            current += timedelta(days=1)
            iteration_count += 1
        
        return solution

    def _evaluate_fast(self, solution: Solution) -> float:
        """Fast fitness evaluation for early generations."""
        penalty = 0
        
        # Check min/max staffing
        for (date, shift_id), emp_ids in solution.assignments.items():
            shift = self.problem.shift_by_id[shift_id]
            count = len(emp_ids)
            if count < shift.min_staff:
                penalty += (shift.min_staff - count) * 10000
            elif count > shift.max_staff:
                penalty += (count - shift.max_staff) * 10000
        
        # Check one shift per day
        violations = 0
        current = self.problem.start_date
        max_iterations = 1000  # Safety check to prevent infinite loops
        iteration_count = 0
        
        while current <= self.problem.end_date and iteration_count < max_iterations:
            emp_counts = {}
            for shift in self.problem.shifts:
                for emp_id in solution.assignments.get((current, shift.id), []):
                    emp_counts[emp_id] = emp_counts.get(emp_id, 0) + 1
            
            for count in emp_counts.values():
                if count > 1:
                    violations += count - 1
            
            current += timedelta(days=1)
            iteration_count += 1
        
        # If we hit the safety limit, add a large penalty
        if iteration_count >= max_iterations:
            penalty += 1000000
        
        penalty += violations * 5000
        
        # Simple coverage bonus
        total_assignments = sum(len(emp_ids) for emp_ids in solution.assignments.values())
        penalty -= total_assignments * 5
        
        return penalty

    def _tournament_selection(self, population: List[Solution], tournament_size: int = 3) -> Solution:
        """Tournament selection."""
        tournament = random.sample(population, tournament_size)
        return min(tournament, key=lambda x: x.cost)

    def _crossover(self, parent1: Solution, parent2: Solution) -> Solution:
        """Single-point crossover."""
        child = Solution()
        
        # Get all date-shift combinations
        all_keys = list(parent1.assignments.keys())
        if not all_keys:
            return child
        
        # Choose crossover point
        crossover_point = random.randint(0, len(all_keys))
        
        # Copy from parent1 before crossover point
        for i in range(crossover_point):
            key = all_keys[i]
            child.assignments[key] = parent1.assignments[key].copy()
        
        # Copy from parent2 after crossover point
        for i in range(crossover_point, len(all_keys)):
            key = all_keys[i]
            child.assignments[key] = parent2.assignments[key].copy()
        
        return child

    def _mutate(self, solution: Solution) -> Solution:
        """Random mutation."""
        if random.random() < self.mutation_rate:
            # Choose random date-shift combination
            all_keys = list(solution.assignments.keys())
            if all_keys:
                key = random.choice(all_keys)
                date, shift_id = key
                shift = self.problem.shift_by_id[shift_id]
                
                # Randomly change assignment
                current_staff = solution.assignments[key]
                if current_staff:
                    # Remove random employee
                    emp_to_remove = random.choice(current_staff)
                    current_staff.remove(emp_to_remove)
                
                # Add random available employee
                available = [
                    emp.id for emp in self.problem.employees
                    if emp.id not in current_staff and
                    date not in emp.absence_dates and
                    not self._is_non_working_day(date)
                ]
                
                if available and len(current_staff) < shift.max_staff:
                    emp_to_add = random.choice(available)
                    current_staff.append(emp_to_add)
        
        return solution
