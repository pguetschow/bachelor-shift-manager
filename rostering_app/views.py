import calendar
import datetime
import os
import time
from datetime import date
from typing import List

from django.conf import settings
from django.core.management import call_command
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from rostering_app.models import ScheduleEntry, Employee, Shift, Company
from rostering_app.services.kpi_calculator import KPICalculator
from rostering_app.utils import is_holiday, is_sunday, is_non_working_day, get_working_days_in_range


def load_company_fixtures(company):
    """Load fixtures for the specified company."""
    try:
        # Determine which company size fixtures to load
        company_size = company.size.lower()
        fixtures_dir = os.path.join(settings.BASE_DIR, 'rostering_app', 'fixtures', company_size)

        if os.path.exists(fixtures_dir):
            # Load employees for this company
            employees_fixture = os.path.join(fixtures_dir, 'employees.json')
            if os.path.exists(employees_fixture):
                call_command('loaddata', employees_fixture, verbosity=0)

            # Load shifts for this company
            shifts_fixture = os.path.join(fixtures_dir, 'shifts.json')
            if os.path.exists(shifts_fixture):
                call_command('loaddata', shifts_fixture, verbosity=0)

            return True
    except Exception as e:
        print(f"Error loading fixtures for company {company.name}: {e}")
        return False

    return False


def get_shift_status(count, min_staff, max_staff):
    """Determine shift coverage status."""
    if count < min_staff:
        return 'understaffed'
    elif count > max_staff:
        return 'overstaffed'
    elif count == max_staff:
        return 'full'
    else:
        return 'ok'


def build_employee_calendar(year, month, entries, absences):
    """Build calendar data for employee view."""
    cal = calendar.monthcalendar(year, month)
    entries_by_date = {e.date: e for e in entries}
    absence_dates = [datetime.datetime.strptime(d, '%Y-%m-%d').date() for d in absences]

    calendar_data = []

    for week in cal:
        week_data = []
        for day in week:
            if day == 0:
                week_data.append(None)
            else:
                date = datetime.date(year, month, day)
                entry = entries_by_date.get(date)

                cell_data = {
                    'day': day,
                    'date': date,
                    'entry': entry,
                    'is_absence': date in absence_dates,
                    'is_today': date == datetime.date.today()
                }
                week_data.append(cell_data)
        calendar_data.append(week_data)

    return calendar_data


# New API endpoints for Vue.js frontend
@csrf_exempt
@require_http_methods(["GET"])
def api_companies(request):
    """API endpoint to get all companies."""
    companies = Company.objects.all()
    companies_data = []

    for company in companies:
        employee_count = Employee.objects.filter(company=company).count()
        shift_count = Shift.objects.filter(company=company).count()

        companies_data.append({
            'id': company.id,
            'name': company.name,
            'size': company.size,
            'description': company.description,
            'icon': company.icon,
            'color': company.color,
            'sunday_is_workday': company.sunday_is_workday,
            'employee_count': employee_count,
            'shift_count': shift_count
        })

    return JsonResponse(companies_data, safe=False)


@csrf_exempt
@require_http_methods(["GET"])
def api_company_detail(request, company_id):
    """API endpoint to get a specific company."""
    company = get_object_or_404(Company, pk=company_id)
    employee_count = Employee.objects.filter(company=company).count()
    shift_count = Shift.objects.filter(company=company).count()

    company_data = {
        'id': company.id,
        'name': company.name,
        'size': company.size,
        'description': company.description,
        'icon': company.icon,
        'color': company.color,
        'sunday_is_workday': company.sunday_is_workday,
        'employee_count': employee_count,
        'shift_count': shift_count
    }

    return JsonResponse(company_data)


@csrf_exempt
@require_http_methods(["GET"])
def api_company_algorithms(request, company_id):
    """API endpoint to get available algorithms for a company."""
    company = get_object_or_404(Company, pk=company_id)
    available_algorithms = ScheduleEntry.objects.filter(company=company).values_list('algorithm', flat=True).distinct()
    available_algorithms = sorted([alg for alg in available_algorithms if alg])

    return JsonResponse({
        'algorithms': available_algorithms
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_company_schedule(request, company_id):
    """API endpoint to get schedule data for a company."""
    company = get_object_or_404(Company, pk=company_id)
    load_company_fixtures(company)

    # Get query parameters
    year = int(request.GET.get('year', datetime.date.today().year))
    month = int(request.GET.get('month', datetime.date.today().month))
    algorithm = request.GET.get('algorithm', '')

    # Calculate date range
    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])

    # Get schedule entries with related objects
    entry_filter = {
        'company': company,
        'date__gte': first_day,
        'date__lte': last_day
    }
    if algorithm:
        entry_filter['algorithm'] = algorithm

    entries = ScheduleEntry.objects.filter(**entry_filter).select_related('shift', 'employee')

    # Calculate statistics
    kpi_calculator = KPICalculator(company)
    coverage_stats = kpi_calculator.calculate_coverage_stats(entries, first_day, last_day)
    employee_hours = kpi_calculator.calculate_employee_hours_with_month_boundaries(entries, first_day, last_day)
    top_employees = sorted(employee_hours.items(), key=lambda x: x[1], reverse=True)[:5]

    # Batch fetch top employee names
    top_employee_ids = [emp_id for emp_id, _ in top_employees]
    employee_objs = Employee.objects.filter(id__in=top_employee_ids)
    employee_id_to_name = {e.id: e.name for e in employee_objs}

    # Format schedule data by date
    schedule_data = {}
    for entry in entries:
        date_str = entry.date.isoformat()
        if date_str not in schedule_data:
            # Add holiday and non-working day information
            is_holiday_day = is_holiday(entry.date)
            is_sunday_day = is_sunday(entry.date)
            is_non_working = is_non_working_day(entry.date, company)

            schedule_data[date_str] = {
                'shifts': {},
                'is_holiday': is_holiday_day,
                'is_sunday': is_sunday_day,
                'is_non_working': is_non_working
            }

        shift_name = entry.shift.name
        if shift_name not in schedule_data[date_str]['shifts']:
            schedule_data[date_str]['shifts'][shift_name] = {
                'count': 0,
                'min_staff': entry.shift.min_staff,
                'max_staff': entry.shift.max_staff,
                'status': 'ok'
            }

        schedule_data[date_str]['shifts'][shift_name]['count'] += 1

    # Calculate status for each shift on each date
    for date_str, date_data in schedule_data.items():
        for shift_name, shift_data in date_data['shifts'].items():
            shift_data['status'] = get_shift_status(
                shift_data['count'],
                shift_data['min_staff'],
                shift_data['max_staff']
            )

    # Add empty shift data for dates without schedule entries
    all_shifts = Shift.objects.filter(company=company)
    current_date = first_day
    while current_date <= last_day:
        date_str = current_date.isoformat()
        if date_str not in schedule_data:
            # Add holiday and non-working day information
            is_holiday_day = is_holiday(current_date)
            is_sunday_day = is_sunday(current_date)
            is_non_working = is_non_working_day(current_date, company)

            schedule_data[date_str] = {
                'shifts': {},
                'is_holiday': is_holiday_day,
                'is_sunday': is_sunday_day,
                'is_non_working': is_non_working
            }

        # Ensure all shifts are represented for each date
        for shift in all_shifts:
            if shift.name not in schedule_data[date_str]['shifts']:
                schedule_data[date_str]['shifts'][shift.name] = {
                    'count': 0,
                    'min_staff': shift.min_staff,
                    'max_staff': shift.max_staff,
                    'status': get_shift_status(0, shift.min_staff, shift.max_staff)
                }

        current_date += datetime.timedelta(days=1)

    total_employees = Employee.objects.filter(company=company).count()
    total_shifts = Shift.objects.filter(company=company).count()

    return JsonResponse({
        'schedule_data': schedule_data,
        'coverage_stats': {
            'total_employees': total_employees,
            'total_shifts': total_shifts,
            'working_days': len(get_working_days_in_range(first_day, last_day, company)),
            'coverage_percentage': sum(stat['coverage_percentage'] for stat in coverage_stats) / len(
                coverage_stats) if coverage_stats else 0,
            'fully_staffed': sum(1 for stat in coverage_stats if stat['status'] == 'full'),
            'understaffed': sum(1 for stat in coverage_stats if stat['status'] == 'understaffed'),
            'shifts': coverage_stats
        },
        'top_employees': [
            {
                'id': emp_id,
                'name': employee_id_to_name.get(emp_id, ''),
                'hours': hours
            }
            for emp_id, hours in top_employees
        ]
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_company_employees(request, company_id):
    """API endpoint to get employees for a company."""
    company = get_object_or_404(Company, pk=company_id)
    employees = Employee.objects.filter(company=company).prefetch_related('preferred_shifts')

    employees_data = []
    for employee in employees:
        employees_data.append({
            'id': employee.id,
            'name': employee.name,
            'position': employee.position,
            'max_hours_per_week': employee.max_hours_per_week,
            'preferred_shifts': list(employee.preferred_shifts.values_list('name', flat=True))
        })

    return JsonResponse(employees_data, safe=False)


@csrf_exempt
@require_http_methods(["GET"])
def api_company_shifts(request, company_id):
    """API endpoint to get shifts for a company."""
    company = get_object_or_404(Company, pk=company_id)
    shifts = Shift.objects.filter(company=company)

    shifts_data = []
    for shift in shifts:
        shifts_data.append({
            'id': shift.id,
            'name': shift.name,
            'start_time': shift.start.isoformat(),
            'end_time': shift.end.isoformat(),
            'min_staff': shift.min_staff,
            'max_staff': shift.max_staff
        })

    return JsonResponse(shifts_data, safe=False)


@csrf_exempt
@require_http_methods(["GET"])
def api_company_day_schedule(request, company_id, date):
    """API endpoint to get schedule data for a specific day."""
    company = get_object_or_404(Company, pk=company_id)
    load_company_fixtures(company)

    try:
        target_date = datetime.datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    # Get algorithm filter from query params
    algorithm = request.GET.get('algorithm', '')

    # Get schedule entries for the specific date, filtered by algorithm if provided
    entry_filter = {
        'company': company,
        'date': target_date
    }
    if algorithm:
        entry_filter['algorithm'] = algorithm
    entries = ScheduleEntry.objects.filter(**entry_filter)

    # Get all shifts for the company
    all_shifts = Shift.objects.filter(company=company)

    # Format shifts data with employee assignments
    shifts_data = []
    for shift in all_shifts:
        shift_entries = entries.filter(shift=shift)
        assigned_employees = []

        for entry in shift_entries:
            assigned_employees.append({
                'id': entry.employee.id,
                'name': entry.employee.name,
                'algorithm': entry.algorithm or 'Unknown'
            })

        shifts_data.append({
            'shift': {
                'id': shift.id,
                'name': shift.name,
                'start_time': shift.start.isoformat(),
                'end_time': shift.end.isoformat(),
                'min_staff': shift.min_staff,
                'max_staff': shift.max_staff,
                'assigned_count': len(assigned_employees),
                'assigned_employees': assigned_employees,
                'status': get_shift_status(len(assigned_employees), shift.min_staff, shift.max_staff)
            }
        })

    # Get day information
    is_holiday_day = is_holiday(target_date)
    is_sunday_day = is_sunday(target_date)
    is_non_working = is_non_working_day(target_date, company)

    return JsonResponse({
        'date': date,
        'is_holiday': is_holiday_day,
        'is_sunday': is_sunday_day,
        'is_non_working': is_non_working,
        'shifts': shifts_data,
        'total_assignments': sum(len(shift['shift']['assigned_employees']) for shift in shifts_data)
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_company_employee_schedule(request, company_id, employee_id):
    """API endpoint to get schedule data for a specific employee."""
    company = get_object_or_404(Company, pk=company_id)
    employee = get_object_or_404(Employee, pk=employee_id, company=company)
    load_company_fixtures(company)

    # Get query parameters
    year = int(request.GET.get('year', datetime.date.today().year))
    month = int(request.GET.get('month', datetime.date.today().month))
    algorithm = request.GET.get('algorithm', '')

    # Calculate date range
    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])

    # Get employee's schedule entries
    entry_filter = {
        'employee': employee,
        'date__gte': first_day,
        'date__lte': last_day
    }
    if algorithm:
        entry_filter['algorithm'] = algorithm

    entries = ScheduleEntry.objects.filter(**entry_filter).order_by('date')

    # Format schedule data
    schedule_data = []
    for entry in entries:
        schedule_data.append({
            'id': entry.id,
            'date': entry.date.isoformat(),
            'shift': {
                'id': entry.shift.id,
                'name': entry.shift.name,
                'start_time': entry.shift.start.isoformat(),
                'end_time': entry.shift.end.isoformat(),
                'min_staff': entry.shift.min_staff,
                'max_staff': entry.shift.max_staff
            },
            'algorithm': entry.algorithm or 'Unknown'
        })

    # Calculate statistics
    total_hours = sum(entry.shift.get_duration() for entry in entries)
    total_shifts = entries.count()
    average_hours_per_shift = total_hours / total_shifts if total_shifts > 0 else 0

    # Calculate weekly workload
    weekly_workload = []
    current_week = first_day
    while current_week <= last_day:
        week_end = min(current_week + datetime.timedelta(days=6), last_day)
        week_entries = entries.filter(date__gte=current_week, date__lte=week_end)
        week_hours = sum(
            entry.shift.get_duration() for entry in week_entries)
        weekly_workload.append(round(week_hours, 3))
        current_week += datetime.timedelta(days=7)

    # Calculate utilization percentage based on monthly hours
    # Calculate exact monthly hours based on working days
    working_days = get_working_days_in_range(first_day, last_day, company)
    total_working_days = len(working_days)

    # Calculate max monthly hours using KPI calculator that accounts for absences
    kpi_calculator = KPICalculator(company)
    max_monthly_hours = kpi_calculator.calculate_expected_month_hours(employee, year, month, company)
    utilization_percentage = kpi_calculator.calculate_utilization_percentage(total_hours, max_monthly_hours)

    return JsonResponse({
        'employee': {
            'id': employee.id,
            'name': employee.name,
            'position': getattr(employee, 'position', 'Mitarbeiter'),
            'max_hours_per_week': employee.max_hours_per_week,
            'preferred_shifts': employee.preferred_shifts,
            'absences': employee.absences
        },
        'schedule_data': schedule_data,
        'statistics': {
            'total_hours': total_hours,
            'total_shifts': total_shifts,
            'average_hours_per_shift': average_hours_per_shift,
            'utilization_percentage': utilization_percentage
        },
        'weekly_workload': weekly_workload,
        'month': month,
        'year': year
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_company_employee_yearly_schedule(request, company_id, employee_id):
    """API endpoint to get yearly schedule data for a specific employee."""
    company = get_object_or_404(Company, pk=company_id)
    employee = get_object_or_404(Employee, pk=employee_id, company=company)
    load_company_fixtures(company)
    kpi_calculator = KPICalculator(company)

    # Get query parameters
    year = int(request.GET.get('year', datetime.date.today().year))
    algorithm = request.GET.get('algorithm', '')

    # Calculate date range for the entire year
    first_day = datetime.date(year, 1, 1)
    last_day = datetime.date(year, 12, 31)

    # Get employee's schedule entries for the year
    entry_filter = {
        'employee': employee,
        'date__gte': first_day,
        'date__lte': last_day
    }
    if algorithm:
        entry_filter['algorithm'] = algorithm

    entries = ScheduleEntry.objects.filter(**entry_filter).order_by('date')

    # Calculate yearly statistics
    total_hours = sum(entry.shift.get_duration() for entry in entries)
    total_shifts = entries.count()
    average_hours_per_shift = total_hours / total_shifts if total_shifts > 0 else 0

    # Calculate monthly breakdown
    monthly_hours_list = []
    monthly_shifts = []
    for month in range(1, 13):
        month_start = datetime.date(year, month, 1)
        month_end = datetime.date(year, month, calendar.monthrange(year, month)[1])
        month_entries = entries.filter(date__gte=month_start, date__lte=month_end)
        month_hours = sum(
            entry.shift.get_duration() for entry in month_entries)
        monthly_hours_list.append(round(month_hours, 3))
        monthly_shifts.append(month_entries.count())

    # Calculate yearly utilization using the new function that accounts for absences
    total_possible_yearly_hours = kpi_calculator.calculate_expected_yearly_hours(employee, year)
    yearly_utilization = kpi_calculator.calculate_utilization_percentage(total_hours, total_possible_yearly_hours)

    # Format schedule data for frontend KPI calculation
    schedule_data = []
    for entry in entries:
        schedule_data.append({
            'id': entry.id,
            'date': entry.date.isoformat(),
            'shift': {
                'id': entry.shift.id,
                'name': entry.shift.name,
                'start_time': entry.shift.start.isoformat(),
                'end_time': entry.shift.end.isoformat(),
                'min_staff': entry.shift.min_staff,
                'max_staff': entry.shift.max_staff
            },
            'algorithm': entry.algorithm or 'Unknown'
        })

    return JsonResponse({
        'employee': {
            'id': employee.id,
            'name': employee.name,
            'position': getattr(employee, 'position', 'Mitarbeiter'),
            'max_hours_per_week': employee.max_hours_per_week,
            'preferred_shifts': employee.preferred_shifts,
            'absences': employee.absences
        },
        'schedule_data': schedule_data,
        'yearly_statistics': {
            'total_hours': total_hours,
            'total_shifts': total_shifts,
            'average_hours_per_shift': average_hours_per_shift,
            'max_yearly_hours': total_possible_yearly_hours,
            'yearly_utilization_percentage': yearly_utilization
        },
        'monthly_breakdown': {
            'hours': monthly_hours_list,
            'shifts': monthly_shifts
        },
        'year': year
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_company_employee_statistics(request, company_id: int):
    """API endpoint to get comprehensive employee statistics for a company.

    Query params:
        year: int (defaults to current year)
        month: int (defaults to current month)
        algorithm: str (optional filter on ScheduleEntry.algorithm)
    """
    company = get_object_or_404(Company, pk=company_id)
    # load_company_fixtures(company)

    # Params
    today = datetime.date.today()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))
    algorithm = request.GET.get("algorithm", "").strip()

    # Date ranges
    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)

    # Company config
    sundays_off = getattr(company, "sundays_off", False)

    # Holidays (set of (y,m,d) tuples). You can replace these with a DB/table-driven list.
    holidays = {(d.month, d.day) for d in get_company_holidays(year, company)}

    # Working days for the month (company-level): useful for absence calc baseline
    working_days = get_working_days_in_range(month_start, month_end, company)
    total_working_days = len(working_days)

    # Calculate KPIs directly using KPICalculator
    kpi_calculator = KPICalculator(company)
    employees = Employee.objects.filter(company=company)

    employees_data = []
    for employee in employees:
        # Get monthly entries for this employee
        monthly_entries = ScheduleEntry.objects.filter(
            employee=employee,
            company=company,
            date__gte=month_start,
            date__lte=month_end
        )
        if algorithm:
            monthly_entries = monthly_entries.filter(algorithm=algorithm)

        # Calculate monthly statistics
        monthly_stats = kpi_calculator.calculate_employee_statistics(
            employee, list(monthly_entries), year, month, algorithm
        )

        # Calculate yearly statistics
        yearly_entries = ScheduleEntry.objects.filter(
            employee=employee,
            company=company,
            date__gte=year_start,
            date__lte=year_end
        )
        if algorithm:
            yearly_entries = yearly_entries.filter(algorithm=algorithm)

        yearly_hours = sum(
            entry.shift.get_duration()
            for entry in yearly_entries
        )
        yearly_shifts = yearly_entries.count()
        maxPossibleHours = kpi_calculator.calculate_expected_yearly_hours(employee, year)
        yearly_utilization = kpi_calculator.calculate_utilization_percentage(yearly_hours, maxPossibleHours)

        employees_data.append({
            "id": employee.id,
            "name": getattr(employee, "name", str(employee)),
            "position": getattr(employee, "position", "Mitarbeiter"),
            "max_hours_per_week": employee.max_hours_per_week,
            "monthly_stats": {
                "possible_hours": round(monthly_stats['expected_monthly_hours'], 2),
                "worked_hours": round(monthly_stats['monthly_hours_worked'], 2),
                "overtime_hours": round(monthly_stats['overtime_hours'], 2),
                "undertime_hours": round(monthly_stats['undertime_hours'], 2),
                "shifts": monthly_stats['monthly_shifts'],
                "days_worked": monthly_stats['days_worked'],
                "absences": monthly_stats['planned_absences'],
                "utilization_percentage": round(monthly_stats['utilization_percentage'], 2),
            },
            "yearly_stats": {
                "worked_hours": round(yearly_hours, 2),
                "maxPossibleHours": maxPossibleHours,
                "shifts": yearly_shifts,
                "utilization_percentage": round(yearly_utilization, 2),
            },
        })

    return JsonResponse({
        "employees": employees_data,
        "month": month,
        "year": year,
        "total_working_days": total_working_days,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Helper functions moved to KPICalculator service


def get_company_holidays(year: int, company: Company) -> List[date]:
    """Return a list of holiday dates for the company in a given year."""
    from rostering_app.utils import get_holidays_for_year
    holidays = get_holidays_for_year(year)
    return [date(year, month, day) for (month, day) in holidays]


@csrf_exempt
@require_http_methods(["POST"])
def api_load_fixtures(request):
    """API endpoint to manually load fixtures."""
    try:
        from django.core.management import call_command
        from django.conf import settings
        import os

        # Get the fixtures directory
        fixtures_dir = os.path.join(settings.BASE_DIR, 'rostering_app', 'fixtures')

        # Load companies first
        companies_fixture = os.path.join(fixtures_dir, 'companies.json')
        if os.path.exists(companies_fixture):
            call_command('loaddata', companies_fixture, verbosity=0)

        # Load company-specific fixtures
        company_dirs = ['small_company', 'medium_company', 'large_company']

        for company_dir in company_dirs:
            company_path = os.path.join(fixtures_dir, company_dir)
            if os.path.exists(company_path):
                # Load employees
                employees_fixture = os.path.join(company_path, 'employees.json')
                if os.path.exists(employees_fixture):
                    call_command('loaddata', employees_fixture, verbosity=0)

                # Load shifts
                shifts_fixture = os.path.join(company_path, 'shifts.json')
                if os.path.exists(shifts_fixture):
                    call_command('loaddata', shifts_fixture, verbosity=0)

        return JsonResponse({'status': 'success', 'message': 'Fixtures loaded successfully'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_upload_status(request):
    """API endpoint to get upload status and instructions."""
    return JsonResponse({
        'status': 'ready',
        'message': 'Upload endpoint is ready for SQL dumps',
        'instructions': {
            'format': 'ZIP file containing benchmark_dump.sql',
            'max_size': '50MB',
            'endpoint': '/api/upload-benchmark-results/',
            'method': 'POST',
            'content_type': 'multipart/form-data',
            'export_command': 'python manage.py export_sql_dump --include-schedules'
        }
    })


def serve_vue_app(request):
    """Serve the Vue.js frontend application."""
    from django.conf import settings
    from django.http import HttpResponse
    import os

    # Path to the built Vue.js index.html file
    index_path = os.path.join(settings.BASE_DIR, 'dist', 'index.html')

    # Check if the built file exists
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Don't modify asset paths - let Django serve them from the dist directory
        return HttpResponse(content, content_type='text/html')
    else:
        # Fallback: return a simple message if the built file doesn't exist
        return HttpResponse(
            '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Shift Manager</title>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                    .container { max-width: 600px; margin: 0 auto; }
                    .error { color: #d32f2f; background: #ffebee; padding: 20px; border-radius: 5px; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Shift Manager</h1>
                    <div class="error">
                        <h2>Frontend Not Built</h2>
                        <p>The Vue.js frontend has not been built yet.</p>
                        <p>Please run <code>npm run build</code> to build the application.</p>
                    </div>
                    <p><a href="/admin/">Django Admin</a></p>
                </div>
            </body>
            </html>
            ''',
            content_type='text/html'
        )


@csrf_exempt
@require_http_methods(["GET"])
def api_company_analytics(request, company_id):
    """API endpoint to get all KPIs for all algorithms for a company and month, as in the benchmark results."""
    company = get_object_or_404(Company, pk=company_id)
    load_company_fixtures(company)

    year = int(request.GET.get('year', datetime.date.today().year))
    month = int(request.GET.get('month', datetime.date.today().month))

    # Get all available algorithms for this company
    available_algorithms = ScheduleEntry.objects.filter(company=company).values_list('algorithm', flat=True).distinct()
    available_algorithms = sorted([alg for alg in available_algorithms if alg])

    # Calculate KPIs directly using KPICalculator
    kpi_calculator = KPICalculator(company)

    results = {}
    for algorithm in available_algorithms:
        start_time = time.time()

        # Get entries for this algorithm
        entries = ScheduleEntry.objects.filter(
            company=company,
            date__year=year,
            date__month=month,
            algorithm=algorithm
        )

        # Calculate company analytics
        company_analytics = kpi_calculator.calculate_company_analytics(
            list(entries), year, month, algorithm
        )

        # Calculate coverage stats
        first_day = datetime.date(year, month, 1)
        last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])
        coverage_stats = kpi_calculator.calculate_coverage_stats(
            list(entries), first_day, last_day
        )

        # Extract coverage rates from calculated data
        coverage_rates = {}
        for stat in coverage_stats:
            shift_name = stat['shift']['name']
            coverage_rates[shift_name] = stat['coverage_percentage']

        runtime = time.time() - start_time
        results[algorithm] = {
            'total_hours_worked': company_analytics['total_hours_worked'],
            'avg_hours_per_employee': company_analytics['avg_hours_per_employee'],
            'hours_std_dev': company_analytics['hours_std_dev'],
            'hours_cv': company_analytics['hours_cv'],
            'gini_coefficient': company_analytics['gini_coefficient'],
            'constraint_violations': company_analytics['total_weekly_violations'],
            'coverage_rates': coverage_rates,
            'min_hours': company_analytics['min_hours'],
            'max_hours': company_analytics['max_hours'],
            'total_working_days': len(coverage_stats),
            'runtime': runtime,
        }
    return JsonResponse({'algorithms': results, 'year': year, 'month': month})
