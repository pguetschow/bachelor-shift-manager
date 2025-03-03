from datetime import timedelta
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import os
import pandas as pd
import seaborn as sns
from pulp import LpProblem, LpVariable, lpSum, LpMinimize, LpBinary, PULP_CBC_CMD


class Employee:
    def __init__(self, name, max_hours_per_week, absences=None, preferred_shifts=None):
        self.name = name
        self.max_hours_per_week = max_hours_per_week
        self.absences = absences if absences else []
        self.preferred_shifts = preferred_shifts if preferred_shifts else []
        self.assigned_shifts = []
        self.weekly_hours = {}


class ShiftType:
    def __init__(self, name, start, end, min_staff, max_staff):
        self.name = name
        self.start = start
        self.end = end
        self.min_staff = min_staff
        self.max_staff = max_staff

    def get_duration(self):
        start_hour, start_minute = map(int, self.start.split(':'))
        end_hour, end_minute = map(int, self.end.split(':'))
        start_time = start_hour + start_minute / 60
        end_time = end_hour + end_minute / 60
        if end_time < start_time:
            end_time += 24  # Shift crosses midnight
        return end_time - start_time


class Day:
    def __init__(self, date, shift_types):
        self.date = date
        self.shifts = shift_types


class EmployeeRostering:
    def __init__(self, employees, start_date, num_days):
        self.employees = employees
        self.days = [Day((start_date + timedelta(days=i)).strftime('%Y-%m-%d'), shift_types) for i in range(num_days)]
        self.problem = LpProblem("Employee Rostering", LpMinimize)
        self.variables = {}

    def generate_schedule(self):
        for employee in self.employees:
            for day in self.days:
                for shift in day.shifts:
                    self.variables[(employee.name, day.date, shift.name)] = LpVariable(
                        f"x_{employee.name}_{day.date}_{shift.name}", 0, 1, LpBinary
                    )

        for employee in self.employees:
            for week_start in range(0, len(self.days), 7):
                week_days = self.days[week_start:week_start + 7]
                self.problem += (
                    lpSum(
                        self.variables[(employee.name, day.date, shift.name)] * shift.get_duration()
                        for day in week_days
                        for shift in day.shifts
                    ) <= employee.max_hours_per_week,
                    f"MaxWeeklyHours_{employee.name}_week_{week_start // 7}"
                )

        for day in self.days:
            for shift in day.shifts:
                self.problem += (
                    lpSum(self.variables[(employee.name, day.date, shift.name)] for employee in self.employees)
                    >= shift.min_staff,
                    f"MinStaff_{day.date}_{shift.name}"
                )
                self.problem += (
                    lpSum(self.variables[(employee.name, day.date, shift.name)] for employee in self.employees)
                    <= shift.max_staff,
                    f"MaxStaff_{day.date}_{shift.name}"
                )

        for employee in self.employees:
            for day in self.days:
                self.problem += (
                    lpSum(self.variables[(employee.name, day.date, shift.name)] for shift in day.shifts) <= 1,
                    f"OneShiftPerDay_{employee.name}_{day.date}"
                )

        for employee in self.employees:
            for day in self.days:
                if day.date in employee.absences:
                    for shift in day.shifts:
                        self.problem += (
                            self.variables[(employee.name, day.date, shift.name)] == 0,
                            f"Absence_{employee.name}_{day.date}_{shift.name}"
                        )

        alpha = 0.85
        beta = 0.15

        total_hours_worked = lpSum(
            self.variables[(employee.name, day.date, shift.name)] * shift.get_duration()
            for employee in self.employees
            for day in self.days
            for shift in day.shifts
        )

        min_hours = LpVariable("MinHours", 0, cat='Integer')
        max_hours = LpVariable("MaxHours", 100, cat='Integer')
        for employee in self.employees:
            total_hours = lpSum(
                self.variables[(employee.name, day.date, shift.name)] * shift.get_duration()
                for day in self.days
                for shift in day.shifts
            )
            self.problem += total_hours >= min_hours, f"MinHoursConstraint_{employee.name}"
            self.problem += total_hours <= max_hours, f"MaxHoursConstraint_{employee.name}"

        fairness = max_hours - min_hours
        self.problem += -alpha * total_hours_worked + beta * fairness, "WeightedObjective"
        self.problem.solve(PULP_CBC_CMD(msg=True))

        for employee in self.employees:
            for day in self.days:
                for shift in day.shifts:
                    if self.variables[(employee.name, day.date, shift.name)].varValue == 1:
                        employee.assigned_shifts.append((day.date, shift.name))

        self.print_schedule()
        self.count_total_hours()
        self.generate_schedule_image()
        self.generate_shift_staffing_image()

    def print_schedule(self):
        for day in self.days:
            print(f"Day: {day.date}")
            for shift in day.shifts:
                assigned_employees = [
                    employee.name
                    for employee in self.employees
                    if self.variables[(employee.name, day.date, shift.name)].varValue == 1
                ]
                print(
                    f"{shift.name} - Employees: {', '.join(assigned_employees) if assigned_employees else 'No employees available'}")
            print("------")

    def count_total_hours(self):
        total_hours = 0
        possible_hours = 0
        max_possible_shift_hours = sum(
            shift.get_duration() * shift.max_staff * len(self.days)
            for shift in shift_types
        )

        for employee in self.employees:
            hours_worked = sum(
                shift.get_duration()
                for day in self.days
                for shift in day.shifts
                if (day.date, shift.name) in employee.assigned_shifts
            )
            max_employee_hours = employee.max_hours_per_week * (len(self.days) / 7)
            total_hours += hours_worked
            possible_hours += max_employee_hours
            utilization = (hours_worked / max_employee_hours * 100) if max_employee_hours > 0 else 0
            # todo: also use absences for calculation
            print(f"{employee.name}: hours worked = {hours_worked}, utilization = {utilization:.2f}%")

        print(f"\nTotal hours worked = {total_hours}")
        print(f"Total possible hours = {possible_hours}")
        print(f"Max possible shift hours = {max_possible_shift_hours}")
        print(f"Staff hour utilization = {total_hours / possible_hours * 100:.2f}%")
        print(f"Staff maximum hour utilization = {total_hours / max_possible_shift_hours * 100:.2f}%")

    def generate_schedule_image(self, filename="export/shift_schedule.png"):
        # Check if the directory exists, if not, create it
        export_dir = os.path.dirname(filename)
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)

        all_employees = [employee.name for employee in self.employees]
        all_days = [day.date for day in self.days]
        df = pd.DataFrame(index=all_employees, columns=all_days)

        # Populate the DataFrame with shift assignments, absences, or 'Off' status
        for employee in self.employees:
            for day in self.days:
                assigned_shifts = [shift_name for (date, shift_name) in employee.assigned_shifts if date == day.date]
                if assigned_shifts:
                    # Only consider the first shift if multiple are assigned (shouldn't happen ideally)
                    df.loc[employee.name, day.date] = assigned_shifts[0]
                elif day.date in employee.absences:
                    df.loc[employee.name, day.date] = 'Absent'
                else:
                    df.loc[employee.name, day.date] = 'Off'

        # Define colors for each status
        colors = {
            'EarlyShift': 'skyblue',
            'LateShift': 'palegreen',
            'NightShift': 'salmon',
            'Absent': 'red',
            'Off': 'lightgrey'
        }

        # Map the string values to numerical codes using replace
        color_codes = {state: code for code, state in enumerate(colors.keys(), start=1)}
        df_numeric = df.replace(color_codes)

        fig, ax = plt.subplots(figsize=(15, len(all_employees) * 0.5))
        sns.heatmap(df_numeric, cmap=mcolors.ListedColormap(colors.values()), cbar=False, ax=ax, linewidths=.5,
                    linecolor='black')

        ax.grid(which="minor", color="black", linestyle='-', linewidth=0.5)

        ax.set_yticklabels(all_employees, rotation=0)
        ax.set_xticklabels(all_days, rotation=45, ha='right')
        ax.set_title('Employee Shift Schedule')

        patches = [plt.Line2D([0], [0], color=colors[label], lw=4, label=label) for label in colors]
        ax.legend(handles=patches, bbox_to_anchor=(1.05, 1), loc='upper left')

        plt.tight_layout()
        plt.savefig(filename)
        print(f"Schedule image saved as {filename}")

    def generate_shift_staffing_image(self, filename="export/shift_staffing.png"):
        # Prepare the matrix for shift staffing image
        all_days = [day.date for day in self.days]
        all_shifts = ['EarlyShift', 'LateShift', 'NightShift']

        staffing_matrix = []

        for shift in all_shifts:
            shift_row = []
            for day in self.days:
                assigned_count = sum(
                    1 for employee in self.employees
                    if self.variables[(employee.name, day.date, shift)].varValue == 1
                )
                shift_info = self.get_shift_status(assigned_count, shift)
                shift_row.append(shift_info)

            staffing_matrix.append(shift_row)

        # Create DataFrame
        df = pd.DataFrame(staffing_matrix, index=all_shifts, columns=all_days)

        # Define the colors for heatmap
        colors = {
            'Min staffed': 'orange',
            'Max staffed': 'green',
            'In between': 'yellow',
            'No employees assigned': 'red'
        }

        # Map status to color codes for heatmap
        color_codes = {state: code for code, state in enumerate(colors.keys(), start=1)}
        df_numeric = df.replace(color_codes)

        # Set the figure size with a fixed height and a proportional width
        fig, ax = plt.subplots(figsize=(15, 7))
        sns.heatmap(df_numeric, cmap=mcolors.ListedColormap(colors.values()), cbar=False, ax=ax, linewidths=.5,
                    linecolor='black')

        ax.grid(which="minor", color="black", linestyle='-', linewidth=0.5)
        ax.set_xticklabels(all_days, rotation=45, ha='right')
        ax.set_yticklabels(all_shifts, rotation=0)
        ax.set_title('Shift Staffing Levels')

        # Create legend for the color map
        patches = [plt.Line2D([0], [0], color=colors[label], lw=4, label=label) for label in colors]
        ax.legend(handles=patches, bbox_to_anchor=(1.05, 1), loc='upper left')

        plt.tight_layout()
        plt.savefig(filename)
        print(f"Shift staffing image saved as {filename}")

    # todo: this doesnt seem to work correctly
    def get_shift_status(self, assigned_count, shift_name):
        # Determine the status based on staffing levels
        for shift in shift_types:
            if shift.name == shift_name:
                if assigned_count == 0:
                    return 'No employees assigned'
                elif assigned_count <= shift.min_staff:
                    return 'Min staffed'
                elif assigned_count >= shift.max_staff:
                    return 'Max staffed'
                else:
                    return 'In between'


shift_types = [
    ShiftType('EarlyShift', '06:00', '14:00', 2, 3),
    ShiftType('LateShift', '14:00', '22:00', 2, 3),
    ShiftType('NightShift', '22:00', '06:00', 1, 2)
]
