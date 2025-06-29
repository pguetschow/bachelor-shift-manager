import calendar
import datetime
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rostering_app.models import ScheduleEntry, Employee, Shift, Company
from rostering_app.utils import is_holiday, is_sunday, is_non_working_day, get_working_days_in_range, \
    get_non_working_days_in_range, get_shift_display_name, monthly_hours
import subprocess
import os


def load_company_fixtures(company):
    """Load fixtures for the specified company."""
    # Placeholder for loading fixtures for the specified company
    return True


def company_selection(request):
    """Landing page for selecting company size."""
    companies = Company.objects.all()

    # Calculate dynamic statistics for each company
    for company in companies:
        employee_count = Employee.objects.filter(company=company).count()
        shift_count = Shift.objects.filter(company=company).count()

        # Update the description dynamically
        company.dynamic_description = f"{employee_count} Mitarbeiter, {shift_count} Schichten"
        company.employee_count = employee_count
        company.shift_count = shift_count

    return render(request, 'rostering_app/company_selection.html', {
        'companies': companies
    })


def schedule_dashboard(request, company_id):
    """Main dashboard showing current month overview."""
    company = get_object_or_404(Company, pk=company_id)
    load_company_fixtures(company)

    # Get current date or from query params
    today = datetime.date.today()
    year_param = request.GET.get('year', '')
    month_param = request.GET.get('month', '')

    # Handle empty string parameters by using defaults
    try:
        year = int(year_param) if year_param else today.year
        month = int(month_param) if month_param else today.month
    except ValueError:
        year = today.year
        month = today.month

    # Calculate date range
    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])

    # Get statistics
    total_employees = Employee.objects.filter(company=company).count()
    total_shifts = Shift.objects.filter(company=company).count()

    # Algorithm filter
    available_algorithms = ScheduleEntry.objects.filter(company=company).values_list('algorithm', flat=True).distinct()
    available_algorithms = sorted([alg for alg in available_algorithms if alg])
    selected_algorithm = request.GET.get('algorithm', '')
    if not selected_algorithm and 'Linear Programming (ILP)' in available_algorithms:
        selected_algorithm = 'Linear Programming (ILP)'

    # Get schedule entries for the month
    entry_filter = {
        'company': company,
        'date__gte': first_day,
        'date__lte': last_day
    }
    if selected_algorithm:
        entry_filter['algorithm'] = selected_algorithm
    entries = ScheduleEntry.objects.filter(**entry_filter)

    # Calculate coverage statistics
    coverage_stats = calculate_coverage_stats(entries, first_day, last_day, company)

    # Get employees with most/least hours
    employee_hours = calculate_employee_hours_with_month_boundaries(entries, first_day, last_day)
    top_employees = sorted(employee_hours.items(), key=lambda x: x[1], reverse=True)[:5]

    context = {
        'company': company,
        'company_name': company.name,
        'current_date': today,
        'current_month': first_day,
        'year': year,
        'month': month,
        'total_employees': total_employees,
        'total_shifts': total_shifts,
        'coverage_stats': coverage_stats,
        'top_employees': top_employees,
        'prev_month': (first_day - datetime.timedelta(days=1)).strftime('%Y-%m'),
        'next_month': (last_day + datetime.timedelta(days=1)).strftime('%Y-%m'),
        'available_algorithms': available_algorithms,
        'selected_algorithm': selected_algorithm,
    }

    return render(request, 'rostering_app/dashboard.html', context)


def month_view(request, company_id):
    """Full month calendar view."""
    company = get_object_or_404(Company, pk=company_id)
    load_company_fixtures(company)

    today = datetime.date.today()
    year_param = request.GET.get('year', '')
    month_param = request.GET.get('month', '')

    # Handle empty string parameters by using defaults
    try:
        year = int(year_param) if year_param else today.year
        month = int(month_param) if month_param else today.month
    except ValueError:
        year = today.year
        month = today.month

    # Algorithm filter
    available_algorithms = ScheduleEntry.objects.filter(company=company).values_list('algorithm', flat=True).distinct()
    available_algorithms = sorted([alg for alg in available_algorithms if alg])
    selected_algorithm = request.GET.get('algorithm', '')
    if not selected_algorithm and 'Linear Programming (ILP)' in available_algorithms:
        selected_algorithm = 'Linear Programming (ILP)'

    cal = calendar.monthcalendar(year, month)
    month_data = []
    week_count = 0

    # Calculate date range for the month
    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])

    # Get working and non-working days for accurate statistics
    working_days = get_working_days_in_range(first_day, last_day, company)
    non_working_days = get_non_working_days_in_range(first_day, last_day, company)
    total_working_days = len(working_days)
    total_non_working_days = len(non_working_days)

    for week in cal:
        week_data = []
        has_day = any(day != 0 for day in week)
        if has_day:
            week_count += 1
        for day in week:
            if day == 0:
                week_data.append(None)
            else:
                date = datetime.date(year, month, day)
                entry_filter = {'date': date, 'company': company}
                if selected_algorithm:
                    entry_filter['algorithm'] = selected_algorithm
                entries = ScheduleEntry.objects.filter(**entry_filter)

                shifts_data = {}
                for shift in Shift.objects.filter(company=company):
                    shift_entries = entries.filter(shift=shift)
                    shifts_data[shift.name] = {
                        'count': shift_entries.count(),
                        'min_staff': shift.min_staff,
                        'max_staff': shift.max_staff,
                        'status': get_shift_status(
                            shift_entries.count(),
                            shift.min_staff,
                            shift.max_staff
                        )
                    }

                # Check if this is a non-working day
                is_holiday_day = is_holiday(date)
                is_sunday_day = is_sunday(date)
                is_non_working = is_non_working_day(date, company)

                week_data.append({
                    'day': day,
                    'date': date,
                    'shifts': shifts_data,
                    'is_today': date == datetime.date.today(),
                    'is_holiday': is_holiday_day,
                    'is_sunday': is_sunday_day,
                    'is_non_working': is_non_working
                })
        month_data.append(week_data)

    shifts = Shift.objects.filter(company=company)
    shifts_per_day = shifts.count()
    total_shifts = total_working_days * shifts_per_day

    prev_month = first_day - datetime.timedelta(days=1)
    next_month = last_day + datetime.timedelta(days=1)

    context = {
        'company': company,
        'company_name': company.name,
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'month_data': month_data,
        'shifts': shifts,
        'prev_year': prev_month.year,
        'prev_month': prev_month.month,
        'next_year': next_month.year,
        'next_month': next_month.month,
        'total_working_days': total_working_days,
        'total_non_working_days': total_non_working_days,
        'shifts_per_day': shifts_per_day,
        'total_shifts': total_shifts,
        'available_algorithms': available_algorithms,
        'selected_algorithm': selected_algorithm,
    }
    return render(request, 'rostering_app/month_view.html', context)


def day_view(request, company_id, date):
    """Detailed view for a specific day."""
    company = get_object_or_404(Company, pk=company_id)
    load_company_fixtures(company)

    try:
        date_obj = datetime.datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        raise Http404("Invalid date format")

    # Algorithm filter
    available_algorithms = ScheduleEntry.objects.filter(company=company).values_list('algorithm', flat=True).distinct()
    available_algorithms = sorted([alg for alg in available_algorithms if alg])
    selected_algorithm = request.GET.get('algorithm', '')
    if not selected_algorithm and 'Linear Programming (ILP)' in available_algorithms:
        selected_algorithm = 'Linear Programming (ILP)'

    # Get all shifts for this day
    shifts_data = []
    for shift in Shift.objects.filter(company=company):
        entry_filter = {'date': date_obj, 'shift': shift, 'company': company}
        if selected_algorithm:
            entry_filter['algorithm'] = selected_algorithm
        entries = ScheduleEntry.objects.filter(**entry_filter).select_related('employee')

        count = entries.count()
        # Calculate percentage for progress bar
        percentage = round((count / shift.max_staff) * 100, 1) if shift.max_staff > 0 else 0

        shifts_data.append({
            'shift': shift,
            'employees': [entry.employee for entry in entries],
            'count': count,
            'percentage': percentage,
            'status': get_shift_status(count,
                                       shift.min_staff,
                                       shift.max_staff)
        })

    # Get available employees for each shift
    all_employees = Employee.objects.filter(company=company)
    available_by_shift = {}

    for shift in Shift.objects.filter(company=company):
        entry_filter = {'date': date_obj, 'company': company}
        if selected_algorithm:
            entry_filter['algorithm'] = selected_algorithm
        assigned = ScheduleEntry.objects.filter(**entry_filter).values_list('employee_id', flat=True)

        available = []
        for emp in all_employees:
            if emp.id not in assigned and date not in emp.absences:
                available.append(emp)

        available_by_shift[shift.id] = available

    context = {
        'company': company,
        'company_name': company.name,
        'date': date_obj,
        'shifts_data': shifts_data,
        'available_by_shift': available_by_shift,
        'prev_date': (date_obj - datetime.timedelta(days=1)).strftime('%Y-%m-%d'),
        'next_date': (date_obj + datetime.timedelta(days=1)).strftime('%Y-%m-%d'),
        'available_algorithms': available_algorithms,
        'selected_algorithm': selected_algorithm,
    }

    return render(request, 'rostering_app/day_view.html', context)


def employee_view(request, company_id, employee_id):
    """View for individual employee schedule."""
    company = get_object_or_404(Company, pk=company_id)
    load_company_fixtures(company)
    employee = get_object_or_404(Employee, pk=employee_id, company=company)

    # Get current month or from query
    today = datetime.date.today()
    year_param = request.GET.get('year', '')
    month_param = request.GET.get('month', '')

    # Handle empty string parameters by using defaults
    try:
        year = int(year_param) if year_param else today.year
        month = int(month_param) if month_param else today.month
    except ValueError:
        year = today.year
        month = today.month
    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])

    # Algorithm filter
    available_algorithms = ScheduleEntry.objects.filter(company=company).values_list('algorithm', flat=True).distinct()
    available_algorithms = sorted([alg for alg in available_algorithms if alg])
    selected_algorithm = request.GET.get('algorithm', '')
    if not selected_algorithm and 'Linear Programming (ILP)' in available_algorithms:
        selected_algorithm = 'Linear Programming (ILP)'

    # Get employee's schedule
    entry_filter = {
        'employee': employee,
        'date__gte': first_day,
        'date__lte': last_day
    }
    if selected_algorithm:
        entry_filter['algorithm'] = selected_algorithm
    entries = ScheduleEntry.objects.filter(**entry_filter).order_by('date')

    # Calculate statistics
    total_hours = sum(calculate_shift_hours_in_month(entry.shift, entry.date, first_day, last_day) for entry in entries)
    total_shifts = entries.count()
    average_hours_per_shift = total_hours / total_shifts if total_shifts > 0 else 0
    shifts_by_type = {}
    for shift in Shift.objects.filter(company=company):
        count = entries.filter(shift=shift).count()
        shifts_by_type[shift.name] = count

    # Build calendar
    cal_data = build_employee_calendar(year, month, entries, employee.absences)

    context = {
        'company': company,
        'company_name': company.name,
        'employee': employee,
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'total_hours': total_hours,
        'total_shifts': total_shifts,
        'average_hours_per_shift': average_hours_per_shift,
        'shifts_by_type': shifts_by_type,
        'calendar_data': cal_data,
        'max_hours_per_week': employee.max_hours_per_week,
        'available_algorithms': available_algorithms,
        'selected_algorithm': selected_algorithm,
    }
    return render(request, 'rostering_app/employee_view.html', context)


def analytics_view(request, company_id):
    """Analytics and statistics view."""
    company = get_object_or_404(Company, pk=company_id)
    load_company_fixtures(company)

    # Use month-based date range
    today = datetime.date.today()
    year_param = request.GET.get('year', '')
    month_param = request.GET.get('month', '')

    # Handle empty string parameters by using defaults
    try:
        year = int(year_param) if year_param else today.year
        month = int(month_param) if month_param else today.month
    except ValueError:
        year = today.year
        month = today.month

    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])
    prev_month = first_day - datetime.timedelta(days=1)
    next_month = last_day + datetime.timedelta(days=1)

    # Algorithm filter
    available_algorithms = ScheduleEntry.objects.filter(company=company).values_list('algorithm', flat=True).distinct()
    available_algorithms = sorted([alg for alg in available_algorithms if alg])
    selected_algorithm = request.GET.get('algorithm', '')
    if not selected_algorithm and 'Linear Programming (ILP)' in available_algorithms:
        selected_algorithm = 'Linear Programming (ILP)'

    entry_filter = {
        'date__gte': first_day,
        'date__lte': last_day,
        'company': company
    }
    if selected_algorithm:
        entry_filter['algorithm'] = selected_algorithm
    entries = ScheduleEntry.objects.filter(**entry_filter)

    # Get working days for accurate KPI calculations
    working_days = get_working_days_in_range(first_day, last_day, company)
    total_working_days = len(working_days)

    stats = {
        'total_shifts': entries.count(),
        'coverage_by_shift': {},
        'employee_distribution': {},
        'weekly_patterns': {},
        'total_working_days': total_working_days,
    }

    for shift in Shift.objects.filter(company=company):
        shift_entries = entries.filter(shift=shift)
        # Only count working days for coverage calculation
        if total_working_days > 0:
            avg_coverage = shift_entries.count() / total_working_days
            stats['coverage_by_shift'][shift.name] = {
                'average': round(avg_coverage, 1),
                'min': shift.min_staff,
                'max': shift.max_staff,
                'percentage': round((avg_coverage / shift.max_staff) * 100, 1) if shift.max_staff > 0 else 0
            }

    employee_stats = []
    for employee in Employee.objects.filter(company=company):
        emp_entries = entries.filter(employee=employee)
        hours = sum(calculate_shift_hours_in_month(e.shift, e.date, first_day, last_day) for e in emp_entries)
        # Calculate utilization based on working days only
        working_weeks = total_working_days / 7 if total_working_days > 0 else 0
        max_possible_hours = employee.max_hours_per_week * working_weeks
        utilization = round((hours / max_possible_hours) * 100, 1) if max_possible_hours > 0 else 0

        employee_stats.append({
            'name': employee.name,
            'shifts': emp_entries.count(),
            'hours': hours,
            'utilization': utilization
        })

    stats['employee_distribution'] = sorted(employee_stats, key=lambda x: x['hours'], reverse=True)[:10]

    context = {
        'company': company,
        'company_name': company.name,
        'stats': stats,
        'start_date': first_day,
        'end_date': last_day,
        'available_algorithms': available_algorithms,
        'selected_algorithm': selected_algorithm,
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'prev_year': prev_month.year,
        'prev_month': prev_month.month,
        'next_year': next_month.year,
        'next_month': next_month.month,
    }
    return render(request, 'rostering_app/analytics.html', context)


def api_schedule_data(request, company_id, year, month):
    """API endpoint for AJAX schedule data."""
    company = get_object_or_404(Company, pk=company_id)
    load_company_fixtures(company)

    year = int(year)
    month = int(month)

    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])

    entries = ScheduleEntry.objects.filter(
        date__gte=first_day,
        date__lte=last_day,
        company=company
    ).select_related('employee', 'shift')

    # Format data for JSON
    schedule_data = {}
    for entry in entries:
        date_str = entry.date.strftime('%Y-%m-%d')
        if date_str not in schedule_data:
            schedule_data[date_str] = {}

        shift_name = entry.shift.name
        if shift_name not in schedule_data[date_str]:
            schedule_data[date_str][shift_name] = []

        schedule_data[date_str][shift_name].append({
            'id': entry.employee.id,
            'name': entry.employee.name
        })

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
                'name': Employee.objects.get(id=emp_id).name,
                'hours': hours
            }
            for emp_id, hours in top_employees
        ]
    })


# Helper functions
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


def calculate_coverage_stats(entries, start_date, end_date, company):
    """Calculate coverage statistics for date range."""
    stats = []
    for shift in Shift.objects.filter(company=company):
        shift_entries = entries.filter(shift=shift)

        # Only count working days for KPI calculations
        working_days = get_working_days_in_range(start_date, end_date, company)
        total_working_days = len(working_days)

        if total_working_days > 0:
            avg_staff = shift_entries.count() / total_working_days if total_working_days > 0 else 0
            # Calculate actual staffing percentage (how well staffed relative to max_staff)
            coverage_percentage = round((avg_staff / shift.max_staff) * 100, 1) if shift.max_staff > 0 else 0

            stats.append({
                'shift': {
                    'id': shift.id,
                    'name': shift.name,
                    'start_time': shift.start.isoformat(),
                    'end_time': shift.end.isoformat(),
                    'min_staff': shift.min_staff,
                    'max_staff': shift.max_staff
                },
                'coverage_percentage': coverage_percentage,
                'avg_staff': round(avg_staff, 1),
                'status': get_shift_status(avg_staff, shift.min_staff, shift.max_staff)
            })

    return stats


def calculate_employee_hours_with_month_boundaries(entries, month_start_date, month_end_date):
    """Calculate total hours per employee, properly handling night shifts that overlap months."""
    hours = {}

    for entry in entries:
        emp_id = entry.employee.id
        shift = entry.shift
        shift_date = entry.date

        # Calculate the actual hours for this shift within the specified month
        actual_hours = calculate_shift_hours_in_month(shift, shift_date, month_start_date, month_end_date)

        hours[emp_id] = hours.get(emp_id, 0) + actual_hours

    return hours


def calculate_shift_hours_in_date_range(shift, shift_date, start_date, end_date):
    """Calculate how many hours of a shift fall within the specified date range."""
    from datetime import datetime, timedelta

    # Create datetime objects for shift start and end
    shift_start_dt = datetime.combine(shift_date, shift.start)
    shift_end_dt = datetime.combine(shift_date, shift.end)

    # If it's a night shift (end time < start time), the end is on the next day
    if shift.end < shift.start:
        shift_end_dt += timedelta(days=1)

    # Create datetime objects for date range boundaries
    range_start_dt = datetime.combine(start_date, datetime.min.time())
    range_end_dt = datetime.combine(end_date, datetime.max.time())

    # Calculate the overlap between the shift and the date range
    effective_start = max(shift_start_dt, range_start_dt)
    effective_end = min(shift_end_dt, range_end_dt)

    # If there's no overlap, return 0 hours
    if effective_end <= effective_start:
        return 0

    # Calculate the hours within the date range
    duration_seconds = (effective_end - effective_start).total_seconds()
    return duration_seconds / 3600


def calculate_shift_hours_in_month(shift, shift_date, month_start_date, month_end_date):
    """Calculate how many hours of a shift fall within the specified month."""
    return calculate_shift_hours_in_date_range(shift, shift_date, month_start_date, month_end_date)


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

    # Get query parameters
    year = int(request.GET.get('year', datetime.date.today().year))
    month = int(request.GET.get('month', datetime.date.today().month))
    algorithm = request.GET.get('algorithm', '')

    # Calculate date range
    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])

    # Get schedule entries
    entry_filter = {
        'company': company,
        'date__gte': first_day,
        'date__lte': last_day
    }
    if algorithm:
        entry_filter['algorithm'] = algorithm

    entries = ScheduleEntry.objects.filter(**entry_filter)

    # Calculate statistics
    coverage_stats = calculate_coverage_stats(entries, first_day, last_day, company)
    employee_hours = calculate_employee_hours_with_month_boundaries(entries, first_day, last_day)
    top_employees = sorted(employee_hours.items(), key=lambda x: x[1], reverse=True)[:5]

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
                'name': Employee.objects.get(id=emp_id).name,
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
    employees = Employee.objects.filter(company=company)

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

    try:
        target_date = datetime.datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    # Get schedule entries for the specific date
    entries = ScheduleEntry.objects.filter(
        company=company,
        date=target_date
    )

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
            'id': shift.id,
            'name': shift.name,
            'start_time': shift.start.isoformat(),
            'end_time': shift.end.isoformat(),
            'min_staff': shift.min_staff,
            'max_staff': shift.max_staff,
            'assigned_count': len(assigned_employees),
            'assigned_employees': assigned_employees,
            'status': get_shift_status(len(assigned_employees), shift.min_staff, shift.max_staff)
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
        'total_assignments': sum(len(shift['assigned_employees']) for shift in shifts_data)
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_company_employee_schedule(request, company_id, employee_id):
    """API endpoint to get schedule data for a specific employee."""
    company = get_object_or_404(Company, pk=company_id)
    employee = get_object_or_404(Employee, pk=employee_id, company=company)

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
    total_hours = sum(calculate_shift_hours_in_month(entry.shift, entry.date, first_day, last_day) for entry in entries)
    total_shifts = entries.count()
    average_hours_per_shift = total_hours / total_shifts if total_shifts > 0 else 0

    # Calculate weekly workload
    weekly_workload = []
    current_week = first_day
    while current_week <= last_day:
        week_end = min(current_week + datetime.timedelta(days=6), last_day)
        week_entries = entries.filter(date__gte=current_week, date__lte=week_end)
        week_hours = sum(
            calculate_shift_hours_in_month(entry.shift, entry.date, current_week, week_end) for entry in week_entries)
        weekly_workload.append(round(week_hours, 3))
        current_week += datetime.timedelta(days=7)

    # Calculate utilization percentage based on monthly hours
    # Calculate exact monthly hours based on working days
    working_days = get_working_days_in_range(first_day, last_day, company)
    total_working_days = len(working_days)

    # Calculate max monthly hours using the new function
    max_monthly_hours = monthly_hours(year, month, employee.max_hours_per_week, company)
    utilization_percentage = (total_hours / max_monthly_hours * 100) if max_monthly_hours > 0 else 0

    return JsonResponse({
        'employee': {
            'id': employee.id,
            'name': employee.name,
            'position': getattr(employee, 'position', 'Mitarbeiter'),
            'max_hours_per_week': employee.max_hours_per_week,
            'preferred_shifts': employee.preferred_shifts
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
    total_hours = sum(calculate_shift_hours_in_month(entry.shift, entry.date, first_day, last_day) for entry in entries)
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
            calculate_shift_hours_in_month(entry.shift, entry.date, month_start, month_end) for entry in month_entries)
        monthly_hours_list.append(round(month_hours, 3))
        monthly_shifts.append(month_entries.count())

    # Calculate yearly utilization using monthly hours calculation
    total_possible_yearly_hours = 0
    for month in range(1, 13):
        month_possible_hours = monthly_hours(year, month, employee.max_hours_per_week, company)
        total_possible_yearly_hours += month_possible_hours

    yearly_utilization = (total_hours / total_possible_yearly_hours * 100) if total_possible_yearly_hours > 0 else 0

    return JsonResponse({
        'employee': {
            'id': employee.id,
            'name': employee.name,
            'position': getattr(employee, 'position', 'Mitarbeiter'),
            'max_hours_per_week': employee.max_hours_per_week,
            'preferred_shifts': employee.preferred_shifts
        },
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
def api_company_employee_statistics(request, company_id):
    """API endpoint to get comprehensive employee statistics for a company."""
    company = get_object_or_404(Company, pk=company_id)

    # Get query parameters
    year = int(request.GET.get('year', datetime.date.today().year))
    month = int(request.GET.get('month', datetime.date.today().month))
    algorithm = request.GET.get('algorithm', '')

    # Calculate date ranges
    month_start = datetime.date(year, month, 1)
    month_end = datetime.date(year, month, calendar.monthrange(year, month)[1])
    year_start = datetime.date(year, 1, 1)
    year_end = datetime.date(year, 12, 31)

    # Get all employees for the company
    employees = Employee.objects.filter(company=company)

    # Get working days for the month
    working_days = get_working_days_in_range(month_start, month_end, company)
    total_working_days = len(working_days)

    employees_data = []
    for employee in employees:
        # Get employee's schedule entries for the month
        month_entry_filter = {
            'employee': employee,
            'date__gte': month_start,
            'date__lte': month_end
        }
        if algorithm:
            month_entry_filter['algorithm'] = algorithm

        month_entries = ScheduleEntry.objects.filter(**month_entry_filter)

        # Get employee's schedule entries for the year
        year_entry_filter = {
            'employee': employee,
            'date__gte': year_start,
            'date__lte': year_end
        }
        if algorithm:
            year_entry_filter['algorithm'] = algorithm

        year_entries = ScheduleEntry.objects.filter(**year_entry_filter)

        # Calculate monthly statistics
        monthly_hours_worked = sum(
            calculate_shift_hours_in_month(entry.shift, entry.date, month_start, month_end) for entry in month_entries)
        monthly_shifts = month_entries.count()

        # Calculate yearly statistics
        yearly_hours = sum(
            calculate_shift_hours_in_month(entry.shift, entry.date, year_start, year_end) for entry in year_entries)
        yearly_shifts = year_entries.count()

        # Calculate possible work hours for the month using the new function
        possible_monthly_hours = monthly_hours(year, month, employee.max_hours_per_week, company)

        # Calculate absences (days without shifts)
        absence_days = total_working_days - monthly_shifts

        # Calculate utilization percentages
        monthly_utilization = (monthly_hours_worked / possible_monthly_hours * 100) if possible_monthly_hours > 0 else 0
        yearly_utilization = (
                    yearly_hours / (employee.max_hours_per_week * 52) * 100) if employee.max_hours_per_week > 0 else 0

        employees_data.append({
            'id': employee.id,
            'name': employee.name,
            'position': getattr(employee, 'position', 'Mitarbeiter'),
            'max_hours_per_week': employee.max_hours_per_week,
            'monthly_stats': {
                'possible_hours': round(possible_monthly_hours, 2),
                'worked_hours': round(monthly_hours_worked, 2),
                'shifts': monthly_shifts,
                'absences': absence_days,
                'utilization_percentage': round(monthly_utilization, 2)
            },
            'yearly_stats': {
                'worked_hours': round(yearly_hours, 2),
                'shifts': yearly_shifts,
                'utilization_percentage': round(yearly_utilization, 2)
            }
        })

    return JsonResponse({
        'employees': employees_data,
        'month': month,
        'year': year,
        'total_working_days': total_working_days
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_run_benchmark(request):
    try:
        data = json.loads(request.body.decode())
        load_fixtures = data.get('load_fixtures', False)
    except Exception:
        load_fixtures = False

    cmd = ["python", "manage.py", "benchmark_algorithms"]
    if load_fixtures:
        cmd.append("--load-fixtures")
    # Run in background
    subprocess.Popen(cmd, cwd=os.path.dirname(os.path.dirname(__file__)))
    return JsonResponse({"status": "started", "load_fixtures": load_fixtures})
