"""Scheduling core algorithms - pure Python implementation independent of Django."""

from .base import (
    Employee,
    ScheduleEntry,
    SchedulingProblem,
)

from .linear_programming import LinearProgrammingScheduler
from .genetic_algorithm import GeneticAlgorithmScheduler
from .simulated_annealing import SimulatedAnnealingScheduler, CoolingSchedule
from .multi_ga import NSGA2Scheduler


__all__ = [
    'Employee',
    'ScheduleEntry',
    'SchedulingProblem',

    # Original algorithms
    'LinearProgrammingScheduler',
    'GeneticAlgorithmScheduler',
    'SimulatedAnnealingScheduler',
    'CoolingSchedule',
    'NSGA2Scheduler',
]