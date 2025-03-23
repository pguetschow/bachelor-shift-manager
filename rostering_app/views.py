import datetime
from django.shortcuts import render
from rostering_app.models import ScheduleEntry, Employee


def start_page(request):
    """
    Display the schedule for the current day, grouped by shift.
    If no schedule exists for today, fall back to the fixture month (February 2024).
    """
    today = datetime.date.today()
    # Query schedule entries for today's date
    entries = ScheduleEntry.objects.filter(date=today, archived=False)
    fallback_used = False

    if not entries.exists():
        # If there are no entries for today, use fixture month (February 2024)
        day_num = today.day if today.day <= 28 else 28
        fixture_date = datetime.date(2024, 2, day_num)
        entries = ScheduleEntry.objects.filter(date=fixture_date, archived=False)
        fallback_used = True
        display_date = fixture_date
    else:
        display_date = today

    # Group schedule entries by shift type
    shift_groups = {}
    for entry in entries:
        shift_name = entry.shift_type.name
        if shift_name not in shift_groups:
            shift_groups[shift_name] = {
                'shift_info': entry.shift_type,
                'employees': []
            }
        shift_groups[shift_name]['employees'].append(entry.employee)

    # Sort groups by shift name (or any desired order)
    grouped_shifts = sorted(shift_groups.items(), key=lambda item: item[0])

    context = {
        'shift_groups': grouped_shifts,
        'fallback_used': fallback_used,
        'date': display_date,
    }
    return render(request, 'rostering_app/index.html', context)


def schedule_view(request):
    """
    Display the full schedule (non-archived entries) ordered by date in a matrix format.
    """
    # Retrieve all non-archived schedule entries
    entries = ScheduleEntry.objects.filter(archived=False)

    # Get a sorted list of unique dates (as strings) from schedule entries
    dates = sorted({entry.date.strftime('%Y-%m-%d') for entry in entries})

    # Get all employees (sorted by name)
    employees = Employee.objects.all().order_by('name')

    # Build a matrix where each row is: {"employee": employee_name, "schedule": [shift for each date]}
    matrix = []
    for emp in employees:
        row = {"employee": emp.name, "schedule": []}
        for d in dates:
            # Convert d (a date string) to a date object using datetime.datetime.strptime
            date_obj = datetime.datetime.strptime(d, '%Y-%m-%d').date()
            # Try to get the schedule entry for this employee and date
            entry = entries.filter(employee=emp, date=date_obj).first()
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
