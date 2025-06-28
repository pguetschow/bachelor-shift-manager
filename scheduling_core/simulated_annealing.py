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
    
    def __init__(self, initial_temp=1000, final_temp=1, max_iterations=1000,
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
        """Solve using simulated annealing."""
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
        max_iterations = 1000  # Safety check to prevent infinite loops
        iteration_count = 0
        
        while current <= self.problem.end_date and iteration_count < max_iterations:
            for shift in self.problem.shifts:
                key = (current, shift.id)
                available = [
                    emp.id for emp in self.problem.employees
                    if (emp.id not in [eid for eids in solution.assignments.values() for eid in eids] and
                        current not in emp.absence_dates and
                        not self._is_non_working_day(current))
                ]
                
                if len(available) >= shift.min_staff:
                    count = random.randint(
                        shift.min_staff,
                        min(shift.max_staff, len(available))
                    )
                    solution.assignments[key] = random.sample(available, count)
                # else: leave unassigned (empty)
            
            current += timedelta(days=1)
            iteration_count += 1
        
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
                    current_staff.count(emp.id) == 0 and
                    date not in emp.absence_dates and
                    not self._is_non_working_day(date)
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
            # Swap employees between shifts
            if len(all_keys) >= 2:
                key1, key2 = random.sample(all_keys, 2)
                staff1 = neighbor.assignments[key1]
                staff2 = neighbor.assignments[key2]
                
                if staff1 and staff2:
                    emp1 = random.choice(staff1)
                    emp2 = random.choice(staff2)
                    
                    # Check if swap is valid
                    date1, shift_id1 = key1
                    date2, shift_id2 = key2
                    shift1 = self.problem.shift_by_id[shift_id1]
                    shift2 = self.problem.shift_by_id[shift_id2]
                    
                    emp1_obj = next(emp for emp in self.problem.employees if emp.id == emp1)
                    emp2_obj = next(emp for emp in self.problem.employees if emp.id == emp2)
                    
                    if (date2 not in emp1_obj.absence_dates and 
                        date1 not in emp2_obj.absence_dates and
                        not self._is_non_working_day(date1) and
                        not self._is_non_working_day(date2)):
                        
                        neighbor.assignments[key1].remove(emp1)
                        neighbor.assignments[key2].remove(emp2)
                        neighbor.assignments[key1].append(emp2)
                        neighbor.assignments[key2].append(emp1)
        
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
                    emp_obj = next(emp for emp in self.problem.employees if emp.id == emp_id)
                    if (target_date not in emp_obj.absence_dates and
                        not self._is_non_working_day(target_date)):
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
            return self.initial_temp * (self.final_temp / self.initial_temp) ** (iteration / self.max_iterations)
        elif self.cooling_schedule == CoolingSchedule.LINEAR:
            return self.initial_temp - (self.initial_temp - self.final_temp) * (iteration / self.max_iterations)
        elif self.cooling_schedule == CoolingSchedule.LOGARITHMIC:
            return self.initial_temp / (1 + iteration)
        else:
            return current_temp