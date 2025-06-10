from datetime import date, timedelta
from django.core.management.base import BaseCommand
from rostering_app.models import Employee, ShiftType, ScheduleEntry
import random

class Command(BaseCommand):
    help = "Generate employee schedule using a balanced heuristic (greedy) approach for a full year with weekly constraints"

    def handle(self, *args, **options):
        self.stdout.write("Generating yearly schedule using balanced heuristic approach...")
        # Archive previous (non-archived) schedule entries.
        ScheduleEntry.objects.filter(archived=False).update(archived=True)

        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())

        # Define the scheduling period: full year from 2025-01-01 to 2025-12-31.
        start_date = date(2025, 1, 1)
        end_date = date(2025, 12, 31)
        num_days = (end_date - start_date).days + 1
        days = [start_date + timedelta(days=i) for i in range(num_days)]

        # Dictionary to track weekly hours per employee.
        # Key: (employee.id, (iso_year, iso_week)), Value: cumulative hours for that week.
        weekly_hours = {}

        # For each day, assign shifts in a balanced manner.
        for day in days:
            # Identify the ISO week for the current day.
            week_key = day.isocalendar()[:2]  # (iso_year, iso_week)

            # Get all employees available on this day (i.e. not marked as absent).
            available_employees = [emp for emp in employees if day.isoformat() not in emp.absences]
            # Keep track of which employees have been assigned already for the day.
            assigned_employees = set()

            # Shuffle the shifts to randomize assignment order.
            shifts = shift_types.copy()
            random.shuffle(shifts)

            for shift in shifts:
                # Determine the pool of employees for this shift:
                # available, not yet assigned today, and with enough remaining weekly hours.
                pool = [
                    emp for emp in available_employees
                    if emp.id not in assigned_employees and
                       (weekly_hours.get((emp.id, week_key), 0) + shift.get_duration() <= emp.max_hours_per_week)
                ]
                if not pool:
                    # No eligible employees available for this shift.
                    continue

                # Determine the number of employees to assign:
                max_possible = min(shift.max_staff, len(pool))
                if len(pool) < shift.min_staff:
                    # Not enough available employees to meet the minimum requirement; assign as many as possible.
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
                    # Mark employee as assigned for the day.
                    assigned_employees.add(emp.id)
                    # Update the employee's weekly hours.
                    weekly_hours[(emp.id, week_key)] = weekly_hours.get((emp.id, week_key), 0) + shift.get_duration()

        self.stdout.write(self.style.SUCCESS("Yearly balanced heuristic schedule generated successfully."))
