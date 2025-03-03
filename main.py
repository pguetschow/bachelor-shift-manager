from pulp import LpProblem, LpVariable, lpSum, LpMinimize, LpBinary, PULP_CBC_CMD
from datetime import datetime, timedelta

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

    def print_schedule(self):
        for day in self.days:
            print(f"Day: {day.date}")
            for shift in day.shifts:
                assigned_employees = [
                    employee.name
                    for employee in self.employees
                    if self.variables[(employee.name, day.date, shift.name)].varValue == 1
                ]
                print(f"{shift.name} - Employees: {', '.join(assigned_employees) if assigned_employees else 'No employees available'}")
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
            print(f"{employee.name}: hours worked = {hours_worked}, utilization = {utilization:.2f}%")

        print(f"\nTotal hours worked = {total_hours}")
        print(f"Total possible hours = {possible_hours}")
        print(f"Max possible shift hours = {max_possible_shift_hours}")
        print(f"Staff hour utilization = {total_hours / possible_hours * 100:.2f}%")
        print(f"Staff maximum hour utilization = {total_hours / max_possible_shift_hours * 100:.2f}%")


start_date = datetime.strptime('2024-03-01', '%Y-%m-%d')
num_days = 28  # Monthly schedule
employees = [
    Employee('Alice', 40, ['2024-02-25', '2024-02-27'], ['EarlyShift']),
    Employee('Bob', 40, ['2024-02-28'], ['NightShift']),
    Employee('Charlie', 40, [], ['LateShift']),
    Employee('David', 40, ['2024-02-27'], ['EarlyShift']),
    Employee('Eve', 40, [], ['LateShift']),
    Employee('Frank', 32, ['2024-02-26'], ['NightShift']),
    Employee('Grace', 40, [], ['EarlyShift']),
    Employee('Peter', 40, [], []),
    Employee('Hannah', 40, ['2024-02-27'], ['LateShift']),
    Employee('Sven', 32, ['2024-02-24'], ['LateShift']),
    Employee('Test', 32, ['2024-02-24'], ['LateShift']),
    Employee('Test1', 32, ['2024-02-24'], ['LateShift']),
    Employee('Test2', 32, ['2024-02-24'], ['LateShift']),
]

shift_types = [
    ShiftType('EarlyShift', '06:00', '14:00', 2, 3),
    ShiftType('LateShift', '14:00', '22:00', 2, 3),
    ShiftType('NightShift', '22:00', '06:00', 1, 2)
]

rostering = EmployeeRostering(employees, start_date, num_days)
rostering.generate_schedule()
rostering.print_schedule()
rostering.count_total_hours()