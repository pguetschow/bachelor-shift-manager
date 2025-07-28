#!/usr/bin/env python3
"""
Simple test script to verify the KPI Calculator is working correctly.
"""

import os
import sys
import django
from datetime import date, time, timedelta, datetime
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rostering_project.settings')
django.setup()

# Import Django models and KPICalculator only after setup
from rostering_app.models import Company, Employee, Shift, ScheduleEntry
from rostering_app.services.kpi_calculator import KPICalculator


def test_kpi_calculator():
    """Test the KPI Calculator with sample data."""
    print("Testing KPI Calculator...")
    
    # Create a test company
    company, created = Company.objects.get_or_create(
        name="Test Company",
        defaults={
            'sunday_is_workday': False,
        }
    )
    
    # Create test employees
    employee1, created = Employee.objects.get_or_create(
        name="Test Employee 1",
        company=company,
        defaults={
            'max_hours_per_week': 40,
        }
    )
    
    employee2, created = Employee.objects.get_or_create(
        name="Test Employee 2", 
        company=company,
        defaults={
            'max_hours_per_week': 32,
        }
    )
    
    # Create test shifts
    shift1, created = Shift.objects.get_or_create(
        name="MorningShift",
        company=company,
        defaults={
            'start': time(8, 0),
            'end': time(16, 0),
            'min_staff': 1,
            'max_staff': 3,
        }
    )
    
    shift2, created = Shift.objects.get_or_create(
        name="NightShift",
        company=company,
        defaults={
            'start': time(22, 0),
            'end': time(6, 0),
            'min_staff': 1,
            'max_staff': 2,
        }
    )
    # Calculate duration for test logic
    def calc_duration(start, end):
        dt1 = datetime.combine(date.today(), start)
        dt2 = datetime.combine(date.today(), end)
        if dt2 < dt1:
            dt2 += timedelta(days=1)
        return (dt2 - dt1).total_seconds() / 3600
    shift1_duration = calc_duration(shift1.start, shift1.end)
    shift2_duration = calc_duration(shift2.start, shift2.end)
    
    # Create test schedule entries
    test_date = date(2025, 1, 15)  # A Wednesday
    
    # Create entries for employee 1
    entry1, created = ScheduleEntry.objects.get_or_create(
        employee=employee1,
        shift=shift1,
        date=test_date,
        company=company,
        algorithm="test",
        defaults={}
    )
    
    entry2, created = ScheduleEntry.objects.get_or_create(
        employee=employee1,
        shift=shift1,
        date=test_date + timedelta(days=1),
        company=company,
        algorithm="test",
        defaults={}
    )
    
    # Create entries for employee 2
    entry3, created = ScheduleEntry.objects.get_or_create(
        employee=employee2,
        shift=shift2,
        date=test_date,
        company=company,
        algorithm="test",
        defaults={}
    )
    
    # Initialize KPI Calculator
    kpi_calculator = KPICalculator(company)
    
    # Test basic functions
    print(f"\n1. Testing date blocking...")
    is_blocked = kpi_calculator.is_date_blocked(employee1, test_date)
    print(f"   Date {test_date} blocked for employee1: {is_blocked}")
    
    print(f"\n2. Testing expected month hours...")
    expected_hours = kpi_calculator.calculate_expected_month_hours(employee1, 2025, 1)
    print(f"   Expected hours for employee1 in January 2025: {expected_hours}")
    
    print(f"\n3. Testing rest period violation...")
    violates = kpi_calculator.violates_rest_period(shift1, shift2, test_date)
    print(f"   Violates rest period between shift1 and shift2: {violates}")
    
    print(f"\n4. Testing shift hours calculation...")
    hours = kpi_calculator.calculate_shift_hours_in_range(shift1, test_date, test_date, test_date + timedelta(days=1))
    print(f"   Hours for shift1 on {test_date}: {hours}")
    
    print(f"\n5. Testing employee hours calculation...")
    entries = [entry1, entry2, entry3]
    employee_hours = kpi_calculator.calculate_employee_hours(entries, test_date, test_date + timedelta(days=1))
    print(f"   Employee hours: {employee_hours}")
    
    print(f"\n6. Testing employee statistics...")
    stats = kpi_calculator.calculate_employee_statistics(employee1, entries, 2025, 1, "test")
    print(f"   Employee1 stats: {stats}")
    
    print(f"\n7. Testing company analytics...")
    analytics = kpi_calculator.calculate_company_analytics(entries, 2025, 1, "test")
    print(f"   Company analytics: {analytics}")
    
    print(f"\n8. Testing coverage stats...")
    coverage = kpi_calculator.calculate_coverage_stats(entries, test_date, test_date + timedelta(days=1))
    print(f"   Coverage stats: {coverage}")
    
    print(f"\nKPI Calculator test completed successfully!")
    
    # Cleanup
    entry1.delete()
    entry2.delete()
    entry3.delete()
    shift1.delete()
    shift2.delete()
    employee1.delete()
    employee2.delete()
    company.delete()


if __name__ == "__main__":
    test_kpi_calculator() 