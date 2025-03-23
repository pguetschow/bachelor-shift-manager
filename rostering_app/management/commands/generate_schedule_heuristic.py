from datetime import date, timedelta
from django.core.management.base import BaseCommand
from rostering_app.models import Employee, ShiftType, ScheduleEntry
import random

class Command(BaseCommand):
    help = "Generate employee schedule using a balanced heuristic (greedy) approach"

    def handle(self, *args, **options):
        self.stdout.write("Generating schedule using balanced heuristic approach...")
        # Archive previous (non-archived) schedule entries.
        ScheduleEntry.objects.filter(archived=False).update(archived=True)

        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())

        # Define the scheduling period (fixture month: 28 days starting from 2024-02-01).
        start_date = date(2024, 2, 1)
        num_days = 28
        days = [start_date + timedelta(days=i) for i in range(num_days)]

        # For each day, assign shifts in a balanced manner.
        for day in days:
            # Get all employees available on this day (i.e. not absent)
            available_employees = [emp for emp in employees if day.isoformat() not in emp.absences]
            # Keep track of which employees have been assigned already for the day.
            assigned_employees = set()

            # Shuffle the shifts to randomize assignment order.
            shifts = shift_types.copy()
            random.shuffle(shifts)

            for shift in shifts:
                # Determine the pool of employees for this shift (available and not yet assigned)
                pool = [emp for emp in available_employees if emp.id not in assigned_employees]
                if not pool:
                    # No one left available to assign for this shift.
                    continue

                # Determine how many employees to assign:
                max_possible = min(shift.max_staff, len(pool))
                if len(pool) < shift.min_staff:
                    # If not enough employees available to meet minimum, assign as many as possible.
                    num_to_assign = len(pool)
                else:
                    num_to_assign = random.randint(shift.min_staff, max_possible)

                # Randomly choose employees from the pool.
                chosen = random.sample(pool, num_to_assign)
                for emp in chosen:
                    ScheduleEntry.objects.create(
                        employee=emp,
                        date=day,
                        shift_type=shift,
                        archived=False
                    )
                    assigned_employees.add(emp.id)

        self.stdout.write(self.style.SUCCESS("Balanced heuristic schedule generated successfully."))
