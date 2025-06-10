import datetime
import calendar
from django.shortcuts import render
from rostering_app.models import ScheduleEntry, Employee


def start_page(request):
    """
    Display the schedule for the current day, grouped by shift.
    If no schedule exists for today, fall back to the fixture month (February 2025).
    """
    today = datetime.date.today()
    # Query schedule entries for today's date
    entries = ScheduleEntry.objects.filter(date=today, archived=False)
    fallback_used = False

    if not entries.exists():
        # If there are no entries for today, use fixture month (February 2025)
        day_num = today.day if today.day <= 28 else 28
        fixture_date = datetime.date(2025, 2, day_num)
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
    # Determine selected month from query parameter, default to current month
    month_param = request.GET.get('month')
    if month_param:
        try:
            year, month = map(int, month_param.split('-'))
        except ValueError:
            today = datetime.date.today()
            year, month = today.year, today.month
    else:
        today = datetime.date.today()
        year, month = today.year, today.month

    # Calculate first and last day of the selected month
    start_date = datetime.date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = datetime.date(year, month, last_day)

    # Filter schedule entries for the selected month
    entries = ScheduleEntry.objects.filter(date__gte=start_date, date__lte=end_date, archived=False)

    # Get a sorted list of unique dates (as strings) within the selected month from schedule entries
    dates = sorted({entry.date.strftime('%Y-%m-%d') for entry in entries})

    # Get all employees (sorted by name)
    employees = Employee.objects.all().order_by('name')

    # Build a schedule matrix for employees for the selected month
    matrix = []
    for emp in employees:
        row = {"employee": emp.name, "schedule": []}
        for d in dates:
            date_obj = datetime.datetime.strptime(d, '%Y-%m-%d').date()
            entry = entries.filter(employee=emp, date=date_obj).first()
            if entry:
                row["schedule"].append(entry.shift_type.name)
            elif d in emp.absences:  # Assuming emp.absences is iterable with date strings
                row["schedule"].append("Absent")
            else:
                row["schedule"].append("Off")
        matrix.append(row)

    # Calculate previous and next month values
    prev_month = month - 1
    prev_year = year
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1
    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year += 1

    prev_month_param = f"{prev_year}-{prev_month:02d}"
    next_month_param = f"{next_year}-{next_month:02d}"
    current_month_value = f"{year}-{month:02d}"

    # Build month overview: list unique months with schedule entries (e.g., "2025-02")
    all_entries = ScheduleEntry.objects.filter(archived=False)
    month_overview = sorted({entry.date.strftime('%Y-%m') for entry in all_entries})

    context = {
        "dates": dates,
        "matrix": matrix,
        "prev_month": prev_month_param,
        "next_month": next_month_param,
        "current_month": datetime.date(year, month, 1).strftime('%B %Y'),
        "current_month_value": current_month_value,
        "month_overview": month_overview,
    }
    return render(request, 'rostering_app/schedule.html', context)
