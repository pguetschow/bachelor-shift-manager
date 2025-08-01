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
    expected_hours = kpi_calculator.calculate_expected_month_hours(employee1, 2025, 1, company)
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
    
    print(f"\n9. Testing expected yearly hours calculation...")
    test_expected_yearly_hours(kpi_calculator, employee1, employee2)
    
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


def test_expected_yearly_hours(kpi_calculator, employee1, employee2):
    """Comprehensive test for calculate_expected_yearly_hours method."""
    print("   Testing calculate_expected_yearly_hours method...")
    
    # Test 1: Basic calculation for 2025
    print("   Test 1: Basic yearly calculation for 2025")
    yearly_hours_2025 = kpi_calculator.calculate_expected_yearly_hours(employee1, 2025)
    print(f"      Employee1 (40h/week) expected yearly hours 2025: {yearly_hours_2025}")
    
    # Test 2: Different employee with different hours
    yearly_hours_2025_emp2 = kpi_calculator.calculate_expected_yearly_hours(employee2, 2025)
    print(f"      Employee2 (32h/week) expected yearly hours 2025: {yearly_hours_2025_emp2}")
    
    # Test 3: Test for different years
    print("   Test 3: Testing different years")
    yearly_hours_2024 = kpi_calculator.calculate_expected_yearly_hours(employee1, 2024)
    yearly_hours_2026 = kpi_calculator.calculate_expected_yearly_hours(employee1, 2026)
    print(f"      Employee1 expected yearly hours 2024: {yearly_hours_2024}")
    print(f"      Employee1 expected yearly hours 2026: {yearly_hours_2026}")
    
    # Test 4: Test with absences
    print("   Test 4: Testing with employee absences")
    # Add some absences to employee1
    original_absences = getattr(employee1, 'absences', [])
    employee1.absences = ["2025-01-15", "2025-02-20", "2025-03-10", "2025-12-25"]
    employee1.save()
    
    yearly_hours_with_absences = kpi_calculator.calculate_expected_yearly_hours(employee1, 2025)
    print(f"      Employee1 with 4 absences expected yearly hours: {yearly_hours_with_absences}")
    
    # Restore original absences
    employee1.absences = original_absences
    employee1.save()
    
    # Test 5: Test with Sunday workday company
    print("   Test 5: Testing with Sunday workday company")
    original_sunday_setting = kpi_calculator.company.sunday_is_workday
    kpi_calculator.company.sunday_is_workday = True
    kpi_calculator.company.save()
    kpi_calculator.sundays_off = False  # Update the calculator
    
    yearly_hours_sunday_work = kpi_calculator.calculate_expected_yearly_hours(employee1, 2025)
    print(f"      Employee1 with Sunday workdays expected yearly hours: {yearly_hours_sunday_work}")
    
    # Restore original setting
    kpi_calculator.company.sunday_is_workday = original_sunday_setting
    kpi_calculator.company.save()
    kpi_calculator.sundays_off = not original_sunday_setting
    
    # Test 6: Test edge cases
    print("   Test 6: Testing edge cases")
    
    # Test with zero hours per week
    original_hours = employee1.max_hours_per_week
    employee1.max_hours_per_week = 0
    employee1.save()
    
    yearly_hours_zero = kpi_calculator.calculate_expected_yearly_hours(employee1, 2025)
    print(f"      Employee1 with 0h/week expected yearly hours: {yearly_hours_zero}")
    
    # Restore original hours
    employee1.max_hours_per_week = original_hours
    employee1.save()
    
    # Test 7: Manual calculation verification
    print("   Test 7: Manual calculation verification")
    # For 2025, let's calculate manually what we expect
    # 2025 has 365 days
    # German holidays in 2025: Jan 1, Jan 6, Apr 18, Apr 21, May 1, May 29, Jun 9, Oct 3, Dec 25, Dec 26 = 10 holidays
    # Sundays: 52 weeks * 1 Sunday = 52 Sundays (if sundays_off = True)
    # Working days = 365 - 10 - 52 = 303 days (if sundays_off = True)
    # Working days = 365 - 10 = 355 days (if sundays_off = False)
    
    if kpi_calculator.sundays_off:
        expected_working_days = 365 - 10 - 52  # 303 days
    else:
        expected_working_days = 365 - 10  # 355 days
    
    expected_daily_hours = 40 / (6 if kpi_calculator.sundays_off else 7)
    expected_raw_hours = expected_daily_hours * expected_working_days
    expected_rounded_hours = round(expected_raw_hours / 8) * 8
    
    print(f"      Manual calculation:")
    print(f"        Working days: {expected_working_days}")
    print(f"        Daily hours: {expected_daily_hours:.2f}")
    print(f"        Raw hours: {expected_raw_hours:.2f}")
    print(f"        Rounded hours: {expected_rounded_hours}")
    print(f"        Actual result: {yearly_hours_2025}")
    print(f"        Match: {abs(yearly_hours_2025 - expected_rounded_hours) < 0.01}")
    
    # Test 8: Test that results are reasonable
    print("   Test 8: Reasonableness checks")
    assert yearly_hours_2025 > 0, "Yearly hours should be positive"
    assert yearly_hours_2025 <= 40 * 52, "Yearly hours should not exceed max possible (40h * 52 weeks)"
    assert yearly_hours_2025_emp2 < yearly_hours_2025, "Employee with fewer weekly hours should have fewer yearly hours"
    assert yearly_hours_sunday_work > yearly_hours_2025, "Sunday workdays should increase yearly hours"
    assert yearly_hours_zero == 0, "Zero weekly hours should result in zero yearly hours"
    
    print("      All reasonableness checks passed!")
    
    print("   calculate_expected_yearly_hours test completed successfully!")


if __name__ == "__main__":
    test_kpi_calculator() 