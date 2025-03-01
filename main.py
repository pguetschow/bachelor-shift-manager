from pulp import LpProblem, LpVariable, lpSum, LpMinimize, LpBinary, GLPK_CMD, PULP_CBC_CMD

class Employee:
    def __init__(self, name, max_hours, absences=None, preferred_shifts=None):
        self.name = name
        self.max_hours = max_hours
        self.absences = absences if absences else []
        self.preferred_shifts = preferred_shifts if preferred_shifts else []
        self.assigned_shifts = []

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

    def get_end_time(self):
        end_hour, end_minute = map(int, self.end.split(':'))
        end_time = end_hour + end_minute / 60
        if end_time < 12:  # If end time is less than 12, it crosses midnight
            end_time += 24
        return end_time

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
                        f"x_{employee.name}_{day.date}_{shift.name}", 0, 1, LpBinary
                    )

        # Constraint: Employees cannot exceed max allowed hours for planning horizon (1 week)
        for employee in self.employees:
            self.problem += (
                lpSum(
                    self.variables[(employee.name, day.date, shift.name)] * shift.get_duration()
                    for day in self.days
                    for shift in day.shifts
                ) <= employee.max_hours,
                f"MaxHours_{employee.name}"
            )

        # Constraint: Each shift must have at least min_staff and at most max_staff employees
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

        # Constraint: Each employee can work at most one shift per day
        for employee in self.employees:
            for day in self.days:
                self.problem += (
                    lpSum(self.variables[(employee.name, day.date, shift.name)] for shift in day.shifts) <= 1,
                    f"OneShiftPerDay_{employee.name}_{day.date}"
                )

        # Constraint: Employees who are absent cannot be assigned shifts
        for employee in self.employees:
            for day in self.days:
                if day.date in employee.absences:
                    for shift in day.shifts:
                        self.problem += (
                            self.variables[(employee.name, day.date, shift.name)] == 0,
                            f"Absence_{employee.name}_{day.date}_{shift.name}"
                        )

        # Constraint: At least 11 hours between shifts
        for employee in self.employees:
            for i, day in enumerate(self.days[:-1]):
                next_day = self.days[i + 1]
                for shift in day.shifts:
                    for next_shift in next_day.shifts:
                        if next_shift.get_end_time() - shift.get_end_time() < 11:
                            self.problem += (
                                self.variables[(employee.name, day.date, shift.name)] +
                                self.variables[(employee.name, next_day.date, next_shift.name)] <= 1,
                                f"RestTime_{employee.name}_{day.date}_{shift.name}_{next_day.date}_{next_shift.name}"
                            )

        # # Objective 1: Maximize the total number of hours worked
        # self.problem += -lpSum(
        #     self.variables[(employee.name, day.date, shift.name)] * shift.get_duration()
        #     for employee in self.employees
        #     for day in self.days
        #     for shift in day.shifts
        # ), "MaximizeTotalHours"
        #
        # # Objective 2: Minimize the difference in hours worked between employees
        # min_hours = LpVariable("MinHours", 0, cat='Integer')
        # max_hours = LpVariable("MaxHours", 100, cat='Integer')
        # for employee in self.employees:
        #     total_hours = lpSum(
        #         self.variables[(employee.name, day.date, shift.name)] * shift.get_duration()
        #         for day in self.days
        #         for shift in day.shifts
        #     )
        #     self.problem += total_hours >= min_hours, f"MinHoursConstraint_{employee.name}"
        #     self.problem += total_hours <= max_hours, f"MaxHoursConstraint_{employee.name}"
        #
        # self.problem += (max_hours - min_hours, "MinimizeHourDifference")

        # Objective: Weighted combination of maximizing total hours worked and minimizing difference in hours worked
        alpha = 0.8  # Weight for maximizing hours worked
        beta = 0.2  # Weight for fairness in hour distribution

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
        # Solve using GLPK with a time limit
        self.problem.solve(solver=GLPK_CMD(msg=True, options=['--tmlim', '30']))

        # Track assigned shifts for each employee
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
                print(
                    f"{shift.name} - Employees: {', '.join(assigned_employees) if assigned_employees else 'No employees available'}"
                )
            print("------")

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
    Employee('Alice', 40, ['2024-02-25'], ['EarlyShift']),
    Employee('Bob', 40, ['2024-02-28'], ['NightShift']),
    Employee('Charlie', 40, [], ['LateShift']),
    Employee('David', 40, ['2024-02-27'], ['EarlyShift']),
    Employee('Eve', 40, [], ['LateShift']),
    Employee('Frank', 40, ['2024-02-26'], ['NightShift']),
    Employee('Grace', 40, [], ['EarlyShift']),
    Employee('Peter', 40, [], []),
    Employee('Hannah', 40, ['2024-02-27'], ['LateShift']),
    Employee('Sven', 40, ['2024-02-24'], ['LateShift']),
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
