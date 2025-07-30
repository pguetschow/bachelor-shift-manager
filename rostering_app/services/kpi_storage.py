"""
KPI Storage Service

This service manages the storage and retrieval of pre-calculated KPIs
to avoid repeated calculations and improve performance.
"""

from datetime import date, timedelta
from typing import Dict, List, Optional, Any
from django.db import transaction
from django.utils import timezone

from rostering_app.models import EmployeeKPI, CompanyKPI, CoverageKPI, ScheduleEntry, Employee, Company
from rostering_app.services.kpi_calculator import KPICalculator


class KPIStorageService:
    """
    Service for managing pre-calculated KPI storage and retrieval.
    """
    
    def __init__(self, company: Company):
        self.company = company
        self.kpi_calculator = KPICalculator(company)
    
    def get_or_calculate_employee_kpi(self, employee: Employee, year: int, month: int, 
                                    algorithm: Optional[str] = None, force_recalculate: bool = False) -> EmployeeKPI:
        """
        Get cached employee KPI or calculate and store it.
        
        Args:
            employee: Employee object
            year: Year for KPI calculation
            month: Month for KPI calculation
            algorithm: Algorithm filter (optional)
            force_recalculate: Force recalculation even if cached
            
        Returns:
            EmployeeKPI object
        """
        if not force_recalculate:
            # Try to get cached KPI
            try:
                kpi = EmployeeKPI.objects.get(
                    employee=employee,
                    company=self.company,
                    year=year,
                    month=month,
                    algorithm=algorithm or ''
                )
                return kpi
            except EmployeeKPI.DoesNotExist:
                pass
        
        # Calculate KPI
        entries = ScheduleEntry.objects.filter(
            employee=employee,
            company=self.company,
            date__year=year,
            date__month=month
        )
        if algorithm:
            entries = entries.filter(algorithm=algorithm)
        
        stats = self.kpi_calculator.calculate_employee_statistics(
            employee, list(entries), year, month, algorithm
        )
        
        # Store KPI
        kpi, created = EmployeeKPI.objects.update_or_create(
            employee=employee,
            company=self.company,
            year=year,
            month=month,
            algorithm=algorithm or '',
            defaults={
                'monthly_hours_worked': stats['monthly_hours_worked'],
                'monthly_shifts': stats['monthly_shifts'],
                'expected_monthly_hours': stats['expected_monthly_hours'],
                'overtime_hours': stats['overtime_hours'],
                'undertime_hours': stats['undertime_hours'],
                'utilization_percentage': stats['utilization_percentage'],
                'absence_days': stats['absence_days'],
                'planned_absences': stats['planned_absences'],
                'days_worked': stats['days_worked'],
                'possible_days': stats['possible_days'],
            }
        )
        
        return kpi
    
    def get_or_calculate_company_kpi(self, year: int, month: int, 
                                   algorithm: Optional[str] = None, force_recalculate: bool = False) -> CompanyKPI:
        """
        Get cached company KPI or calculate and store it.
        
        Args:
            year: Year for KPI calculation
            month: Month for KPI calculation
            algorithm: Algorithm filter (optional)
            force_recalculate: Force recalculation even if cached
            
        Returns:
            CompanyKPI object
        """
        if not force_recalculate:
            # Try to get cached KPI
            try:
                kpi = CompanyKPI.objects.get(
                    company=self.company,
                    year=year,
                    month=month,
                    algorithm=algorithm or ''
                )
                return kpi
            except CompanyKPI.DoesNotExist:
                pass
        
        # Calculate KPI
        entries = ScheduleEntry.objects.filter(
            company=self.company,
            date__year=year,
            date__month=month
        )
        if algorithm:
            entries = entries.filter(algorithm=algorithm)
        
        analytics = self.kpi_calculator.calculate_company_analytics(
            list(entries), year, month, algorithm
        )
        
        # Calculate detailed violations
        start_date = date(year, month, 1)
        end_date = date(year, month, 28)
        while end_date.month == month:
            end_date += timedelta(days=1)
        end_date -= timedelta(days=1)
        
        weekly_violations_detailed = self.kpi_calculator.check_weekly_hours_violations_detailed(
            list(entries), start_date, end_date
        )
        rest_period_violations_detailed = self.kpi_calculator.check_rest_period_violations_detailed(
            list(entries), start_date, end_date
        )
        
        # Store KPI
        kpi, created = CompanyKPI.objects.update_or_create(
            company=self.company,
            year=year,
            month=month,
            algorithm=algorithm or '',
            defaults={
                'total_hours_worked': analytics['total_hours_worked'],
                'avg_hours_per_employee': analytics['avg_hours_per_employee'],
                'hours_std_dev': analytics['hours_std_dev'],
                'hours_cv': analytics['hours_cv'],
                'gini_coefficient': analytics['gini_coefficient'],
                'min_hours': analytics['min_hours'],
                'max_hours': analytics['max_hours'],
                'total_weekly_violations': analytics['total_weekly_violations'],
                'rest_period_violations': analytics['rest_period_violations'],
                'employee_hours': analytics['employee_hours'],
                'weekly_violations': analytics['weekly_violations'],
                'weekly_violations_detailed': weekly_violations_detailed,
                'rest_period_violations_detailed': rest_period_violations_detailed,
            }
        )
        
        return kpi
    
    def get_or_calculate_coverage_kpi(self, start_date: date, end_date: date,
                                    algorithm: Optional[str] = None, force_recalculate: bool = False) -> CoverageKPI:
        """
        Get cached coverage KPI or calculate and store it.
        
        Args:
            start_date: Start date for coverage calculation
            end_date: End date for coverage calculation
            algorithm: Algorithm filter (optional)
            force_recalculate: Force recalculation even if cached
            
        Returns:
            CoverageKPI object
        """
        if not force_recalculate:
            # Try to get cached KPI
            try:
                kpi = CoverageKPI.objects.get(
                    company=self.company,
                    start_date=start_date,
                    end_date=end_date,
                    algorithm=algorithm or ''
                )
                return kpi
            except CoverageKPI.DoesNotExist:
                pass
        
        # Calculate KPI
        entries = ScheduleEntry.objects.filter(
            company=self.company,
            date__gte=start_date,
            date__lte=end_date
        )
        if algorithm:
            entries = entries.filter(algorithm=algorithm)
        
        coverage_stats = self.kpi_calculator.calculate_coverage_stats(
            list(entries), start_date, end_date
        )
        
        # Calculate summary statistics
        total_working_days = len(coverage_stats)
        total_required_staff = sum(stat.get('required_staff', 0) for stat in coverage_stats)
        total_assigned_staff = sum(stat.get('assigned_staff', 0) for stat in coverage_stats)
        coverage_rate = (total_assigned_staff / total_required_staff * 100) if total_required_staff > 0 else 0
        understaffed_days = sum(1 for stat in coverage_stats if stat.get('assigned_staff', 0) < stat.get('required_staff', 0))
        overstaffed_days = sum(1 for stat in coverage_stats if stat.get('assigned_staff', 0) > stat.get('required_staff', 0))
        
        # Store KPI
        kpi, created = CoverageKPI.objects.update_or_create(
            company=self.company,
            start_date=start_date,
            end_date=end_date,
            algorithm=algorithm or '',
            defaults={
                'total_working_days': total_working_days,
                'total_required_staff': total_required_staff,
                'total_assigned_staff': total_assigned_staff,
                'coverage_rate': coverage_rate,
                'understaffed_days': understaffed_days,
                'overstaffed_days': overstaffed_days,
                'shift_coverage': coverage_stats,
            }
        )
        
        return kpi
    
    def calculate_all_employee_kpis(self, year: int, month: int, 
                                  algorithm: Optional[str] = None) -> List[EmployeeKPI]:
        """
        Calculate and store KPIs for all employees in a company for a given month.
        
        Args:
            year: Year for KPI calculation
            month: Month for KPI calculation
            algorithm: Algorithm filter (optional)
            
        Returns:
            List of EmployeeKPI objects
        """
        employees = Employee.objects.filter(company=self.company)
        kpis = []
        
        for employee in employees:
            kpi = self.get_or_calculate_employee_kpi(employee, year, month, algorithm, force_recalculate=True)
            kpis.append(kpi)
        
        return kpis
    
    def calculate_all_kpis(self, year: int, month: int, 
                          algorithm: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculate and store all KPIs for a company for a given month.
        
        Args:
            year: Year for KPI calculation
            month: Month for KPI calculation
            algorithm: Algorithm filter (optional)
            
        Returns:
            Dictionary containing all calculated KPIs
        """
        with transaction.atomic():
            # Calculate employee KPIs
            employee_kpis = self.calculate_all_employee_kpis(year, month, algorithm)
            
            # Calculate company KPI
            company_kpi = self.get_or_calculate_company_kpi(year, month, algorithm, force_recalculate=True)
            
            # Calculate coverage KPI for the month
            start_date = date(year, month, 1)
            end_date = date(year, month, 28)  # Use 28 to ensure we get the full month
            while end_date.month == month:
                end_date += timedelta(days=1)
            end_date -= timedelta(days=1)
            
            coverage_kpi = self.get_or_calculate_coverage_kpi(start_date, end_date, algorithm, force_recalculate=True)
            
            return {
                'employee_kpis': employee_kpis,
                'company_kpi': company_kpi,
                'coverage_kpi': coverage_kpi,
            }
    
    def invalidate_kpis(self, year: int, month: int, algorithm: Optional[str] = None):
        """
        Invalidate cached KPIs for a specific period.
        
        Args:
            year: Year for KPI invalidation
            month: Month for KPI invalidation
            algorithm: Algorithm filter (optional)
        """
        # Delete employee KPIs
        EmployeeKPI.objects.filter(
            company=self.company,
            year=year,
            month=month,
            algorithm=algorithm or ''
        ).delete()
        
        # Delete company KPI
        CompanyKPI.objects.filter(
            company=self.company,
            year=year,
            month=month,
            algorithm=algorithm or ''
        ).delete()
        
        # Delete coverage KPIs for the month
        start_date = date(year, month, 1)
        end_date = date(year, month, 28)
        while end_date.month == month:
            end_date += timedelta(days=1)
        end_date -= timedelta(days=1)
        
        CoverageKPI.objects.filter(
            company=self.company,
            start_date__gte=start_date,
            end_date__lte=end_date,
            algorithm=algorithm or ''
        ).delete()
    
    def get_employee_kpis_for_period(self, employee: Employee, start_date: date, 
                                   end_date: date, algorithm: Optional[str] = None) -> List[EmployeeKPI]:
        """
        Get cached employee KPIs for a date range.
        
        Args:
            employee: Employee object
            start_date: Start date
            end_date: End date
            algorithm: Algorithm filter (optional)
            
        Returns:
            List of EmployeeKPI objects
        """
        return EmployeeKPI.objects.filter(
            employee=employee,
            company=self.company,
            year__gte=start_date.year,
            year__lte=end_date.year,
            month__gte=start_date.month if start_date.year == end_date.year else 1,
            month__lte=end_date.month if start_date.year == end_date.year else 12,
            algorithm=algorithm or ''
        ).order_by('year', 'month')
    
    def get_company_kpis_for_period(self, start_date: date, end_date: date,
                                  algorithm: Optional[str] = None) -> List[CompanyKPI]:
        """
        Get cached company KPIs for a date range.
        
        Args:
            start_date: Start date
            end_date: End date
            algorithm: Algorithm filter (optional)
            
        Returns:
            List of CompanyKPI objects
        """
        return CompanyKPI.objects.filter(
            company=self.company,
            year__gte=start_date.year,
            year__lte=end_date.year,
            month__gte=start_date.month if start_date.year == end_date.year else 1,
            month__lte=end_date.month if start_date.year == end_date.year else 12,
            algorithm=algorithm or ''
        ).order_by('year', 'month') 