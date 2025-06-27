"""Base classes and interfaces for scheduling algorithms."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, time
from typing import List, Dict, Set, Tuple, Optional


@dataclass
class Employee:
    """Employee data structure."""
    id: int
    name: str
    max_hours_per_week: int
    absence_dates: Set[date]
    preferred_shifts: List[str]


@dataclass
class ShiftType:
    """Shift type data structure."""
    id: int
    name: str
    start: time
    end: time
    min_staff: int
    max_staff: int
    duration: float  # Pre-calculated duration in hours


@dataclass
class ScheduleEntry:
    """Single schedule entry."""
    employee_id: int
    date: date
    shift_id: int


@dataclass
class SchedulingProblem:
    """Problem definition for scheduling."""
    employees: List[Employee]
    shift_types: List[ShiftType]
    start_date: date
    end_date: date
    
    def __post_init__(self):
        """Create helper structures."""
        self.emp_by_id = {e.id: e for e in self.employees}
        self.shift_by_id = {s.id: s for s in self.shift_types}


class SchedulingAlgorithm(ABC):
    """Abstract base class for scheduling algorithms."""
    
    @abstractmethod
    def solve(self, problem: SchedulingProblem) -> List[ScheduleEntry]:
        """Solve the scheduling problem and return list of schedule entries."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Algorithm name for display."""
        pass


class Solution:
    """Solution representation used by heuristic algorithms."""
    
    def __init__(self):
        # (date, shift_id) -> [employee_ids]
        self.assignments: Dict[Tuple[date, int], List[int]] = {}
        self.cost: float = float('inf')
    
    def to_entries(self) -> List[ScheduleEntry]:
        """Convert to list of schedule entries."""
        entries = []
        for (date, shift_id), emp_ids in self.assignments.items():
            for emp_id in emp_ids:
                entries.append(ScheduleEntry(emp_id, date, shift_id))
        return entries
    
    def copy(self) -> 'Solution':
        """Create a deep copy of the solution."""
        new_sol = Solution()
        new_sol.assignments = {k: v.copy() for k, v in self.assignments.items()}
        new_sol.cost = self.cost
        return new_sol
