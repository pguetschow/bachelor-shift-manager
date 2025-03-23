from django.contrib import admin
from .models import Employee, ShiftType, ScheduleEntry

admin.site.register(Employee)
admin.site.register(ShiftType)
admin.site.register(ScheduleEntry)
