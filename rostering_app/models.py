from django.db import models
from django.db.models import JSONField  # Use JSONField (available in Django 3.1+)

class Company(models.Model):
    name = models.CharField(max_length=100, unique=True)
    size = models.CharField(max_length=20, choices=[('small', 'Small'), ('medium', 'Medium'), ('large', 'Large')])
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=10, blank=True)
    color = models.CharField(max_length=20, blank=True)

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
        ('EarlyShift', 'Early Shift'),
        ('LateShift', 'Late Shift'),
        ('NightShift', 'Night Shift'),
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
