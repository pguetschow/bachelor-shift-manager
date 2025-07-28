from django.db import models
from django.db.models import JSONField  # Use JSONField (available in Django 3.1+)


class Company(models.Model):
    name = models.CharField(max_length=100, unique=True)
    size = models.CharField(max_length=20, choices=[('small', 'Small'), ('medium', 'Medium'), ('large', 'Large')])
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=10, blank=True)
    color = models.CharField(max_length=20, blank=True)
    sunday_is_workday = models.BooleanField(default=False, help_text="Indicates if Sunday is considered a workday for this company")

    def __str__(self):
        return self.name

class Employee(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='employees')
    name = models.CharField(max_length=100)
    max_hours_per_week = models.IntegerField()
    # List of ISO date strings (e.g., ["2025-02-05", "2025-02-12"])
    absences = JSONField(default=list, blank=True)
    # List of preferred shift names (e.g., ["EarlyShift"])
    preferred_shifts = JSONField(default=list, blank=True)

    def __str__(self):
        return self.name

class Shift(models.Model):
    SHIFT_CHOICES = [
        ('EarlyShift', 'Frühschicht'),
        ('MorningShift', 'Morgenschicht'),
        ('LateShift', 'Spätschicht'),
        ('NightShift', 'Nachtschicht'),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='shifts')
    name = models.CharField(max_length=20, choices=SHIFT_CHOICES)
    start = models.TimeField()
    end = models.TimeField()
    min_staff = models.IntegerField()
    max_staff = models.IntegerField()

    def get_duration(self):
        from datetime import datetime, date, timedelta
        dt1 = datetime.combine(date.today(), self.start)
        dt2 = datetime.combine(date.today(), self.end)
        if dt2 < dt1:
            dt2 += timedelta(days=1)
        return (dt2 - dt1).seconds / 3600

    def __str__(self):
        return self.name

    class Meta:
        unique_together = ('company', 'name')

class ScheduleEntry(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, db_index=True)
    date = models.DateField(db_index=True)
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, db_index=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='schedule_entries', null=True, blank=True, db_index=True)
    algorithm = models.CharField(max_length=64, blank=True, default='', db_index=True)

    def __str__(self):
        return f"{self.date} - {self.employee.name} - {self.shift.name} - {self.company.name if self.company else 'No Company'}"

    class Meta:
        index_together = [
            ('company', 'date'),
            ('company', 'employee'),
            ('company', 'shift'),
            ('company', 'algorithm'),
            ('employee', 'date'),
        ]


class EmployeeKPI(models.Model):
    """
    Pre-calculated monthly KPI data for individual employees.
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='kpis')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='employee_kpis')
    year = models.IntegerField()
    month = models.IntegerField()
    algorithm = models.CharField(max_length=64, blank=True, default='')
    
    # Monthly statistics
    monthly_hours_worked = models.FloatField(default=0.0)
    monthly_shifts = models.IntegerField(default=0)
    expected_monthly_hours = models.FloatField(default=0.0)
    overtime_hours = models.FloatField(default=0.0)
    undertime_hours = models.FloatField(default=0.0)
    utilization_percentage = models.FloatField(default=0.0)
    absence_days = models.IntegerField(default=0)
    days_worked = models.IntegerField(default=0)
    possible_days = models.IntegerField(default=0)
    
    # Calculated timestamp
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('employee', 'company', 'year', 'month', 'algorithm')
        indexes = [
            models.Index(fields=['company', 'year', 'month']),
            models.Index(fields=['employee', 'year', 'month']),
            models.Index(fields=['algorithm']),
        ]
    
    def __str__(self):
        return f"{self.employee.name} - {self.year}-{self.month:02d} - {self.algorithm or 'All'}"


class CompanyKPI(models.Model):
    """
    Pre-calculated monthly KPI data for companies.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='company_kpis')
    year = models.IntegerField()
    month = models.IntegerField()
    algorithm = models.CharField(max_length=64, blank=True, default='')
    
    # Company-wide statistics
    total_hours_worked = models.FloatField(default=0.0)
    avg_hours_per_employee = models.FloatField(default=0.0)
    hours_std_dev = models.FloatField(default=0.0)
    hours_cv = models.FloatField(default=0.0)  # Coefficient of variation
    gini_coefficient = models.FloatField(default=0.0)
    min_hours = models.FloatField(default=0.0)
    max_hours = models.FloatField(default=0.0)
    total_weekly_violations = models.IntegerField(default=0)
    rest_period_violations = models.IntegerField(default=0)
    
    # Employee hours breakdown (stored as JSON for flexibility)
    employee_hours = JSONField(default=dict, blank=True)
    weekly_violations = JSONField(default=dict, blank=True)
    
    # Calculated timestamp
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('company', 'year', 'month', 'algorithm')
        indexes = [
            models.Index(fields=['company', 'year', 'month']),
            models.Index(fields=['algorithm']),
        ]
    
    def __str__(self):
        return f"{self.company.name} - {self.year}-{self.month:02d} - {self.algorithm or 'All'}"


class CoverageKPI(models.Model):
    """
    Pre-calculated shift coverage statistics for date ranges.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='coverage_kpis')
    start_date = models.DateField()
    end_date = models.DateField()
    algorithm = models.CharField(max_length=64, blank=True, default='')
    
    # Coverage statistics
    total_working_days = models.IntegerField(default=0)
    total_required_staff = models.IntegerField(default=0)
    total_assigned_staff = models.IntegerField(default=0)
    coverage_rate = models.FloatField(default=0.0)
    understaffed_days = models.IntegerField(default=0)
    overstaffed_days = models.IntegerField(default=0)
    
    # Shift-specific coverage (stored as JSON)
    shift_coverage = JSONField(default=list, blank=True)
    
    # Calculated timestamp
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('company', 'start_date', 'end_date', 'algorithm')
        indexes = [
            models.Index(fields=['company', 'start_date', 'end_date']),
            models.Index(fields=['algorithm']),
        ]
    
    def __str__(self):
        return f"{self.company.name} - {self.start_date} to {self.end_date} - {self.algorithm or 'All'}"
