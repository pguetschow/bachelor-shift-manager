from datetime import date
from typing import Set, List

from rostering_app.models import Employee as DjangoEmployee, Shift as DjangoShift, ScheduleEntry as DjangoScheduleEntry
from scheduling_core.base import Employee as CoreEmployee, Shift as CoreShift, ScheduleEntry as CoreScheduleEntry


def employee_to_core(employee: DjangoEmployee) -> CoreEmployee:
    """
    Convert a Django Employee model instance to a core Employee dataclass.
    Handles conversion of absences (list of ISO strings) to set of date objects.
    """
    absences_raw = getattr(employee, 'absences', [])
    absence_dates: Set[date] = set()
    for d in absences_raw:
        try:
            absence_dates.add(date.fromisoformat(d))
        except Exception:
            pass
    preferred_shifts = getattr(employee, 'preferred_shifts', [])
    return CoreEmployee(
        id=int(getattr(employee, 'id')),
        name=str(getattr(employee, 'name')),
        max_hours_per_week=int(getattr(employee, 'max_hours_per_week')),
        absence_dates=absence_dates,
        preferred_shifts=preferred_shifts,
    )


def shift_to_core(shift: DjangoShift) -> CoreShift:
    """
    Convert a Django Shift model instance to a core Shift dataclass.
    """
    # start and end are already Python time objects from TimeField
    return CoreShift(
        id=int(getattr(shift, 'id')),
        name=str(getattr(shift, 'name')),
        start=getattr(shift, 'start'),
        end=getattr(shift, 'end'),
        min_staff=int(getattr(shift, 'min_staff')),
        max_staff=int(getattr(shift, 'max_staff')),
        duration=float(shift.get_duration()) if hasattr(shift, 'get_duration') else 0.0,
    )


def scheduleentry_to_core(entry: DjangoScheduleEntry) -> CoreScheduleEntry:
    """
    Convert a Django ScheduleEntry model instance to a core ScheduleEntry dataclass.
    """
    return CoreScheduleEntry(
        employee_id=int(getattr(entry.employee, 'id')),
        date=getattr(entry, 'date'),
        shift_id=int(getattr(entry.shift, 'id')),
    )


def employees_to_core(employees: List[DjangoEmployee]) -> List[CoreEmployee]:
    return [employee_to_core(e) for e in employees]


def shifts_to_core(shifts: List[DjangoShift]) -> List[CoreShift]:
    return [shift_to_core(s) for s in shifts]


def scheduleentries_to_core(entries: List[DjangoScheduleEntry]) -> List[CoreScheduleEntry]:
    return [scheduleentry_to_core(e) for e in entries]
