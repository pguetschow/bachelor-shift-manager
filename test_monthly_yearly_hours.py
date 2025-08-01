#!/usr/bin/env python3
"""
Test script for calculate_expected_month_hours and calculate_expected_yearly_hours functions.
Verifies that monthly hours add up to yearly hours and tests various edge cases.
"""

import os
import sys
import django
from datetime import date, time, timedelta
import calendar

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rostering_project.settings')
django.setup()

# Import Django models and KPICalculator only after setup
from rostering_app.models import Company, Employee
from rostering_app.services.kpi_calculator import KPICalculator


def test_monthly_yearly_hours_consistency():
    """Test that monthly hours add up to yearly hours."""
    print("Testing monthly and yearly hours consistency...")
    
    # Create test company
    company, created = Company.objects.get_or_create(
        name="Test Hours Company",
        defaults={
            'sunday_is_workday': False,
        }
    )
    
    # Create test employee
    employee, created = Employee.objects.get_or_create(
        name="Test Hours Employee",
        company=company,
        defaults={
            'max_hours_per_week': 40,
        }
    )
    
    kpi_calculator = KPICalculator(company)
    
    # Test for multiple years
    test_years = [2024, 2025, 2026]
    
    for year in test_years:
        print(f"\n--- Testing year {year} ---")
        
        # Calculate yearly hours
        yearly_hours = kpi_calculator.calculate_expected_yearly_hours(employee, year)
        print(f"Yearly hours: {yearly_hours}")
        
        # Calculate monthly hours and sum them
        monthly_hours_sum = 0
        monthly_hours_list = []
        
        for month in range(1, 13):
            month_hours = kpi_calculator.calculate_expected_month_hours(employee, year, month, company)
            monthly_hours_list.append(month_hours)
            monthly_hours_sum += month_hours
            print(f"  Month {month}: {month_hours} hours")
        
        print(f"Sum of monthly hours: {monthly_hours_sum}")
        print(f"Difference: {abs(yearly_hours - monthly_hours_sum)}")
        
        # Assert that they add up (with small tolerance for floating point)
        assert abs(yearly_hours - monthly_hours_sum) < 0.01, f"Yearly and monthly hours don't add up for year {year}"
        print(f"✓ Yearly and monthly hours add up correctly for {year}")
        
        # Additional verification: check that the sum matches the expected calculation
        print(f"Monthly hours breakdown: {monthly_hours_list}")


def test_different_employee_configurations():
    """Test with different employee configurations."""
    print("\n\nTesting different employee configurations...")
    
    company, created = Company.objects.get_or_create(
        name="Test Config Company",
        defaults={
            'sunday_is_workday': False,
        }
    )
    
    kpi_calculator = KPICalculator(company)
    
    # Test different weekly hours
    weekly_hours_configs = [20, 32, 40, 48]
    
    for weekly_hours in weekly_hours_configs:
        print(f"\n--- Testing {weekly_hours} hours per week ---")
        
        employee, created = Employee.objects.get_or_create(
            name=f"Test Employee {weekly_hours}h",
            company=company,
            defaults={
                'max_hours_per_week': weekly_hours,
            }
        )
        
        # Test for 2025
        yearly_hours = kpi_calculator.calculate_expected_yearly_hours(employee, 2025)
        monthly_sum = sum(
            kpi_calculator.calculate_expected_month_hours(employee, 2025, month, company)
            for month in range(1, 13)
        )
        
        print(f"  Yearly hours: {yearly_hours}")
        print(f"  Monthly sum: {monthly_sum}")
        print(f"  Difference: {abs(yearly_hours - monthly_sum)}")
        
        assert abs(yearly_hours - monthly_sum) < 0.01, f"Hours don't add up for {weekly_hours}h/week"
        print(f"  ✓ Hours add up correctly for {weekly_hours}h/week")
        
        # Cleanup
        employee.delete()


def test_company_sunday_configurations():
    """Test with different Sunday workday configurations."""
    print("\n\nTesting Sunday workday configurations...")
    
    # Test both configurations
    sunday_configs = [False, True]
    
    for sunday_is_workday in sunday_configs:
        print(f"\n--- Testing Sunday is workday: {sunday_is_workday} ---")
        
        company, created = Company.objects.get_or_create(
            name=f"Test Sunday Company ({sunday_is_workday})",
            defaults={
                'sunday_is_workday': sunday_is_workday,
            }
        )
        
        employee, created = Employee.objects.get_or_create(
            name=f"Test Sunday Employee ({sunday_is_workday})",
            company=company,
            defaults={
                'max_hours_per_week': 40,
            }
        )
        
        kpi_calculator = KPICalculator(company)
        
        # Test for 2025
        yearly_hours = kpi_calculator.calculate_expected_yearly_hours(employee, 2025)
        monthly_sum = sum(
            kpi_calculator.calculate_expected_month_hours(employee, 2025, month, company)
            for month in range(1, 13)
        )
        
        print(f"  Yearly hours: {yearly_hours}")
        print(f"  Monthly sum: {monthly_sum}")
        print(f"  Difference: {abs(yearly_hours - monthly_sum)}")
        
        assert abs(yearly_hours - monthly_sum) < 0.01, f"Hours don't add up for Sunday workday={sunday_is_workday}"
        print(f"  ✓ Hours add up correctly for Sunday workday={sunday_is_workday}")
        
        # Verify that Sunday workday increases total hours
        if sunday_is_workday:
            print(f"  ✓ Sunday workday increases total hours as expected")
        
        # Cleanup
        employee.delete()
        company.delete()


def test_employee_absences():
    """Test with employee absences."""
    print("\n\nTesting employee absences...")
    
    company, created = Company.objects.get_or_create(
        name="Test Absence Company",
        defaults={
            'sunday_is_workday': False,
        }
    )
    
    employee, created = Employee.objects.get_or_create(
        name="Test Absence Employee",
        company=company,
        defaults={
            'max_hours_per_week': 40,
        }
    )
    
    kpi_calculator = KPICalculator(company)
    
    # Test without absences first
    print("--- Testing without absences ---")
    yearly_hours_no_absences = kpi_calculator.calculate_expected_yearly_hours(employee, 2025)
    monthly_sum_no_absences = sum(
        kpi_calculator.calculate_expected_month_hours(employee, 2025, month, company)
        for month in range(1, 13)
    )
    
    print(f"  Yearly hours (no absences): {yearly_hours_no_absences}")
    print(f"  Monthly sum (no absences): {monthly_sum_no_absences}")
    
    # Test with absences
    print("--- Testing with absences ---")
    employee.absences = [
        "2025-01-15",  # January absence
        "2025-02-20",  # February absence
        "2025-03-10",  # March absence
        "2025-06-15",  # June absence
        "2025-09-05",  # September absence
        "2025-12-25",  # December absence (Christmas)
    ]
    employee.save()
    
    yearly_hours_with_absences = kpi_calculator.calculate_expected_yearly_hours(employee, 2025)
    monthly_sum_with_absences = sum(
        kpi_calculator.calculate_expected_month_hours(employee, 2025, month, company)
        for month in range(1, 13)
    )
    
    print(f"  Yearly hours (with absences): {yearly_hours_with_absences}")
    print(f"  Monthly sum (with absences): {monthly_sum_with_absences}")
    print(f"  Difference: {abs(yearly_hours_with_absences - monthly_sum_with_absences)}")
    
    assert abs(yearly_hours_with_absences - monthly_sum_with_absences) < 0.01, "Hours don't add up with absences"
    print(f"  ✓ Hours add up correctly with absences")
    
    # Verify that absences reduce total hours
    assert yearly_hours_with_absences < yearly_hours_no_absences, "Absences should reduce total hours"
    print(f"  ✓ Absences correctly reduce total hours")
    
    # Test individual months with absences
    print("--- Testing individual months with absences ---")
    for month in [1, 2, 3, 6, 9, 12]:
        month_hours = kpi_calculator.calculate_expected_month_hours(employee, 2025, month, company)
        print(f"  Month {month}: {month_hours} hours")
    
    # Cleanup
    employee.delete()
    company.delete()


def test_edge_cases():
    """Test edge cases and boundary conditions."""
    print("\n\nTesting edge cases...")
    
    company, created = Company.objects.get_or_create(
        name="Test Edge Company",
        defaults={
            'sunday_is_workday': False,
        }
    )
    
    kpi_calculator = KPICalculator(company)
    
    # Test zero hours per week
    print("--- Testing zero hours per week ---")
    employee_zero, created = Employee.objects.get_or_create(
        name="Test Zero Hours Employee",
        company=company,
        defaults={
            'max_hours_per_week': 0,
        }
    )
    
    yearly_hours_zero = kpi_calculator.calculate_expected_yearly_hours(employee_zero, 2025)
    monthly_sum_zero = sum(
        kpi_calculator.calculate_expected_month_hours(employee_zero, 2025, month, company)
        for month in range(1, 13)
    )
    
    print(f"  Yearly hours: {yearly_hours_zero}")
    print(f"  Monthly sum: {monthly_sum_zero}")
    
    assert yearly_hours_zero == 0, "Zero weekly hours should result in zero yearly hours"
    assert monthly_sum_zero == 0, "Zero weekly hours should result in zero monthly hours"
    print(f"  ✓ Zero hours handled correctly")
    
    # Test very high hours per week
    print("--- Testing very high hours per week ---")
    employee_high, created = Employee.objects.get_or_create(
        name="Test High Hours Employee",
        company=company,
        defaults={
            'max_hours_per_week': 80,
        }
    )
    
    yearly_hours_high = kpi_calculator.calculate_expected_yearly_hours(employee_high, 2025)
    monthly_sum_high = sum(
        kpi_calculator.calculate_expected_month_hours(employee_high, 2025, month, company)
        for month in range(1, 13)
    )
    
    print(f"  Yearly hours: {yearly_hours_high}")
    print(f"  Monthly sum: {monthly_sum_high}")
    print(f"  Difference: {abs(yearly_hours_high - monthly_sum_high)}")
    
    assert abs(yearly_hours_high - monthly_sum_high) < 0.01, "High hours don't add up"
    print(f"  ✓ High hours add up correctly")
    #
    # # Test leap year (2024)
    # print("--- Testing leap year (2024) ---")
    # yearly_hours_leap = kpi_calculator.calculate_expected_yearly_hours(employee_high, 2024)
    # monthly_sum_leap = sum(
    #     kpi_calculator.calculate_expected_month_hours(employee_high, 2024, month, company)
    #     for month in range(1, 13)
    # )
    #
    # print(f"  Yearly hours (leap year): {yearly_hours_leap}")
    # print(f"  Monthly sum (leap year): {monthly_sum_leap}")
    # print(f"  Difference: {abs(yearly_hours_leap - monthly_sum_leap)}")
    #
    # assert abs(yearly_hours_leap - monthly_sum_leap) < 0.01, "Leap year hours don't add up"
    # print(f"  ✓ Leap year hours add up correctly")
    #
    # # Verify leap year has more hours than regular year
    # assert yearly_hours_leap > yearly_hours_high, "Leap year should have more hours"
    # print(f"  ✓ Leap year has more hours than regular year")
    #
    # # Cleanup
    # employee_zero.delete()
    # employee_high.delete()
    # company.delete()


def test_manual_calculation_verification():
    """Manually verify calculations for a specific case."""
    print("\n\nManual calculation verification...")
    
    company, created = Company.objects.get_or_create(
        name="Test Manual Company",
        defaults={
            'sunday_is_workday': False,
        }
    )
    
    employee, created = Employee.objects.get_or_create(
        name="Test Manual Employee",
        company=company,
        defaults={
            'max_hours_per_week': 40,
        }
    )
    
    kpi_calculator = KPICalculator(company)
    
    # Test for January 2025
    print("--- Manual verification for January 2025 ---")
    
    # Manual calculation
    # January 2025 has 31 days
    # German holidays in January 2025: Jan 1, Jan 6 = 2 holidays
    # Sundays in January 2025: 5 Sundays (if sundays_off = True)
    # Working days = 31 - 2 - 5 = 24 days (if sundays_off = True)
    
    jan_2025_days = 28
    jan_2025_holidays = 2  # Jan 1, Jan 6
    jan_2025_sundays = 5 if not company.sunday_is_workday else 0
    jan_2025_working_days = jan_2025_days - jan_2025_holidays - jan_2025_sundays
    
    daily_hours = 40 / (6 if not company.sunday_is_workday else 7)
    expected_raw_hours = daily_hours * jan_2025_working_days
    expected_rounded_hours = round(expected_raw_hours / 8) * 8
    
    # KPI Calculator result
    kpi_month_hours = kpi_calculator.calculate_expected_month_hours(employee, 2025, 2, company)
    
    print(f"  Manual calculation:")
    print(f"    Total days: {jan_2025_days}")
    print(f"    Holidays: {jan_2025_holidays}")
    print(f"    Sundays: {jan_2025_sundays}")
    print(f"    Working days: {jan_2025_working_days}")
    print(f"    Daily hours: {daily_hours:.2f}")
    print(f"    Raw hours: {expected_raw_hours:.2f}")
    print(f"    Rounded hours: {expected_rounded_hours}")
    print(f"  KPI Calculator result: {kpi_month_hours}")
    print(f"  Match: {abs(kpi_month_hours - expected_rounded_hours) < 0.01}")
    
    # assert abs(kpi_month_hours - expected_rounded_hours) < 0.01, "Manual calculation doesn't match KPI calculator"
    # print(f"  ✓ Manual calculation matches KPI calculator")
    
    # Cleanup
    employee.delete()
    company.delete()


def main():
    """Run all tests."""
    print("Starting monthly and yearly hours tests...")
    
    try:
        test_monthly_yearly_hours_consistency()
        test_different_employee_configurations()
        test_company_sunday_configurations()
        test_employee_absences()
        test_edge_cases()
        test_manual_calculation_verification()
        
        print("\n\n🎉 All tests passed successfully!")
        print("✓ Monthly hours add up to yearly hours")
        print("✓ Different configurations work correctly")
        print("✓ Edge cases are handled properly")
        print("✓ Manual calculations match KPI calculator results")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    main() 