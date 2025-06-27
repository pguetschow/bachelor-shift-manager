"""Simulated annealing based scheduling."""
import random
import math
from typing import List
from datetime import timedelta
from enum import Enum

from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry, Solution
from .utils import (
    get_weeks, is_employee_available, evaluate_solution,
    create_empty_solution
)


class CoolingSchedule(Enum):
    """Types of cooling schedules."""
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    LOGARITHMIC = "logarithmic"


class SimulatedAnnealingScheduler(SchedulingAlgorithm):
    """Scheduling using simulated annealing."""
    
    def __init__(self, cooling_schedule=CoolingSchedule.EXPONENTIAL,
                 initial_temp=10000.0, final_temp=1.0, 
                 max_iterations=10000, cooling_rate=0.995):
        self.cooling_schedule = cooling_schedule
        self.initial_temp = initial_temp
        self.final_temp = final_temp
        self.max_iterations = max_iterations
        self.cooling_rate = cooling_rate
    
    @property
    def name(self) -> str:
        schedule_name = {
            CoolingSchedule.EXPONENTIAL: "Exponential",
            CoolingSchedule.LINEAR: "Linear",
            CoolingSchedule.LOGARITHMIC: "Logarithmic"
        }[self.cooling_schedule]
        return f"Simulated Annealing ({schedule_name})"
    
    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:
        """Solve using simulated annealing."""
        self.problem = problem
        self.weeks = get_weeks(problem.start_date, problem.end_date)
        
        # Create initial solution
        current_solution = self._create_initial_solution()
        current_cost = evaluate_solution(current_solution, problem)
        current_solution.cost = current_cost
        
        best_solution = current_solution.copy()
        best_cost = current_cost
        
        # Initialize temperature
        temperature = self.initial_temp
        
        # Annealing process
        for iteration in range(self.max_iterations):
            # Get neighbor
            neighbor = self._get_neighbor(current_solution)
            neighbor_cost = evaluate_solution(neighbor, problem)
            
            # Calculate acceptance probability
            delta = neighbor_cost - current_cost
            
            if delta < 0 or random.random() < math.exp(-delta / temperature):
                current_solution = neighbor
                current_cost = neighbor_cost
                
                if current_cost < best_cost:
                    best_solution = current_solution.copy()
                    best_cost = current_cost
            
            # Cool down
            temperature = self._update_temperature(iteration, temperature)
            
            if temperature < self.final_temp:
                break
        
        return best_solution.to_entries()
    
    def _create_initial_solution(self) -> Solution:
        """Create initial solution."""
        solution = create_empty_solution(self.problem)
        
        current = self.problem.start_date
        while current <= self.problem.end_date:
            for shift in self.problem.shifts:
                key = (current, shift.id)
                available = [
                    emp.id for emp in self.problem.employees
                    if is_employee_available(emp.id, current, shift, solution,
                                           self.problem, self.weeks)
                ]
                
                if len(available) >= shift.min_staff:
                    count = random.randint(
                        shift.min_staff,
                        min(shift.max_staff, len(available))
                    )
                    solution.assignments[key] = random.sample(available, count)
                # else: leave unassigned (empty)
            
            current += timedelta(days=1)
        
        return solution
    
    def _get_neighbor(self, solution: Solution) -> Solution:
        """Generate neighbor solution."""
        neighbor = solution.copy()
        
        # Choose random date and shift
        all_keys = list(neighbor.assignments.keys())
        date, shift_id = random.choice(all_keys)
        shift = self.problem.shift_by_id[shift_id]
        
        # Choose operation
        operations = ['add', 'remove', 'swap', 'move']
        operation = random.choice(operations)
        
        if operation == 'add':
            current_staff = neighbor.assignments[(date, shift_id)]
            if len(current_staff) < shift.max_staff:
                available = [
                    emp.id for emp in self.problem.employees
                    if emp.id not in current_staff and
                    is_employee_available(emp.id, date, shift, neighbor,
                                        self.problem, self.weeks)
                ]
                if available:
                    neighbor.assignments[(date, shift_id)].append(
                        random.choice(available)
                    )
        
        elif operation == 'remove':
            current_staff = neighbor.assignments[(date, shift_id)]
            if len(current_staff) > shift.min_staff:
                neighbor.assignments[(date, shift_id)].remove(
                    random.choice(current_staff)
                )
        
        elif operation == 'swap':
            # Swap employees between two shifts
            date2, shift2_id = random.choice(all_keys)
            shift2 = self.problem.shift_by_id[shift2_id]
            
            staff1 = neighbor.assignments[(date, shift_id)]
            staff2 = neighbor.assignments[(date2, shift2_id)]
            
            if staff1 and staff2:
                emp1 = random.choice(staff1)
                emp2 = random.choice(staff2)
                
                # Try swap
                neighbor.assignments[(date, shift_id)].remove(emp1)
                neighbor.assignments[(date, shift_id)].append(emp2)
                neighbor.assignments[(date2, shift2_id)].remove(emp2)
                neighbor.assignments[(date2, shift2_id)].append(emp1)
                
                # Validate swap
                valid1 = is_employee_available(emp2, date, shift, neighbor,
                                             self.problem, self.weeks)
                valid2 = is_employee_available(emp1, date2, shift2, neighbor,
                                             self.problem, self.weeks)
                
                if not (valid1 and valid2):
                    # Revert swap
                    neighbor.assignments[(date, shift_id)].remove(emp2)
                    neighbor.assignments[(date, shift_id)].append(emp1)
                    neighbor.assignments[(date2, shift2_id)].remove(emp1)
                    neighbor.assignments[(date2, shift2_id)].append(emp2)
        
        elif operation == 'move':
            # Move employee to different shift
            current_staff = neighbor.assignments[(date, shift_id)]
            if current_staff:
                emp_id = random.choice(current_staff)
                neighbor.assignments[(date, shift_id)].remove(emp_id)
                
                # Find new shift
                target_date = random.choice(list(range(
                    (self.problem.end_date - self.problem.start_date).days + 1
                )))
                target_date = self.problem.start_date + timedelta(days=target_date)
                target_shift = random.choice(self.problem.shifts)
                
                if len(neighbor.assignments[(target_date, target_shift.id)]) < target_shift.max_staff:
                    if is_employee_available(emp_id, target_date, target_shift,
                                           neighbor, self.problem, self.weeks):
                        neighbor.assignments[(target_date, target_shift.id)].append(emp_id)
                    else:
                        # Revert if invalid
                        neighbor.assignments[(date, shift_id)].append(emp_id)
                else:
                    # Revert if full
                    neighbor.assignments[(date, shift_id)].append(emp_id)
        
        return neighbor
    
    def _update_temperature(self, iteration: int, current_temp: float) -> float:
        """Update temperature based on cooling schedule."""
        if self.cooling_schedule == CoolingSchedule.EXPONENTIAL:
            return current_temp * self.cooling_rate
        
        elif self.cooling_schedule == CoolingSchedule.LINEAR:
            beta = (self.initial_temp - self.final_temp) / self.max_iterations
            return self.initial_temp - beta * (iteration + 1)
        
        elif self.cooling_schedule == CoolingSchedule.LOGARITHMIC:
            return max(self.final_temp, self.initial_temp / math.log(2 + iteration))
        
        return current_temp