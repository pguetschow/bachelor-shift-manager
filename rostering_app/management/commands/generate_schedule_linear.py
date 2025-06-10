from datetime import datetime, timedelta
from collections import defaultdict
import json

from django.core.management.base import BaseCommand
from pulp import LpProblem, LpVariable, lpSum, LpMinimize, LpBinary, PULP_CBC_CMD

from rostering_app.models import Employee, ShiftType, ScheduleEntry


class Command(BaseCommand):
    help = 'Generate employee rostering schedule for a full year with weekly constraints and compute KPIs and export to JSON'

    def handle(self, *args, **kwargs):
        # Archive previous schedule entries.
        ScheduleEntry.objects.filter(archived=False).update(archived=True)

        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())

        # Define scheduling period: full year from 2025-01-01 to 2025-12-31.
        start_date = datetime.strptime('2025-01-01', '%Y-%m-%d').date()
        end_date = datetime.strptime('2025-12-31', '%Y-%m-%d').date()
        num_days = (end_date - start_date).days + 1

        # Build list of days (each day offers all shift types).
        days = []
        for i in range(num_days):
            day_date = start_date + timedelta(days=i)
            days.append({'date': day_date, 'shifts': shift_types})

        # Group days by ISO week for weekly constraints.
        weeks = defaultdict(list)
        for day in days:
            iso_year, iso_week, _ = day['date'].isocalendar()
            weeks[(iso_year, iso_week)].append(day)

        # Setup the optimization problem.
        problem = LpProblem("Employee_Rostering_Year", LpMinimize)
        variables = {}

        # Create decision variables for each employee, day, and shift.
        for employee in employees:
            for day in days:
                for shift in day['shifts']:
                    key = (employee.id, day['date'], shift.id)
                    variables[key] = LpVariable(
                        f"x_{employee.id}_{day['date']}_{shift.id}",
                        0, 1, LpBinary
                    )

        # Weekly hour constraints: for each employee and each ISO week,
        # total shift duration must not exceed employee.max_hours_per_week.
        for employee in employees:
            for week_key, week_days in weeks.items():
                problem += lpSum(
                    variables[(employee.id, day['date'], shift.id)] * shift.get_duration()
                    for day in week_days for shift in day['shifts']
                ) <= employee.max_hours_per_week, f"MaxWeeklyHours_{employee.id}_week_{week_key}"

        # Staffing constraints for each day and shift.
        for day in days:
            for shift in day['shifts']:
                problem += lpSum(
                    variables[(employee.id, day['date'], shift.id)]
                    for employee in employees
                ) >= shift.min_staff, f"MinStaff_{day['date']}_{shift.id}"
                problem += lpSum(
                    variables[(employee.id, day['date'], shift.id)]
                    for employee in employees
                ) <= shift.max_staff, f"MaxStaff_{day['date']}_{shift.id}"

        # Ensure one shift per day per employee and enforce absences.
        for employee in employees:
            for day in days:
                problem += lpSum(
                    variables[(employee.id, day['date'], shift.id)]
                    for shift in day['shifts']
                ) <= 1, f"OneShiftPerDay_{employee.id}_{day['date']}"
                if day['date'].isoformat() in employee.absences:
                    for shift in day['shifts']:
                        problem += variables[(employee.id, day['date'], shift.id)] == 0, \
                                   f"Absence_{employee.id}_{day['date']}_{shift.id}"

        # Compute total hours worked.
        total_hours_worked = lpSum(
            variables[(employee.id, day['date'], shift.id)] * shift.get_duration()
            for employee in employees for day in days for shift in day['shifts']
        )

        # Preferred shift bonus: reward assignments where the shift's name is in employee.preferred_shifts.
        alpha = 0.05
        preferred_reward = lpSum(
            variables[(employee.id, day['date'], shift.id)]
            for employee in employees
            for day in days
            for shift in day['shifts']
            if shift.name in employee.preferred_shifts
        )

        # Objective: maximize total assigned hours and reward preferred shift assignments.
        problem += -total_hours_worked - alpha * preferred_reward, "Objective"

        # Solve the problem.
        problem.solve(PULP_CBC_CMD(msg=True))

        # Prepare JSON output list
        schedule_json = []

        # Save new schedule entries to the database and JSON list.
        for employee in employees:
            for day in days:
                for shift in day['shifts']:
                    var = variables[(employee.id, day['date'], shift.id)]
                    if var.varValue == 1:
                        # DB entry
                        ScheduleEntry.objects.create(
                            employee=employee,
                            date=day['date'],
                            shift_type=shift,
                            archived=False
                        )
                        # JSON record
                        schedule_json.append({
                            "employee_id": employee.id,
                            "employee_name":employee.name,
                            "date": day['date'].isoformat(),
                            "shift_id": shift.id,
                            "shift_name": shift.name
                        })

        # Write JSON to file
        output_path = 'yearly_schedule.json'
        with open(output_path, 'w') as json_file:
            json.dump(schedule_json, json_file, indent=4)

        self.stdout.write(self.style.SUCCESS(
            f"Yearly schedule generated successfully with preferred shift bonus and exported to {output_path}."
        ))
