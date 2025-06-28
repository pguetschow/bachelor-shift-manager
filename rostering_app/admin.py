from django.contrib import admin
from .models import Employee, Shift, ScheduleEntry, Company

admin.site.register(Company)
admin.site.register(Employee)
admin.site.register(Shift)
admin.site.register(ScheduleEntry)
