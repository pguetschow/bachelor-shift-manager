import datetime
import calendar
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, Http404
from django.db.models import Count, Q
from rostering_app.models import ScheduleEntry, Employee, ShiftType


def load_company_fixtures(company_size):
    """Load fixtures for the specified company size."""
    valid_sizes = ['small', 'medium', 'large']
    if company_size not in valid_sizes:
        raise Http404("Invalid company size")
    
    # In a real application, you would load the appropriate fixtures here
    # For now, we'll just use whatever is in the database
    return True


def company_selection(request):
    """Landing page for selecting company size."""
    companies = [
        {
            'size': 'small',
            'name': 'Kleines Unternehmen',
            'description': '10 Mitarbeiter, 2 Schichten',
            'icon': '🏪',
            'color': 'primary'
        },
        {
            'size': 'medium',
            'name': 'Mittleres Unternehmen',
            'description': '30 Mitarbeiter, 3 Schichten',
            'icon': '🏥',
            'color': 'success'
        },
        {
            'size': 'large',
            'name': 'Großes Unternehmen',
            'description': '100 Mitarbeiter, 3 Schichten',
            'icon': '🏭',
            'color': 'warning'
        }
    ]
    
    return render(request, 'rostering_app/company_selection.html', {
        'companies': companies
    })


def schedule_dashboard(request, company_size):
    """Main dashboard showing current month overview."""
    load_company_fixtures(company_size)
    
    # Get current date or from query params
    today = datetime.date.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    
    # Calculate date range
    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])
    
    # Get statistics
    total_employees = Employee.objects.count()
    total_shifts = ShiftType.objects.count()
    
    # Get schedule entries for the month
    entries = ScheduleEntry.objects.filter(
        date__gte=first_day,
        date__lte=last_day,
        archived=False
    )
    
    # Calculate coverage statistics
    coverage_stats = calculate_coverage_stats(entries, first_day, last_day)
    
    # Get employees with most/least hours
    employee_hours = calculate_employee_hours(entries)
    top_employees = sorted(employee_hours.items(), key=lambda x: x[1], reverse=True)[:5]
    
    context = {
        'company_size': company_size,
        'company_name': get_company_name(company_size),
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
    }
    
    return render(request, 'rostering_app/dashboard.html', context)


# def month_view(request, company_size):
#     """Full month calendar view."""
#     load_company_fixtures(company_size)
#
#     # Get date parameters
#     year = int(request.GET.get('year', datetime.date.today().year))
#     month = int(request.GET.get('month', datetime.date.today().month))
#
#     # Build calendar data
#     cal = calendar.monthcalendar(year, month)
#     month_data = []
#
#     for week in cal:
#         week_data = []
#         for day in week:
#             if day == 0:
#                 week_data.append(None)
#             else:
#                 date = datetime.date(year, month, day)
#                 entries = ScheduleEntry.objects.filter(date=date, archived=False)
#
#                 shifts_data = {}
#                 for shift_type in ShiftType.objects.all():
#                     shift_entries = entries.filter(shift_type=shift_type)
#                     shifts_data[shift_type.name] = {
#                         'count': shift_entries.count(),
#                         'min_staff': shift_type.min_staff,
#                         'max_staff': shift_type.max_staff,
#                         'status': get_shift_status(shift_entries.count(),
#                                                  shift_type.min_staff,
#                                                  shift_type.max_staff)
#                     }
#
#                 week_data.append({
#                     'day': day,
#                     'date': date,
#                     'shifts': shifts_data,
#                     'is_today': date == datetime.date.today()
#                 })
#         month_data.append(week_data)
#
#     # Navigation
#     first_day = datetime.date(year, month, 1)
#     last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])
#     prev_month = first_day - datetime.timedelta(days=1)
#     next_month = last_day + datetime.timedelta(days=1)
#
#     context = {
#         'company_size': company_size,
#         'company_name': get_company_name(company_size),
#         'year': year,
#         'month': month,
#         'month_name': calendar.month_name[month],
#         'month_data': month_data,
#         'shift_types': ShiftType.objects.all(),
#         'prev_year': prev_month.year,
#         'prev_month': prev_month.month,
#         'next_year': next_month.year,
#         'next_month': next_month.month,
#     }
#
#     return render(request, 'rostering_app/month_view.html', context)
def month_view(request, company_size):
    """Full month calendar view."""
    load_company_fixtures(company_size)

    # Get date parameters
    year = int(request.GET.get('year', datetime.date.today().year))
    month = int(request.GET.get('month', datetime.date.today().month))

    # Build calendar data
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
                entries = ScheduleEntry.objects.filter(date=date, archived=False)

                shifts_data = {}
                for shift_type in ShiftType.objects.all():
                    shift_entries = entries.filter(shift_type=shift_type)
                    shifts_data[shift_type.name] = {
                        'count': shift_entries.count(),
                        'min_staff': shift_type.min_staff,
                        'max_staff': shift_type.max_staff,
                        'status': get_shift_status(
                            shift_entries.count(),
                            shift_type.min_staff,
                            shift_type.max_staff
                        )
                    }

                week_data.append({
                    'day': day,
                    'date': date,
                    'shifts': shifts_data,
                    'is_today': date == datetime.date.today()
                })
        month_data.append(week_data)

    # Zusatzberechnungen
    shift_types = ShiftType.objects.all()
    days_per_week = 7
    total_workdays = week_count * days_per_week - 2
    total_weekends = week_count * 2
    shifts_per_day = shift_types.count()
    total_shifts = week_count * days_per_week * shifts_per_day

    # Navigation
    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])
    prev_month = first_day - datetime.timedelta(days=1)
    next_month = last_day + datetime.timedelta(days=1)

    context = {
        'company_size': company_size,
        'company_name': get_company_name(company_size),
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'month_data': month_data,
        'shift_types': shift_types,
        'prev_year': prev_month.year,
        'prev_month': prev_month.month,
        'next_year': next_month.year,
        'next_month': next_month.month,
        # Neue Werte für die Übersicht
        'total_workdays': total_workdays,
        'total_weekends': total_weekends,
        'shifts_per_day': shifts_per_day,
        'total_shifts': total_shifts,
    }

    return render(request, 'rostering_app/month_view.html', context)


def day_view(request, company_size, date):
    """Detailed view for a specific day."""
    load_company_fixtures(company_size)
    
    try:
        date_obj = datetime.datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        raise Http404("Invalid date format")
    
    # Get all shifts for this day
    shifts_data = []
    for shift_type in ShiftType.objects.all():
        entries = ScheduleEntry.objects.filter(
            date=date_obj,
            shift_type=shift_type,
            archived=False
        ).select_related('employee')
        
        shifts_data.append({
            'shift': shift_type,
            'employees': [entry.employee for entry in entries],
            'count': entries.count(),
            'status': get_shift_status(entries.count(), 
                                     shift_type.min_staff, 
                                     shift_type.max_staff)
        })
    
    # Get available employees for each shift
    all_employees = Employee.objects.all()
    available_by_shift = {}
    
    for shift_type in ShiftType.objects.all():
        assigned = ScheduleEntry.objects.filter(
            date=date_obj,
            archived=False
        ).values_list('employee_id', flat=True)
        
        available = []
        for emp in all_employees:
            if emp.id not in assigned and date not in emp.absences:
                available.append(emp)
        
        available_by_shift[shift_type.id] = available
    
    context = {
        'company_size': company_size,
        'company_name': get_company_name(company_size),
        'date': date_obj,
        'shifts_data': shifts_data,
        'available_by_shift': available_by_shift,
        'prev_date': (date_obj - datetime.timedelta(days=1)).strftime('%Y-%m-%d'),
        'next_date': (date_obj + datetime.timedelta(days=1)).strftime('%Y-%m-%d'),
    }
    
    return render(request, 'rostering_app/day_view.html', context)


def employee_view(request, company_size, employee_id):
    """View for individual employee schedule."""
    load_company_fixtures(company_size)
    
    employee = get_object_or_404(Employee, pk=employee_id)
    
    # Get current month or from query
    today = datetime.date.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    
    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])
    
    # Get employee's schedule
    entries = ScheduleEntry.objects.filter(
        employee=employee,
        date__gte=first_day,
        date__lte=last_day,
        archived=False
    ).order_by('date')
    
    # Calculate statistics
    total_hours = sum(entry.shift_type.get_duration() for entry in entries)
    shifts_by_type = {}
    for shift_type in ShiftType.objects.all():
        count = entries.filter(shift_type=shift_type).count()
        shifts_by_type[shift_type.name] = count
    
    # Build calendar
    cal_data = build_employee_calendar(year, month, entries, employee.absences)
    
    context = {
        'company_size': company_size,
        'company_name': get_company_name(company_size),
        'employee': employee,
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'total_hours': total_hours,
        'shifts_by_type': shifts_by_type,
        'calendar_data': cal_data,
        'max_hours_per_week': employee.max_hours_per_week,
    }
    
    return render(request, 'rostering_app/employee_view.html', context)


def analytics_view(request, company_size):
    """Analytics and statistics view."""
    load_company_fixtures(company_size)
    
    # Get date range
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=30)
    
    # Get all entries in range
    entries = ScheduleEntry.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        archived=False
    )
    
    # Calculate various statistics
    stats = {
        'total_shifts': entries.count(),
        'coverage_by_shift': {},
        'employee_distribution': {},
        'weekly_patterns': {},
    }
    
    # Coverage by shift type
    for shift_type in ShiftType.objects.all():
        shift_entries = entries.filter(shift_type=shift_type)
        dates = shift_entries.values('date').distinct().count()
        if dates > 0:
            avg_coverage = shift_entries.count() / dates
            stats['coverage_by_shift'][shift_type.name] = {
                'average': round(avg_coverage, 1),
                'min': shift_type.min_staff,
                'max': shift_type.max_staff,
                'percentage': round((avg_coverage / shift_type.max_staff) * 100, 1)
            }
    
    # Employee distribution
    employee_stats = []
    for employee in Employee.objects.all():
        emp_entries = entries.filter(employee=employee)
        hours = sum(e.shift_type.get_duration() for e in emp_entries)
        employee_stats.append({
            'name': employee.name,
            'shifts': emp_entries.count(),
            'hours': hours,
            'utilization': round((hours / (employee.max_hours_per_week * 4)) * 100, 1)
        })
    
    stats['employee_distribution'] = sorted(employee_stats, 
                                          key=lambda x: x['hours'], 
                                          reverse=True)[:10]
    
    context = {
        'company_size': company_size,
        'company_name': get_company_name(company_size),
        'stats': stats,
        'start_date': start_date,
        'end_date': end_date,
    }
    
    return render(request, 'rostering_app/analytics.html', context)


def api_schedule_data(request, company_size, year, month):
    """API endpoint for AJAX schedule data."""
    load_company_fixtures(company_size)
    
    year = int(year)
    month = int(month)
    
    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])
    
    entries = ScheduleEntry.objects.filter(
        date__gte=first_day,
        date__lte=last_day,
        archived=False
    ).select_related('employee', 'shift_type')
    
    # Format data for JSON
    schedule_data = {}
    for entry in entries:
        date_str = entry.date.strftime('%Y-%m-%d')
        if date_str not in schedule_data:
            schedule_data[date_str] = {}
        
        shift_name = entry.shift_type.name
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
def get_company_name(company_size):
    """Get display name for company size."""
    names = {
        'small': 'Kleines Unternehmen',
        'medium': 'Mittleres Unternehmen',
        'large': 'Großes Unternehmen'
    }
    return names.get(company_size, 'Unternehmen')


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


def calculate_coverage_stats(entries, start_date, end_date):
    """Calculate coverage statistics for date range."""
    stats = []
    for shift_type in ShiftType.objects.all():
        shift_entries = entries.filter(shift_type=shift_type)
        total_days = (end_date - start_date).days + 1
        
        if total_days > 0:
            coverage_days = shift_entries.values('date').distinct().count()
            avg_staff = shift_entries.count() / total_days if total_days > 0 else 0
            
            stats.append({
                'shift': shift_type,
                'coverage_percentage': round((coverage_days / total_days) * 100, 1),
                'avg_staff': round(avg_staff, 1),
                'status': get_shift_status(avg_staff, shift_type.min_staff, shift_type.max_staff)
            })
    
    return stats


def calculate_employee_hours(entries):
    """Calculate total hours per employee."""
    hours = {}
    for entry in entries:
        emp_name = entry.employee.name
        duration = entry.shift_type.get_duration()
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
