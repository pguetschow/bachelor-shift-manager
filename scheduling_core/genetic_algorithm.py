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
                 mutation_rate=0.2, crossover_rate=0.8, elitism_size=2):
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elitism_size = elitism_size
    
    @property
    def name(self) -> str:
        return "Genetic Algorithm"
    
    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:
        """Solve using genetic algorithm."""
        self.problem = problem
        self.weeks = get_weeks(problem.start_date, problem.end_date)
        
        # Initialize population
        population = [self._create_random_solution() for _ in range(self.population_size)]
        
        # Evaluate initial population
        for solution in population:
            solution.cost = self._evaluate_fast(solution)
        
        population.sort(key=lambda x: x.cost)
        best_solution = population[0].copy()
        
        # Evolution
        for generation in range(self.generations):
            new_population = []
            
            # Elitism - keep best solutions
            for i in range(self.elitism_size):
                new_population.append(population[i].copy())
            
            # Generate new solutions
            while len(new_population) < self.population_size:
                # Selection
                parent1 = self._tournament_selection(population)
                parent2 = self._tournament_selection(population)
                
                # Crossover
                if random.random() < self.crossover_rate:
                    child1, child2 = self._crossover(parent1, parent2)
                else:
                    child1, child2 = parent1.copy(), parent2.copy()
                
                # Mutation
                self._mutate(child1)
                if len(new_population) + 1 < self.population_size:
                    self._mutate(child2)
                
                # Evaluate
                if generation > self.generations // 2:
                    # Use full evaluation in later generations
                    child1.cost = evaluate_solution(child1, self.problem)
                    if len(new_population) + 1 < self.population_size:
                        child2.cost = evaluate_solution(child2, self.problem)
                else:
                    # Use fast evaluation in early generations
                    child1.cost = self._evaluate_fast(child1)
                    if len(new_population) + 1 < self.population_size:
                        child2.cost = self._evaluate_fast(child2)
                
                new_population.append(child1)
                if len(new_population) < self.population_size:
                    new_population.append(child2)
            
            # Update population
            population = sorted(new_population, key=lambda x: x.cost)[:self.population_size]
            
            # Update best solution
            if population[0].cost < best_solution.cost:
                best_solution = population[0].copy()
                best_solution.cost = evaluate_solution(best_solution, self.problem)
        
        # Final evaluation of best solution
        best_solution.cost = evaluate_solution(best_solution, self.problem)
        return best_solution.to_entries()
    
    def _create_random_solution(self) -> Solution:
        """Create a random valid solution."""
        solution = create_empty_solution(self.problem)
        
        # Pre-calculate daily availability
        daily_availability = {}
        current = self.problem.start_date
        while current <= self.problem.end_date:
            available = []
            for emp in self.problem.employees:
                if current not in emp.absence_dates:
                    available.append(emp.id)
            daily_availability[current] = available
            current += timedelta(days=1)
        
        # Assign employees randomly
        current = self.problem.start_date
        while current <= self.problem.end_date:
            available = daily_availability[current].copy()
            random.shuffle(available)
            used = set()
            
            for shift in self.problem.shift_types:
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
        while current <= self.problem.end_date:
            emp_counts = {}
            for shift in self.problem.shift_types:
                for emp_id in solution.assignments.get((current, shift.id), []):
                    emp_counts[emp_id] = emp_counts.get(emp_id, 0) + 1
            
            for count in emp_counts.values():
                if count > 1:
                    violations += count - 1
            current += timedelta(days=1)
        
        penalty += violations * 5000
        
        # Simple coverage bonus
        total_assignments = sum(len(emp_ids) for emp_ids in solution.assignments.values())
        penalty -= total_assignments * 5
        
        return penalty
    
    def _tournament_selection(self, population: List[Solution], 
                            tournament_size: int = 3) -> Solution:
        """Select solution using tournament selection."""
        tournament = random.sample(population, min(tournament_size, len(population)))
        return min(tournament, key=lambda x: x.cost)
    
    def _crossover(self, parent1: Solution, parent2: Solution) -> Tuple[Solution, Solution]:
        """Uniform crossover."""
        child1, child2 = Solution(), Solution()
        
        for key in parent1.assignments:
            if random.random() < 0.5:
                child1.assignments[key] = parent1.assignments[key].copy()
                child2.assignments[key] = parent2.assignments[key].copy()
            else:
                child1.assignments[key] = parent2.assignments[key].copy()
                child2.assignments[key] = parent1.assignments[key].copy()
        
        return child1, child2
    
    def _mutate(self, solution: Solution) -> None:
        """Mutate solution."""
        for key in list(solution.assignments.keys()):
            if random.random() < self.mutation_rate:
                date, shift_id = key
                shift = self.problem.shift_by_id[shift_id]
                current_staff = solution.assignments[key]
                
                mutation_type = random.choice(['add', 'remove', 'replace'])
                
                if mutation_type == 'add' and len(current_staff) < shift.max_staff:
                    # Try to add employee
                    available = [
                        emp.id for emp in self.problem.employees
                        if emp.id not in current_staff and
                        is_employee_available(emp.id, date, shift, solution, 
                                            self.problem, self.weeks)
                    ]
                    if available:
                        solution.assignments[key].append(random.choice(available))
                
                elif mutation_type == 'remove' and len(current_staff) > shift.min_staff:
                    # Remove random employee
                    solution.assignments[key].remove(random.choice(current_staff))
                
                elif mutation_type == 'replace' and current_staff:
                    # Replace employee
                    old_emp = random.choice(current_staff)
                    available = [
                        emp.id for emp in self.problem.employees
                        if emp.id not in current_staff and
                        is_employee_available(emp.id, date, shift, solution,
                                            self.problem, self.weeks)
                    ]
                    if available:
                        solution.assignments[key].remove(old_emp)
                        solution.assignments[key].append(random.choice(available))
