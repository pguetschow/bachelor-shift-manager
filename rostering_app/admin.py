from django.contrib import admin
from .models import Employee, Shift, ScheduleEntry, Company, BenchmarkStatus


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


@admin.register(BenchmarkStatus)
class BenchmarkStatusAdmin(admin.ModelAdmin):
    list_display = ['status', 'started_at', 'completed_at', 'load_fixtures', 'updated_at']
    list_filter = ['status', 'load_fixtures']
    readonly_fields = ['created_at', 'updated_at']
    
    def has_add_permission(self, request):
        # Only allow one benchmark status record
        return not BenchmarkStatus.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        # Don't allow deletion of the benchmark status
        return False


admin.site.register(Employee)
admin.site.register(Shift)
admin.site.register(ScheduleEntry)
