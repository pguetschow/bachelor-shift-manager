from django.shortcuts import render
from rostering_app.models import ScheduleEntry, Employee
from datetime import datetime

def schedule_view(request):
    # Retrieve all non-archived schedule entries
    entries = ScheduleEntry.objects.filter(archived=False)

    # Get a sorted list of unique dates (as strings) from schedule entries
    dates = sorted({entry.date.strftime('%Y-%m-%d') for entry in entries})

    # Get all employees (you may want to sort them by name)
    employees = Employee.objects.all().order_by('name')

    # Build a matrix where each row is: {"employee": employee_name, "schedule": [shift for each date]}
    matrix = []
    for emp in employees:
        row = {"employee": emp.name, "schedule": []}
        for d in dates:
            # Try to get the schedule entry for this employee and date
            entry = entries.filter(employee=emp, date=datetime.strptime(d, '%Y-%m-%d').date()).first()
            if entry:
                row["schedule"].append(entry.shift_type.name)
            elif d in emp.absences:  # Check if the employee is absent on that day
                row["schedule"].append("Absent")
            else:
                row["schedule"].append("Off")
        matrix.append(row)

    context = {
        "dates": dates,
        "matrix": matrix
    }
    return render(request, 'rostering_app/schedule.html', context)
