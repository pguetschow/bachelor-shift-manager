from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from pulp import LpProblem, LpVariable, lpSum, LpMinimize, LpBinary, PULP_CBC_CMD

from rostering_app.models import Employee, ShiftType, ScheduleEntry


class Command(BaseCommand):
    help = 'Generate employee rostering schedule'

    def handle(self, *args, **kwargs):
        # Archive previous schedule entries
        ScheduleEntry.objects.filter(archived=False).update(archived=True)

        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())

        # Scheduling period
        start_date = datetime.strptime('2024-02-01', '%Y-%m-%d').date()
        num_days = 28
        days = []
        for i in range(num_days):
            day_date = start_date + timedelta(days=i)
            # For simplicity, every day offers all shift types.
            days.append({'date': day_date, 'shifts': shift_types})

        # Setup the optimization problem
        problem = LpProblem("Employee Rostering", LpMinimize)
        variables = {}

        # Create decision variables for each employee, day, and shift
        for employee in employees:
            for day in days:
                for shift in day['shifts']:
                    key = (employee.id, day['date'], shift.id)
                    variables[key] = LpVariable(f"x_{employee.id}_{day['date']}_{shift.id}", 0, 1, LpBinary)

        # Weekly hour constraints
        for employee in employees:
            for week_start in range(0, num_days, 7):
                week_days = days[week_start:week_start + 7]
                problem += lpSum(
                    variables[(employee.id, day['date'], shift.id)] * shift.get_duration()
                    for day in week_days for shift in day['shifts']
                ) <= employee.max_hours_per_week, f"MaxWeeklyHours_{employee.id}_week_{week_start // 7}"

        # Staffing constraints for each shift in each day
        for day in days:
            for shift in day['shifts']:
                problem += lpSum(
                    variables[(employee.id, day['date'], shift.id)] for employee in employees
                ) >= shift.min_staff, f"MinStaff_{day['date']}_{shift.id}"
                problem += lpSum(
                    variables[(employee.id, day['date'], shift.id)] for employee in employees
                ) <= shift.max_staff, f"MaxStaff_{day['date']}_{shift.id}"

        # Ensure one shift per day and enforce absences
        for employee in employees:
            for day in days:
                problem += lpSum(
                    variables[(employee.id, day['date'], shift.id)] for shift in day['shifts']
                ) <= 1, f"OneShiftPerDay_{employee.id}_{day['date']}"

                # Enforce absences (ISO date strings)
                if day['date'].isoformat() in employee.absences:
                    for shift in day['shifts']:
                        problem += variables[(
                        employee.id, day['date'], shift.id)] == 0, f"Absence_{employee.id}_{day['date']}_{shift.id}"

        # Simplified objective: maximize total assigned hours (minimize negative total)
        total_hours_worked = lpSum(
            variables[(employee.id, day['date'], shift.id)] * shift.get_duration()
            for employee in employees for day in days for shift in day['shifts']
        )
        problem += -total_hours_worked, "Objective"

        problem.solve(PULP_CBC_CMD(msg=True))

        # Save new schedule entries to the database
        for employee in employees:
            for day in days:
                for shift in day['shifts']:
                    var = variables[(employee.id, day['date'], shift.id)]
                    if var.varValue == 1:
                        ScheduleEntry.objects.create(
                            employee=employee,
                            date=day['date'],
                            shift_type=shift,
                            archived=False
                        )

        self.stdout.write(self.style.SUCCESS("Schedule generated successfully."))