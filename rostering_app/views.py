import calendar
import datetime
import json
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rostering_app.models import ScheduleEntry, Employee, Shift, Company
from rostering_app.utils import is_holiday, is_sunday, is_non_working_day, get_working_days_in_range, get_non_working_days_in_range, get_shift_display_name, monthly_hours
import subprocess
import os
from django.core.management import call_command
from django.conf import settings


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
    load_company_fixtures(company)
    
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
            'coverage_percentage': sum(stat['coverage_percentage'] for stat in coverage_stats) / len(coverage_stats) if coverage_stats else 0,
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
    load_company_fixtures(company)
    
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
    load_company_fixtures(company)
    
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
    load_company_fixtures(company)
    
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
@require_http_methods(["GET"])
def api_benchmark_status(request):
    """API endpoint to get comprehensive benchmark status including individual company status."""
    from .models import BenchmarkStatus, CompanyBenchmarkStatus
    import os
    import json
    
    # Get overall benchmark status
    status = BenchmarkStatus.get_current()
    
    # Company name mapping from benchmark command
    company_name_mapping = {
        'small_company': 'Kleines Unternehmen',
        'medium_company': 'Mittleres Unternehmen', 
        'large_company': 'Großes Unternehmen'
    }
    
    # Check export directory for results
    export_dir = 'export'
    has_overall_results = False
    overall_file = None
    
    if os.path.exists(export_dir):
        overall_file = os.path.join(export_dir, 'benchmark_results.json')
        has_overall_results = os.path.exists(overall_file)
    
    # Get individual company benchmark statuses
    company_statuses = CompanyBenchmarkStatus.objects.all()
    company_status_data = {}
    
    for status_obj in company_statuses:
        company_status_data[status_obj.company_name] = {
            'completed': status_obj.completed,
            'completed_at': status_obj.completed_at.isoformat() if status_obj.completed_at else None,
            'error_message': status_obj.error_message,
            'test_case': status_obj.test_case,
            'updated_at': status_obj.updated_at.isoformat()
        }
    
    # Check individual company result files
    results_status = {}
    for test_case, company_name in company_name_mapping.items():
        test_dir = os.path.join(export_dir, test_case) if os.path.exists(export_dir) else None
        results_file = os.path.join(test_dir, 'results.json') if test_dir else None
        
        has_results = results_file and os.path.exists(results_file)
        results_status[company_name] = {
            'has_results': has_results,
            'test_case': test_case,
            'results_file': results_file if has_results else None
        }
    
    return JsonResponse({
        # Overall benchmark status
        'status': status.status,
        'started_at': status.started_at.isoformat() if status.started_at else None,
        'completed_at': status.completed_at.isoformat() if status.completed_at else None,
        'load_fixtures': status.load_fixtures,
        'error_message': status.error_message,
        'updated_at': status.updated_at.isoformat(),
        
        # Individual company statuses
        'company_statuses': company_status_data,
        
        # Results file status
        'results_status': results_status,
        'has_overall_results': has_overall_results,
        'overall_file': overall_file if has_overall_results else None
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_run_benchmark(request):
    """API endpoint to start benchmark with status tracking."""
    from .models import BenchmarkStatus
    
    try:
        data = json.loads(request.body.decode())
        load_fixtures = data.get('load_fixtures', False)
        force = data.get('force', False)
    except Exception:
        load_fixtures = False
        force = False
    
    # Check current status
    benchmark_status = BenchmarkStatus.get_current()
    
    if benchmark_status.status == 'running' and not force:
        return JsonResponse({
            "status": "error",
            "message": "Benchmark is already running. Use force=true to override."
        }, status=409)
    
    # Build command
    cmd = ["python", "manage.py", "benchmark_algorithms"]
    if load_fixtures:
        cmd.append("--load-fixtures")
    if force:
        cmd.append("--force")
    
    # Run in background
    subprocess.Popen(cmd, cwd=os.path.dirname(os.path.dirname(__file__)))
    
    return JsonResponse({
        "status": "started", 
        "load_fixtures": load_fixtures,
        "force": force
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_reset_benchmark(request):
    """API endpoint to reset benchmark status."""
    try:
        # Reset benchmark status for all companies
        from rostering_app.models import CompanyBenchmarkStatus
        CompanyBenchmarkStatus.objects.all().delete()
        
        return JsonResponse({'status': 'success', 'message': 'Benchmark status reset successfully'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


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
@require_http_methods(["POST"])
def api_upload_benchmark_results(request):
    """API endpoint to upload benchmark results from local export."""
    from django.core.files.uploadedfile import UploadedFile
    from django.db import transaction
    import zipfile
    import tempfile
    import os
    
    try:
        # Check if file was uploaded
        if 'file' not in request.FILES:
            return JsonResponse({
                'status': 'error',
                'message': 'No file uploaded. Please provide a ZIP file.'
            }, status=400)
        
        uploaded_file = request.FILES['file']
        
        # Validate file type
        if not uploaded_file.name.endswith('.zip'):
            return JsonResponse({
                'status': 'error',
                'message': 'Please upload a ZIP file containing benchmark export data.'
            }, status=400)
        
        # Extract and process the ZIP file
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save uploaded file temporarily
            temp_zip_path = os.path.join(temp_dir, 'upload.zip')
            with open(temp_zip_path, 'wb') as f:
                for chunk in uploaded_file.chunks():
                    f.write(chunk)
            
            # Extract ZIP file
            with zipfile.ZipFile(temp_zip_path, 'r') as zipf:
                zipf.extractall(temp_dir)
            
            # Look for the JSON file
            json_file = None
            for file_name in os.listdir(temp_dir):
                if file_name.endswith('.json'):
                    json_file = os.path.join(temp_dir, file_name)
                    break
            
            if not json_file:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No JSON file found in the ZIP archive.'
                }, status=400)
            
            # Load and validate JSON data
            with open(json_file, 'r', encoding='utf-8') as f:
                import json
                export_data = json.load(f)
            
            # Validate required fields
            required_fields = ['metadata', 'companies', 'employees', 'shifts', 'company_benchmark_statuses']
            for field in required_fields:
                if field not in export_data:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Missing required field: {field}'
                    }, status=400)
            
            # Import data with transaction
            with transaction.atomic():
                import_results = _import_benchmark_data(export_data)
            
            return JsonResponse({
                'status': 'success',
                'message': 'Benchmark results uploaded successfully',
                'import_summary': import_results
            })
            
    except zipfile.BadZipFile:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid ZIP file format.'
        }, status=400)
    except json.JSONDecodeError as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Invalid JSON format: {str(e)}'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Upload failed: {str(e)}'
        }, status=500)


def _import_benchmark_data(export_data):
    """Import benchmark data from export format."""
    from datetime import datetime
    from .models import Company, Employee, Shift, ScheduleEntry, BenchmarkStatus, CompanyBenchmarkStatus
    
    import_results = {
        'companies_imported': 0,
        'employees_imported': 0,
        'shifts_imported': 0,
        'schedule_entries_imported': 0,
        'company_statuses_imported': 0,
        'errors': []
    }
    
    # Validate export data structure
    if not export_data.get('companies'):
        import_results['errors'].append("No companies found in export data")
        return import_results
    
    # Clear all existing data first
    try:
        ScheduleEntry.objects.all().delete()
        Employee.objects.all().delete()
        Shift.objects.all().delete()
        Company.objects.all().delete()
        CompanyBenchmarkStatus.objects.all().delete()
    except Exception as e:
        import_results['errors'].append(f"Failed to clear existing data: {str(e)}")
        return import_results
    
    # Import companies first (no foreign key dependencies)
    company_id_mapping = {}  # Map old IDs to new company objects
    for company_data in export_data['companies']:
        try:
            company = Company.objects.create(
                name=company_data['name'],
                size=company_data['size'],
                description=company_data['description'],
                icon=company_data['icon'],
                color=company_data['color'],
                sunday_is_workday=company_data['sunday_is_workday'],
            )
            
            # Store mapping from old ID to new company object
            company_id_mapping[company_data['id']] = company
            import_results['companies_imported'] += 1
        except Exception as e:
            import_results['errors'].append(f"Company {company_data.get('name', 'Unknown')}: {str(e)}")
    
    # Import employees (depend on companies)
    employee_id_mapping = {}  # Map old IDs to new employee objects
    for employee_data in export_data.get('employees', []):
        try:
            # Get the company using the mapping
            company = company_id_mapping.get(employee_data['company_id'])
            if not company:
                import_results['errors'].append(f"Employee {employee_data.get('name', 'Unknown')}: Company not found")
                continue
            
            employee = Employee.objects.create(
                company=company,
                name=employee_data['name'],
                max_hours_per_week=employee_data['max_hours_per_week'],
                absences=employee_data['absences'],
                preferred_shifts=employee_data['preferred_shifts'],
            )
            
            # Store mapping from old ID to new employee object
            employee_id_mapping[employee_data['id']] = employee
            import_results['employees_imported'] += 1
        except Exception as e:
            import_results['errors'].append(f"Employee {employee_data.get('name', 'Unknown')}: {str(e)}")
    
    # Import shifts (depend on companies)
    shift_id_mapping = {}  # Map old IDs to new shift objects
    for shift_data in export_data.get('shifts', []):
        try:
            # Get the company using the mapping
            company = company_id_mapping.get(shift_data['company_id'])
            if not company:
                import_results['errors'].append(f"Shift {shift_data.get('name', 'Unknown')}: Company not found")
                continue
            
            shift = Shift.objects.create(
                company=company,
                name=shift_data['name'],
                start=datetime.fromisoformat(shift_data['start']).time(),
                end=datetime.fromisoformat(shift_data['end']).time(),
                min_staff=shift_data['min_staff'],
                max_staff=shift_data['max_staff'],
            )
            
            # Store mapping from old ID to new shift object
            shift_id_mapping[shift_data['id']] = shift
            import_results['shifts_imported'] += 1
        except Exception as e:
            import_results['errors'].append(f"Shift {shift_data.get('name', 'Unknown')}: {str(e)}")
    
    # Import schedule entries if present (depend on employees, shifts, and companies)
    if 'schedule_entries' in export_data and export_data['schedule_entries']:
        for entry_data in export_data['schedule_entries']:
            try:
                # Get the related objects using mappings
                employee = employee_id_mapping.get(entry_data['employee_id'])
                shift = shift_id_mapping.get(entry_data['shift_id'])
                company = company_id_mapping.get(entry_data['company_id']) if entry_data['company_id'] else None
                
                if not employee:
                    import_results['errors'].append(f"Schedule entry: Employee not found")
                    continue
                if not shift:
                    import_results['errors'].append(f"Schedule entry: Shift not found")
                    continue
                
                ScheduleEntry.objects.create(
                    employee=employee,
                    date=datetime.fromisoformat(entry_data['date']).date(),
                    shift=shift,
                    company=company,
                    algorithm=entry_data['algorithm'],
                )
                import_results['schedule_entries_imported'] += 1
            except Exception as e:
                import_results['errors'].append(f"Schedule entry: {str(e)}")
    
    # Import company benchmark statuses
    for status_data in export_data.get('company_benchmark_statuses', []):
        try:
            status = CompanyBenchmarkStatus.objects.create(
                company_name=status_data['company_name'],
                test_case=status_data['test_case'],
                completed=status_data['completed'],
                completed_at=datetime.fromisoformat(status_data['completed_at']) if status_data['completed_at'] else None,
                error_message=status_data['error_message'],
            )
            import_results['company_statuses_imported'] += 1
        except Exception as e:
            import_results['errors'].append(f"Company status {status_data.get('company_name', 'Unknown')}: {str(e)}")
    
    # Update overall benchmark status if metadata is present
    if 'metadata' in export_data and 'benchmark_status' in export_data['metadata']:
        try:
            benchmark_status = BenchmarkStatus.get_current()
            bs_data = export_data['metadata']['benchmark_status']
            
            benchmark_status.status = bs_data['status']
            if bs_data['started_at']:
                benchmark_status.started_at = datetime.fromisoformat(bs_data['started_at'])
            if bs_data['completed_at']:
                benchmark_status.completed_at = datetime.fromisoformat(bs_data['completed_at'])
            benchmark_status.load_fixtures = bs_data['load_fixtures']
            benchmark_status.error_message = bs_data['error_message']
            benchmark_status.save()
        except Exception as e:
            import_results['errors'].append(f"Benchmark status: {str(e)}")
    
    return import_results


@csrf_exempt
@require_http_methods(["GET"])
def api_upload_status(request):
    """API endpoint to get upload status and instructions."""
    return JsonResponse({
        'status': 'ready',
        'message': 'Upload endpoint is ready',
        'instructions': {
            'format': 'ZIP file containing benchmark_export.json',
            'max_size': '50MB',
            'endpoint': '/api/upload-benchmark-results/',
            'method': 'POST',
            'content_type': 'multipart/form-data'
        }
    })


def serve_vue_app(request):
    """Serve the Vue.js frontend application."""
    from django.shortcuts import render
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
