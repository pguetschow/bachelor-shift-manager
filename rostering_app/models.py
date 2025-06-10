from django.db import models
from django.db.models import JSONField  # Use JSONField (available in Django 3.1+)

class Employee(models.Model):
    name = models.CharField(max_length=100)
    max_hours_per_week = models.IntegerField()
    # List of ISO date strings (e.g., ["2025-02-05", "2025-02-12"])
    absences = JSONField(default=list, blank=True)
    # List of preferred shift names (e.g., ["EarlyShift"])
    preferred_shifts = JSONField(default=list, blank=True)

    def __str__(self):
        return self.name

class ShiftType(models.Model):
    SHIFT_CHOICES = [
        ('EarlyShift', 'Early Shift'),
        ('LateShift', 'Late Shift'),
        ('NightShift', 'Night Shift'),
    ]
    name = models.CharField(max_length=20, choices=SHIFT_CHOICES, unique=True)
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

class ScheduleEntry(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    shift_type = models.ForeignKey(ShiftType, on_delete=models.CASCADE)
    archived = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.date} - {self.employee.name} - {self.shift_type.name}"
