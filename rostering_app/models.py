from django.db import models
from django.db.models import JSONField  # Use JSONField (available in Django 3.1+)
from django.utils import timezone

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
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='schedule_entries', null=True, blank=True)
    algorithm = models.CharField(max_length=64, blank=True, default='')

    def __str__(self):
        return f"{self.date} - {self.employee.name} - {self.shift.name} - {self.company.name if self.company else 'No Company'}"

class BenchmarkStatus(models.Model):
    """Track the status of benchmark runs."""
    STATUS_CHOICES = [
        ('idle', 'Idle'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='idle')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    load_fixtures = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Benchmark Status"
    
    def __str__(self):
        return f"Benchmark {self.status} at {self.updated_at}"
    
    @classmethod
    def get_current(cls):
        """Get the current benchmark status, creating one if none exists."""
        status, created = cls.objects.get_or_create(
            id=1,  # Always use ID 1 for singleton
            defaults={'status': 'idle'}
        )
        return status
    
    def start_benchmark(self, load_fixtures=False):
        """Start a new benchmark run."""
        self.status = 'running'
        self.started_at = timezone.now()
        self.completed_at = None
        self.load_fixtures = load_fixtures
        self.error_message = ''
        self.save()
    
    def complete_benchmark(self, success=True, error_message=''):
        """Mark benchmark as completed."""
        self.status = 'completed' if success else 'failed'
        self.completed_at = timezone.now()
        self.error_message = error_message
        self.save()
    
    def reset(self):
        """Reset to idle state."""
        self.status = 'idle'
        self.started_at = None
        self.completed_at = None
        self.error_message = ''
        self.save()

class CompanyBenchmarkStatus(models.Model):
    """Track the benchmark completion status for individual companies."""
    company_name = models.CharField(max_length=100, unique=True)
    test_case = models.CharField(max_length=50)  # small_company, medium_company, large_company
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Company Benchmark Status"
    
    def __str__(self):
        return f"{self.company_name} - {'Completed' if self.completed else 'Pending'}"
    
    @classmethod
    def get_or_create_for_company(cls, company_name, test_case):
        """Get or create status for a specific company."""
        status, created = cls.objects.get_or_create(
            company_name=company_name,
            defaults={'test_case': test_case, 'completed': False}
        )
        return status
    
    def mark_completed(self, success=True, error_message=''):
        """Mark company benchmark as completed."""
        self.completed = success
        self.completed_at = timezone.now() if success else None
        self.error_message = error_message
        self.save()
    
    def reset(self):
        """Reset to pending state."""
        self.completed = False
        self.completed_at = None
        self.error_message = ''
        self.save()
