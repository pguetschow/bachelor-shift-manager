from django.contrib import admin
from .models import Employee, Shift, ScheduleEntry, Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'size', 'sunday_is_workday', 'description')
    list_filter = ('size', 'sunday_is_workday')
    search_fields = ('name', 'description')
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'size', 'description')
        }),
        ('Appearance', {
            'fields': ('icon', 'color')
        }),
        ('Work Schedule', {
            'fields': ('sunday_is_workday',),
            'description': 'Configure whether Sunday is considered a workday for this company.'
        }),
    )


admin.site.register(Employee)
admin.site.register(Shift)
admin.site.register(ScheduleEntry)
