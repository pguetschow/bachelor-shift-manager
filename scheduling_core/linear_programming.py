"""Linear programming based scheduling algorithm."""
from datetime import timedelta
from collections import defaultdict
from typing import List

from pulp import LpProblem, LpVariable, lpSum, LpMinimize, LpBinary, PULP_CBC_CMD

from .base import SchedulingAlgorithm, SchedulingProblem, ScheduleEntry, Shift
from .utils import get_weeks


class LinearProgrammingScheduler(SchedulingAlgorithm):
    """Scheduling using integer linear programming."""
    
    @property
    def name(self) -> str:
        return "Linear Programming (ILP)"
    
    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:
        """Solve scheduling problem using linear programming."""
        # Create LP problem
        lp_problem = LpProblem("EmployeeScheduling", LpMinimize)
        
        # Decision variables: x[emp_id, date, shift_id]
        variables = {}
        total_days = (problem.end_date - problem.start_date).days + 1
        
        for emp in problem.employees:
            current = problem.start_date
            for _ in range(total_days):
                for shift in problem.shifts:
                    key = (emp.id, current, shift.id)
                    variables[key] = LpVariable(
                        f"x_{emp.id}_{current}_{shift.id}",
                        0, 1, LpBinary
                    )
                current += timedelta(days=1)
        
        # Helper variables for fairness
        emp_total_hours = {}
        emp_overtime = {}
        emp_undertime = {}
        
        for emp in problem.employees:
            emp_total_hours[emp.id] = LpVariable(f"total_hours_{emp.id}", 0)
            emp_overtime[emp.id] = LpVariable(f"overtime_{emp.id}", 0)
            emp_undertime[emp.id] = LpVariable(f"undertime_{emp.id}", 0)
        
        # Calculate target hours
        total_possible_hours = 0
        current = problem.start_date
        for _ in range(total_days):
            for shift in problem.shifts:
                total_possible_hours += shift.duration * shift.max_staff
            current += timedelta(days=1)
        
        total_capacity_hours = sum(
            emp.max_hours_per_week * ((total_days + 6) // 7)
            for emp in problem.employees
        )
        
        target_total_hours = min(total_possible_hours, total_capacity_hours)
        avg_hours_per_emp = target_total_hours / len(problem.employees) if problem.employees else 0

        # Constraints
        
        # 1. Absences
        for emp in problem.employees:
            for absence_date in emp.absence_dates:
                if problem.start_date <= absence_date <= problem.end_date:
                    for shift in problem.shifts:
                        if (emp.id, absence_date, shift.id) in variables:
                            lp_problem += variables[(emp.id, absence_date, shift.id)] == 0
        
        # 2. One shift per day per employee
        for emp in problem.employees:
            current = problem.start_date
            for _ in range(total_days):
                day_vars = []
                for shift in problem.shifts:
                    key = (emp.id, current, shift.id)
                    if key in variables:
                        day_vars.append(variables[key])
                if day_vars:
                    lp_problem += lpSum(day_vars) <= 1
                current += timedelta(days=1)
        
        # 3. Min/max staffing
        current = problem.start_date
        for _ in range(total_days):
            for shift in problem.shifts:
                shift_vars = []
                for emp in problem.employees:
                    key = (emp.id, current, shift.id)
                    if key in variables:
                        shift_vars.append(variables[key])
                if shift_vars:
                    lp_problem += lpSum(shift_vars) >= shift.min_staff
                    lp_problem += lpSum(shift_vars) <= shift.max_staff
            current += timedelta(days=1)
        
        # 4. Weekly hours limit
        weeks = get_weeks(problem.start_date, problem.end_date)
        for emp in problem.employees:
            for week_dates in weeks.values():
                week_hours = []
                for date in week_dates:
                    for shift in problem.shifts:
                        key = (emp.id, date, shift.id)
                        if key in variables:
                            week_hours.append(variables[key] * shift.duration)
                if week_hours:
                    lp_problem += lpSum(week_hours) <= emp.max_hours_per_week
        
        # 5. 11-hour rest period
        current = problem.start_date
        for day_idx in range(total_days - 1):
            next_date = current + timedelta(days=1)
            for emp in problem.employees:
                for today_shift in problem.shifts:
                    for tomorrow_shift in problem.shifts:
                        if self._violates_rest_period(today_shift, tomorrow_shift, current):
                            today_key = (emp.id, current, today_shift.id)
                            tomorrow_key = (emp.id, next_date, tomorrow_shift.id)
                            if today_key in variables and tomorrow_key in variables:
                                lp_problem += (variables[today_key] + 
                                             variables[tomorrow_key]) <= 1
            current += timedelta(days=1)
        
        # 6. Calculate total hours
        for emp in problem.employees:
            total_hours = []
            current = problem.start_date
            for _ in range(total_days):
                for shift in problem.shifts:
                    key = (emp.id, current, shift.id)
                    if key in variables:
                        total_hours.append(variables[key] * shift.duration)
                current += timedelta(days=1)
            if total_hours:
                lp_problem += emp_total_hours[emp.id] == lpSum(total_hours)
        
        # 7. Over/undertime for fairness
        for emp in problem.employees:
            max_hours = emp.max_hours_per_week * ((total_days + 6) // 7)
            target = min(max_hours, avg_hours_per_emp)
            lp_problem += (emp_total_hours[emp.id] - target == 
                          emp_overtime[emp.id] - emp_undertime[emp.id])
        
        # Objective function
        maximize_coverage = []
        preference_bonus = []
        
        for emp in problem.employees:
            current = problem.start_date
            for _ in range(total_days):
                for shift in problem.shifts:
                    key = (emp.id, current, shift.id)
                    if key in variables:
                        maximize_coverage.append(variables[key])
                        if shift.name in emp.preferred_shifts:
                            preference_bonus.append(variables[key])
                current += timedelta(days=1)
        
        fairness_penalty = lpSum([emp_overtime[emp.id] + emp_undertime[emp.id] 
                                 for emp in problem.employees])
        
        # Weighted objective
        lp_problem += (-lpSum(maximize_coverage) * 10000 +  # Maximize coverage
                      fairness_penalty * 100 +              # Fairness
                      -lpSum(preference_bonus) * 1)         # Preferences
        
        # Solve
        lp_problem.solve(PULP_CBC_CMD(msg=False, timeLimit=300))
        
        # Extract solution
        entries = []
        if lp_problem.status == 1:  # Optimal
            for (emp_id, date, shift_id), var in variables.items():
                if var.varValue == 1:
                    entries.append(ScheduleEntry(emp_id, date, shift_id))
        
        return entries
    
    def _violates_rest_period(self, shift1: Shift, shift2: Shift, date1) -> bool:
        """Check if shift combination violates 11-hour rest period."""
        from datetime import datetime
        
        end1 = datetime.combine(date1, shift1.end)
        start2 = datetime.combine(date1 + timedelta(days=1), shift2.start)
        
        if shift1.end < shift1.start:  # Night shift
            end1 += timedelta(days=1)
        
        pause_hours = (start2 - end1).total_seconds() / 3600
        return pause_hours < 11
