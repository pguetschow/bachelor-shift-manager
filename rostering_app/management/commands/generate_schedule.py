from django.core.management.base import BaseCommand
from rostering_app.models import Employee, ShiftType, ScheduleEntry
from datetime import datetime, timedelta
from pulp import LpProblem, LpVariable, lpSum, LpMinimize, LpBinary, PULP_CBC_CMD
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import seaborn as sns


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

        # Generate images
        self.generate_schedule_image(employees, days)
        self.generate_shift_staffing_image(employees, days, shift_types)

    def generate_schedule_image(self, employees, days, filename="export/shift_schedule.png"):
        export_dir = os.path.dirname(filename)
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)

        all_employees = [employee.name for employee in employees]
        all_days = [day['date'].isoformat() for day in days]
        df = pd.DataFrame(index=all_employees, columns=all_days)

        from rostering_app.models import ScheduleEntry
        for employee in employees:
            for day in days:
                entry = ScheduleEntry.objects.filter(employee=employee, date=day['date'], archived=False).first()
                if entry:
                    df.loc[employee.name, day['date'].isoformat()] = entry.shift_type.name
                elif day['date'].isoformat() in employee.absences:
                    df.loc[employee.name, day['date'].isoformat()] = 'Absent'
                else:
                    df.loc[employee.name, day['date'].isoformat()] = 'Off'

        colors = {
            'EarlyShift': 'skyblue',
            'LateShift': 'palegreen',
            'NightShift': 'salmon',
            'Absent': 'red',
            'Off': 'lightgrey'
        }
        color_codes = {state: code for code, state in enumerate(colors.keys(), start=1)}
        df_numeric = df.replace(color_codes)

        fig, ax = plt.subplots(figsize=(15, len(all_employees) * 0.5))
        sns.heatmap(df_numeric, cmap=mcolors.ListedColormap(list(colors.values())), cbar=False,
                    ax=ax, linewidths=.5, linecolor='black')
        ax.set_yticklabels(all_employees, rotation=0)
        ax.set_xticklabels(all_days, rotation=45, ha='right')
        ax.set_title('Employee Shift Schedule')

        # Create legend
        patches = [plt.Line2D([0], [0], color=colors[label], lw=4, label=label) for label in colors]
        ax.legend(handles=patches, bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        plt.savefig(filename)
        self.stdout.write(f"Schedule image saved as {filename}")

    def generate_shift_staffing_image(self, employees, days, shift_types, filename="export/shift_staffing.png"):
        all_days = [day['date'].isoformat() for day in days]
        all_shifts = [shift.name for shift in shift_types]
        df = pd.DataFrame(index=all_shifts, columns=all_days)

        from rostering_app.models import ScheduleEntry
        for day in days:
            for shift in day['shifts']:
                count = ScheduleEntry.objects.filter(date=day['date'], shift_type=shift, archived=False).count()
                df.at[shift.name, day['date'].isoformat()] = self.get_shift_status(count, shift)

        colors = {
            'No employees assigned': 'darkred',
            'Understaffed': 'red',
            'Min staffed': 'orange',
            'In between': 'yellow',
            'Max staffed': 'green'
        }
        color_codes = {state: idx for idx, state in enumerate(colors.keys())}
        df_numeric = df.replace(color_codes)

        fig, ax = plt.subplots(figsize=(15, 2))
        sns.heatmap(df_numeric.astype(float), cmap=mcolors.ListedColormap(list(colors.values())),
                    cbar=False, ax=ax, linewidths=.5, linecolor='black', annot=True, fmt='')
        ax.set_xticklabels(all_days, rotation=45, ha='right')
        ax.set_yticklabels(all_shifts, rotation=0)
        ax.set_title('Shift Staffing Levels')
        patches = [plt.Line2D([0], [0], color=colors[label], lw=4, label=label) for label in colors]
        ax.legend(handles=patches, bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        plt.savefig(filename)
        self.stdout.write(f"Shift staffing image saved as {filename}")

    def get_shift_status(self, assigned_count, shift):
        if assigned_count == 0:
            return 'No employees assigned'
        elif assigned_count < shift.min_staff:
            return 'Understaffed'
        elif assigned_count == shift.min_staff:
            return 'Min staffed'
        elif assigned_count == shift.max_staff:
            return 'Max staffed'
        else:
            return 'In between'
