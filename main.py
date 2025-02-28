from pulp import LpProblem, LpVariable, lpSum, LpMinimize, LpBinary, GLPK_CMD

class Employee:
    def __init__(self, name, max_hours, absences=None, preferred_shifts=None):
        self.name = name
        self.max_hours = max_hours
        self.absences = absences if absences else []
        self.preferred_shifts = preferred_shifts if preferred_shifts else []
        self.assigned_shifts = []  # New property to track assigned shifts

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
    def __init__(self, employees, days):
        self.employees = employees
        self.days = days
        self.problem = LpProblem("Employee Rostering", LpMinimize)
        self.variables = {}

    def generate_schedule(self):
        # Create decision variables
        for employee in self.employees:
            for day in self.days:
                for shift in day.shifts:
                    self.variables[(employee.name, day.date, shift.name)] = LpVariable(
                        f"{employee.name}_{day.date}_{shift.name}", cat=LpBinary
                    )

        # Calculate total hours for each employee
        total_hours = {employee.name: lpSum(
            self.variables[(employee.name, day.date, shift.name)] * shift.get_duration()
            for day in self.days
            for shift in day.shifts
        ) for employee in self.employees}

        # Constraint: Employees cannot exceed max allowed hours for planning horizon (1 week)
        for employee in self.employees:
            self.problem += total_hours[employee.name] <= employee.max_hours, f"MaxHours_{employee.name}"

        # Constraint: Each shift must have exactly the required staff
        for day in self.days:
            for shift in day.shifts:
                total_staff = lpSum(
                    self.variables[(employee.name, day.date, shift.name)]
                    for employee in self.employees
                )
                self.problem += total_staff >= shift.min_staff, f"MinStaff_{day.date}_{shift.name}"
                self.problem += total_staff <= shift.max_staff, f"MaxStaff_{day.date}_{shift.name}"

        # Constraint: Each employee can work at most one shift per day
        for employee in self.employees:
            for day in self.days:
                total_shifts = lpSum(
                    self.variables[(employee.name, day.date, shift.name)]
                    for shift in day.shifts
                )
                self.problem += total_shifts <= 1, f"OneShiftPerDay_{employee.name}_{day.date}"

        # Constraint: At least 12 hours between shifts
        for employee in self.employees:
            for i in range(len(self.days) - 1):
                day1 = self.days[i]
                day2 = self.days[i + 1]
                for shift1 in day1.shifts:
                    for shift2 in day2.shifts:
                        if shift1.end == '22:00' and shift2.start == '06:00':
                            self.problem += (
                                self.variables[(employee.name, day1.date, shift1.name)] +
                                self.variables[(employee.name, day2.date, shift2.name)] <= 1
                            ), f"RestBetweenShifts_{employee.name}_{day1.date}_{shift1.name}_{day2.date}_{shift2.name}"

        # Objective: Minimize the difference in hours worked between employees
        max_hours = LpVariable("max_hours", lowBound=0)
        min_hours = LpVariable("min_hours", lowBound=0)

        for employee in self.employees:
            self.problem += max_hours >= total_hours[employee.name]
            self.problem += min_hours <= total_hours[employee.name]

        self.problem += max_hours - min_hours, "MinimizeHoursDifference"

        # todo: is it possible to maximize employees per shift and minimize hour difference?

        # Solve using GLPK
        self.problem.solve(solver=GLPK_CMD(msg=True))

        # Track assigned shifts for each employee
        for employee in self.employees:
            for day in self.days:
                for shift in day.shifts:
                    if self.variables[(employee.name, day.date, shift.name)].varValue == 1:
                        employee.assigned_shifts.append((day.date, shift.name))

    def print_schedule(self):
        for day in self.days:
            for shift in day.shifts:
                assigned_employees = [
                    employee.name
                    for employee in self.employees
                    if self.variables[(employee.name, day.date, shift.name)].varValue == 1
                ]
                print(
                    f"Shift: {day.date} - {shift.name} - Employees: {', '.join(assigned_employees) if assigned_employees else 'No employees available'}"
                )

    def count_total_hours(self):
        for employee in self.employees:
            total_hours = sum(
                shift.get_duration()
                for day in self.days
                for shift in day.shifts
                if (day.date, shift.name) in employee.assigned_shifts
            )
            print(f"{employee.name}: Total hours worked = {total_hours}")

# Example data
employees = [
    Employee('Alice', 40, ['2024-02-27'], ['EarlyShift']),
    Employee('Bob', 40, ['2024-02-28'], ['NightShift']),
    Employee('Charlie', 40, [], ['LateShift']),
    Employee('David', 40, ['2024-02-27'], ['EarlyShift']),
    Employee('Eve', 40, [], ['LateShift']),
    Employee('Frank', 40, ['2024-02-26'], ['NightShift']),
    Employee('Grace', 40, [], ['EarlyShift']),
    Employee('Grace3', 40, [], []),
    Employee('Hannah', 40, ['2024-02-27'], ['LateShift']),
    Employee('Test', 40, ['2024-02-27'], ['LateShift'])
]

shift_types = [
    ShiftType('EarlyShift', '06:00', '14:00', 2, 3),
    ShiftType('LateShift', '14:00', '22:00', 2, 3),
    ShiftType('NightShift', '22:00', '06:00', 1, 2)
]

days = [
    Day('2024-02-23', shift_types),
    Day('2024-02-24', shift_types),
    Day('2024-02-25', shift_types),
    Day('2024-02-26', shift_types),
    Day('2024-02-27', shift_types),
    Day('2024-02-28', shift_types)
]

# Create and solve the rostering problem
rostering = EmployeeRostering(employees, days)
rostering.generate_schedule()
rostering.print_schedule()
rostering.count_total_hours()
