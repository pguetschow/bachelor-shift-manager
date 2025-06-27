import datetime
import calendar
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, Http404
from django.db.models import Count, Q
from rostering_app.models import ScheduleEntry, Employee, Shift, Company


def load_company_fixtures(company):
    """Load fixtures for the specified company."""
    # Placeholder for loading fixtures for the specified company
    return True


def company_selection(request):
    """Landing page for selecting company size."""
    companies = Company.objects.all()
    return render(request, 'rostering_app/company_selection.html', {
        'companies': companies
    })


def schedule_dashboard(request, company_id):
    """Main dashboard showing current month overview."""
    company = get_object_or_404(Company, pk=company_id)
    load_company_fixtures(company)
    
    # Get current date or from query params
    today = datetime.date.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    
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
        'date__lte': last_day,
        'archived': False
    }
    if selected_algorithm:
        entry_filter['algorithm'] = selected_algorithm
    entries = ScheduleEntry.objects.filter(**entry_filter)
    
    # Calculate coverage statistics
    coverage_stats = calculate_coverage_stats(entries, first_day, last_day, company)
    
    # Get employees with most/least hours
    employee_hours = calculate_employee_hours(entries)
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

    year = int(request.GET.get('year', datetime.date.today().year))
    month = int(request.GET.get('month', datetime.date.today().month))

    # Algorithm filter
    available_algorithms = ScheduleEntry.objects.filter(company=company).values_list('algorithm', flat=True).distinct()
    available_algorithms = sorted([alg for alg in available_algorithms if alg])
    selected_algorithm = request.GET.get('algorithm', '')
    if not selected_algorithm and 'Linear Programming (ILP)' in available_algorithms:
        selected_algorithm = 'Linear Programming (ILP)'

    cal = calendar.monthcalendar(year, month)
    month_data = []
    week_count = 0

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
                entry_filter = {'date': date, 'archived': False, 'company': company}
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

                week_data.append({
                    'day': day,
                    'date': date,
                    'shifts': shifts_data,
                    'is_today': date == datetime.date.today()
                })
        month_data.append(week_data)

    shifts = Shift.objects.filter(company=company)
    days_per_week = 7
    total_workdays = week_count * days_per_week - 2
    total_weekends = week_count * 2
    shifts_per_day = shifts.count()
    total_shifts = week_count * days_per_week * shifts_per_day

    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])
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
        'total_workdays': total_workdays,
        'total_weekends': total_weekends,
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
        entry_filter = {'date': date_obj, 'shift': shift, 'archived': False, 'company': company}
        if selected_algorithm:
            entry_filter['algorithm'] = selected_algorithm
        entries = ScheduleEntry.objects.filter(**entry_filter).select_related('employee')
        
        shifts_data.append({
            'shift': shift,
            'employees': [entry.employee for entry in entries],
            'count': entries.count(),
            'status': get_shift_status(entries.count(), 
                                     shift.min_staff, 
                                     shift.max_staff)
        })
    
    # Get available employees for each shift
    all_employees = Employee.objects.filter(company=company)
    available_by_shift = {}
    
    for shift in Shift.objects.filter(company=company):
        entry_filter = {'date': date_obj, 'archived': False, 'company': company}
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
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
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
        'date__lte': last_day,
        'archived': False
    }
    if selected_algorithm:
        entry_filter['algorithm'] = selected_algorithm
    entries = ScheduleEntry.objects.filter(**entry_filter).order_by('date')

    # Calculate statistics
    total_hours = sum(entry.shift.get_duration() for entry in entries)
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
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
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
        'archived': False,
        'company': company
    }
    if selected_algorithm:
        entry_filter['algorithm'] = selected_algorithm
    entries = ScheduleEntry.objects.filter(**entry_filter)

    stats = {
        'total_shifts': entries.count(),
        'coverage_by_shift': {},
        'employee_distribution': {},
        'weekly_patterns': {},
    }
    for shift in Shift.objects.filter(company=company):
        shift_entries = entries.filter(shift=shift)
        dates = shift_entries.values('date').distinct().count()
        if dates > 0:
            avg_coverage = shift_entries.count() / dates
            stats['coverage_by_shift'][shift.name] = {
                'average': round(avg_coverage, 1),
                'min': shift.min_staff,
                'max': shift.max_staff,
                'percentage': round((avg_coverage / shift.max_staff) * 100, 1)
            }
    employee_stats = []
    for employee in Employee.objects.filter(company=company):
        emp_entries = entries.filter(employee=employee)
        hours = sum(e.shift.get_duration() for e in emp_entries)
        employee_stats.append({
            'name': employee.name,
            'shifts': emp_entries.count(),
            'hours': hours,
            'utilization': round((hours / (employee.max_hours_per_week * 4)) * 100, 1)
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
        archived=False,
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
    
    return JsonResponse({
        'success': True,
        'data': schedule_data,
        'year': year,
        'month': month
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
        total_days = (end_date - start_date).days + 1
        
        if total_days > 0:
            coverage_days = shift_entries.values('date').distinct().count()
            avg_staff = shift_entries.count() / total_days if total_days > 0 else 0
            
            stats.append({
                'shift': shift,
                'coverage_percentage': round((coverage_days / total_days) * 100, 1),
                'avg_staff': round(avg_staff, 1),
                'status': get_shift_status(avg_staff, shift.min_staff, shift.max_staff)
            })
    
    return stats


def calculate_employee_hours(entries):
    """Calculate total hours per employee."""
    hours = {}
    for entry in entries:
        emp_name = entry.employee.name
        duration = entry.shift.get_duration()
        hours[emp_name] = hours.get(emp_name, 0) + duration
    return hours


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
