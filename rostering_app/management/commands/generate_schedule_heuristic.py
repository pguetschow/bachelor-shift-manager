from datetime import date, timedelta

from django.core.management.base import BaseCommand

from rostering_app.models import Employee, ShiftType, ScheduleEntry


class Command(BaseCommand):
    help = "Generate employee schedule using a heuristic (greedy) approach"

    def handle(self, *args, **options):
        self.stdout.write("Generating schedule using heuristic approach...")
        # Archive previous (non-archived) schedule entries.
        ScheduleEntry.objects.filter(archived=False).update(archived=True)

        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())

        # Define the scheduling period (fixture month: 28 days starting from 2024-02-01).
        start_date = date(2024, 2, 1)
        num_days = 28
        days = [start_date + timedelta(days=i) for i in range(num_days)]

        # For each day and for each shift, assign employees using a two-pass heuristic.
        for day in days:
            for shift in shift_types:
                assigned = 0
                # First pass: assign employees until the minimum staffing is reached.
                for emp in employees:
                    # Skip if employee is absent on that day.
                    if day.isoformat() in emp.absences:
                        continue
                    # Skip if employee already has an assignment for this day.
                    if ScheduleEntry.objects.filter(employee=emp, date=day, archived=False).exists():
                        continue
                    if assigned < shift.min_staff:
                        ScheduleEntry.objects.create(
                            employee=emp,
                            date=day,
                            shift_type=shift,
                            archived=False
                        )
                        assigned += 1
                # Second pass: assign additional employees until reaching maximum staffing.
                for emp in employees:
                    if assigned >= shift.max_staff:
                        break
                    if day.isoformat() in emp.absences:
                        continue
                    if ScheduleEntry.objects.filter(employee=emp, date=day, archived=False).exists():
                        continue
                    ScheduleEntry.objects.create(
                        employee=emp,
                        date=day,
                        shift_type=shift,
                        archived=False
                    )
                    assigned += 1

        self.stdout.write(self.style.SUCCESS("Schedule generated successfully."))