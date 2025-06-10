from datetime import datetime

from legacy.classes.employee_rostering import EmployeeRostering, Employee

employees = [
    Employee('Alice', 40, ['2025-02-05', '2025-02-12'], ['EarlyShift']),
    Employee('Bob', 40, ['2025-02-28'], ['NightShift']),
    Employee('Charlie', 40, [], ['LateShift']),
    Employee('David', 40, ['2025-02-17'], ['EarlyShift']),
    Employee('Eve', 40, [], ['LateShift']),
    Employee('Frank', 32, ['2025-02-26'], ['NightShift']),
    Employee('Grace', 40, [], ['EarlyShift']),
    Employee('Jens', 40, ['2025-02-19'], ['EarlyShift']),
    Employee('Peter', 32, [], []),
    Employee('Hannah', 40, ['2025-02-07'], ['LateShift']),
    Employee('Sven', 32, ['2025-02-04'], ['EarlyShift']),
    Employee('Mike', 32, ['2025-02-21'], ['LateShift']),
    Employee('Jace', 40, [], ['NightShift']),
    Employee('Anna', 32, ['2025-02-14'], ['EarlyShift']),
    Employee('Werner', 40, [], []),
    Employee('Hans', 40, ['2025-02-20'], ['LateShift']),
]
start_date = datetime.strptime('2025-02-01', '%Y-%m-%d')
num_days = 28  # Monthly schedule

rostering = EmployeeRostering(employees, start_date, num_days)
rostering.generate_schedule()

