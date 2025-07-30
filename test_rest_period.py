#!/usr/bin/env python3
"""
Test script to verify rest period violation calculations.
"""

import os
import sys
import django
from datetime import datetime, date, time, timedelta

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rostering_project.settings')
django.setup()

from rostering_app.services.kpi_calculator import KPICalculator
from rostering_app.models import Company, Shift, Employee, ScheduleEntry

def test_rest_period_calculation():
    """Test the rest period calculation logic."""
    
    # Create a test company
    company = Company.objects.create(
        name="Test Company",
        size="small",
        sunday_is_workday=False
    )
    
    # Create test shifts
    early_shift = Shift.objects.create(
        company=company,
        name="EarlyShift",
        start=time(6, 0),  # 6:00 AM
        end=time(14, 0),   # 2:00 PM
        min_staff=1,
        max_staff=5
    )
    
    late_shift = Shift.objects.create(
        company=company,
        name="LateShift", 
        start=time(14, 0),  # 2:00 PM
        end=time(22, 0),    # 10:00 PM
        min_staff=1,
        max_staff=5
    )
    
    night_shift = Shift.objects.create(
        company=company,
        name="NightShift",
        start=time(22, 0),  # 10:00 PM
        end=time(6, 0),     # 6:00 AM (next day)
        min_staff=1,
        max_staff=5
    )
    
    # Create test employee
    employee = Employee.objects.create(
        company=company,
        name="Test Employee",
        max_hours_per_week=40
    )
    
    # Initialize KPI calculator
    kpi_calculator = KPICalculator(company)
    
    print("=== Rest Period Violation Test ===\n")
    
    # Test 1: Early shift followed by late shift (should be OK - 8 hours rest)
    print("Test 1: Early shift (6:00-14:00) followed by Late shift (14:00-22:00) next day")
    print(f"Expected: No violation (8 hours rest)")
    result1 = kpi_calculator.violates_rest_period(early_shift, late_shift, date(2025, 1, 1))
    print(f"Result: {'VIOLATION' if result1 else 'OK'}")
    
    # Calculate actual rest period
    end_first = datetime.combine(date(2025, 1, 1), early_shift.end)
    start_second = datetime.combine(date(2025, 1, 2), late_shift.start)
    rest_hours = (start_second - end_first).total_seconds() / 3600
    print(f"Rest period: {rest_hours:.1f} hours\n")
    
    # Test 2: Late shift followed by early shift (should be violation - 8 hours rest)
    print("Test 2: Late shift (14:00-22:00) followed by Early shift (6:00-14:00) next day")
    print(f"Expected: VIOLATION (8 hours rest < 11 required)")
    result2 = kpi_calculator.violates_rest_period(late_shift, early_shift, date(2025, 1, 1))
    print(f"Result: {'VIOLATION' if result2 else 'OK'}")
    
    # Calculate actual rest period
    end_first = datetime.combine(date(2025, 1, 1), late_shift.end)
    start_second = datetime.combine(date(2025, 1, 2), early_shift.start)
    rest_hours = (start_second - end_first).total_seconds() / 3600
    print(f"Rest period: {rest_hours:.1f} hours\n")
    
    # Test 3: Night shift followed by early shift (should be violation)
    print("Test 3: Night shift (22:00-6:00) followed by Early shift (6:00-14:00) next day")
    print(f"Expected: VIOLATION (0 hours rest < 11 required)")
    result3 = kpi_calculator.violates_rest_period(night_shift, early_shift, date(2025, 1, 1))
    print(f"Result: {'VIOLATION' if result3 else 'OK'}")
    
    # Calculate actual rest period
    end_first = datetime.combine(date(2025, 1, 1), night_shift.end)
    if night_shift.end < night_shift.start:
        end_first += timedelta(days=1)  # Night shift wraps to next day
    start_second = datetime.combine(date(2025, 1, 2), early_shift.start)
    rest_hours = (start_second - end_first).total_seconds() / 3600
    print(f"Rest period: {rest_hours:.1f} hours\n")
    
    # Test 4: Early shift followed by night shift (should be OK)
    print("Test 4: Early shift (6:00-14:00) followed by Night shift (22:00-6:00) next day")
    print(f"Expected: OK (8 hours rest)")
    result4 = kpi_calculator.violates_rest_period(early_shift, night_shift, date(2025, 1, 1))
    print(f"Result: {'VIOLATION' if result4 else 'OK'}")
    
    # Calculate actual rest period
    end_first = datetime.combine(date(2025, 1, 1), early_shift.end)
    start_second = datetime.combine(date(2025, 1, 2), night_shift.start)
    rest_hours = (start_second - end_first).total_seconds() / 3600
    print(f"Rest period: {rest_hours:.1f} hours\n")
    
    # Test 5: Night shift followed by night shift (should be OK - 16 hours rest)
    print("Test 5: Night shift (22:00-6:00) followed by Night shift (22:00-6:00) next day")
    print(f"Expected: OK (16 hours rest)")
    result5 = kpi_calculator.violates_rest_period(night_shift, night_shift, date(2025, 1, 1))
    print(f"Result: {'VIOLATION' if result5 else 'OK'}")
    
    # Calculate actual rest period
    end_first = datetime.combine(date(2025, 1, 1), night_shift.end)
    if night_shift.end < night_shift.start:
        end_first += timedelta(days=1)  # Night shift wraps to next day
    start_second = datetime.combine(date(2025, 1, 2), night_shift.start)
    rest_hours = (start_second - end_first).total_seconds() / 3600
    print(f"Rest period: {rest_hours:.1f} hours\n")
    
    # Test with actual schedule entries
    print("=== Testing with Schedule Entries ===\n")
    
    # Create schedule entries for a violation scenario
    entry1 = ScheduleEntry.objects.create(
        employee=employee,
        date=date(2025, 1, 1),
        shift=late_shift,
        company=company,
        algorithm="test"
    )
    
    entry2 = ScheduleEntry.objects.create(
        employee=employee,
        date=date(2025, 1, 2),
        shift=early_shift,
        company=company,
        algorithm="test"
    )
    
    entries = [entry1, entry2]
    violations = kpi_calculator.check_rest_period_violations(entries, date(2025, 1, 1), date(2025, 1, 2))
    print(f"Schedule entries violation count: {violations}")
    print(f"Expected: 1 violation (late shift followed by early shift)")
    
    # Clean up
    ScheduleEntry.objects.all().delete()
    Employee.objects.all().delete()
    Shift.objects.all().delete()
    Company.objects.all().delete()

if __name__ == "__main__":
    test_rest_period_calculation() 