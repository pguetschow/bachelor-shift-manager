"""Shared utilities for scheduling algorithms."""
from datetime import datetime, timedelta, date
from typing import Dict, List, Tuple, Set
from collections import defaultdict
from .base import Employee, Shift, Solution, SchedulingProblem


def get_weeks(start_date: date, end_date: date) -> Dict[Tuple[int, int], List[date]]:
    """Group dates by ISO week."""
    weeks = defaultdict(list)
    current = start_date
    while current <= end_date:
        iso = current.isocalendar()
        weeks[(iso[0], iso[1])].append(current)
        current += timedelta(days=1)
    return dict(weeks)


def is_employee_available(
    emp_id: int,
    date: date,
    shift: Shift,
    solution: Solution,
    problem: SchedulingProblem,
    weeks: Dict[Tuple[int, int], List[date]]
) -> bool:
    """Check if employee can be assigned to shift."""
    emp = problem.emp_by_id[emp_id]
    
    # Check absence
    if date in emp.absence_dates:
        return False
    
    # Check if already assigned on same day
    for s in problem.shifts:
        if emp_id in solution.assignments.get((date, s.id), []):
            return False
    
    # Check weekly hours
    week_key = tuple(date.isocalendar()[:2])
    weekly_hours = 0
    for d in weeks[week_key]:
        for s in problem.shifts:
            if emp_id in solution.assignments.get((d, s.id), []):
                weekly_hours += s.duration
    
    if weekly_hours + shift.duration > emp.max_hours_per_week:
        return False
    
    # Check 11-hour rest period
    if not check_rest_period(emp_id, date, shift, solution, problem):
        return False
    
    return True


def check_rest_period(
    emp_id: int,
    date: date,
    shift: Shift,
    solution: Solution,
    problem: SchedulingProblem
) -> bool:
    """Check 11-hour rest period between shifts."""
    # Check previous day
    prev_date = date - timedelta(days=1)
    for s in problem.shifts:
        if emp_id in solution.assignments.get((prev_date, s.id), []):
            end_prev = datetime.combine(prev_date, s.end)
            if s.end < s.start:  # Night shift
                end_prev += timedelta(days=1)
            start_curr = datetime.combine(date, shift.start)
            if (start_curr - end_prev).total_seconds() / 3600 < 11:
                return False
    
    # Check next day
    next_date = date + timedelta(days=1)
    for s in problem.shifts:
        if emp_id in solution.assignments.get((next_date, s.id), []):
            end_curr = datetime.combine(date, shift.end)
            if shift.end < shift.start:  # Night shift
                end_curr += timedelta(days=1)
            start_next = datetime.combine(next_date, s.start)
            if (start_next - end_curr).total_seconds() / 3600 < 11:
                return False
    
    return True


def evaluate_solution(
    solution: Solution,
    problem: SchedulingProblem,
    penalty_weights: Dict[str, float] = None
) -> float:
    """Evaluate solution quality (lower is better)."""
    if penalty_weights is None:
        penalty_weights = {
            'understaffing': 10000,
            'overstaffing': 10000,
            'fairness': 10,
            'preference_bonus': -1,
            'coverage_bonus': -10
        }
    
    penalty = 0
    
    # Check staffing levels
    total_days = (problem.end_date - problem.start_date).days + 1
    current = problem.start_date
    
    for _ in range(total_days):
        for shift in problem.shifts:
            assigned = len(solution.assignments.get((current, shift.id), []))
            if assigned < shift.min_staff:
                penalty += (shift.min_staff - assigned) * penalty_weights['understaffing']
            elif assigned > shift.max_staff:
                penalty += (assigned - shift.max_staff) * penalty_weights['overstaffing']
        current += timedelta(days=1)
    
    # Calculate fairness (standard deviation of hours)
    emp_hours = defaultdict(float)
    for (d, sid), emp_ids in solution.assignments.items():
        shift = problem.shift_by_id[sid]
        for emp_id in emp_ids:
            emp_hours[emp_id] += shift.duration
    
    if emp_hours:
        hours_list = list(emp_hours.values())
        avg_hours = sum(hours_list) / len(hours_list)
        for h in hours_list:
            penalty += abs(h - avg_hours) * penalty_weights['fairness']
    
    # Preference bonus
    for (d, sid), emp_ids in solution.assignments.items():
        shift = problem.shift_by_id[sid]
        for emp_id in emp_ids:
            emp = problem.emp_by_id[emp_id]
            if shift.name in emp.preferred_shifts:
                penalty += penalty_weights['preference_bonus']
    
    # Coverage bonus (encourage filling shifts)
    total_assignments = sum(len(emp_ids) for emp_ids in solution.assignments.values())
    penalty += total_assignments * penalty_weights['coverage_bonus']
    
    return penalty


def create_empty_solution(problem: SchedulingProblem) -> Solution:
    """Create an empty solution with all possible date-shift combinations."""
    solution = Solution()
    current = problem.start_date
    while current <= problem.end_date:
        for shift in problem.shifts:
            solution.assignments[(current, shift.id)] = []
        current += timedelta(days=1)
    return solution
