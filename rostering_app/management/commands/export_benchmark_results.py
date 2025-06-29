"""Export benchmark results for upload to deployed environment."""
import json
import os
import zipfile
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from rostering_app.models import (
    Company, Employee, Shift, ScheduleEntry, 
    BenchmarkStatus, CompanyBenchmarkStatus
)


class Command(BaseCommand):
    help = "Export benchmark results for upload to deployed environment"

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default='benchmark_export',
            help='Output directory for export files (default: benchmark_export)',
        )
        parser.add_argument(
            '--include-schedules',
            action='store_true',
            help='Include schedule entries in export (can be large)',
        )
        parser.add_argument(
            '--company',
            type=str,
            help='Export only specific company (by name)',
        )

    def handle(self, *args, **options):
        output_dir = options['output_dir']
        include_schedules = options['include_schedules']
        company_filter = options.get('company')
        
        # Create output directory
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Get current benchmark status
        benchmark_status = BenchmarkStatus.get_current()
        
        # Export metadata
        metadata = {
            'exported_at': datetime.now().isoformat(),
            'benchmark_status': {
                'status': benchmark_status.status,
                'started_at': benchmark_status.started_at.isoformat() if benchmark_status.started_at else None,
                'completed_at': benchmark_status.completed_at.isoformat() if benchmark_status.completed_at else None,
                'load_fixtures': benchmark_status.load_fixtures,
                'error_message': benchmark_status.error_message,
            },
            'export_options': {
                'include_schedules': include_schedules,
                'company_filter': company_filter,
            }
        }
        
        # Export companies
        companies_query = Company.objects.all()
        if company_filter:
            companies_query = companies_query.filter(name__icontains=company_filter)
        
        companies_data = []
        for company in companies_query:
            company_data = {
                'id': company.id,
                'name': company.name,
                'size': company.size,
                'description': company.description,
                'icon': company.icon,
                'color': company.color,
                'sunday_is_workday': company.sunday_is_workday,
            }
            companies_data.append(company_data)
        
        # Export employees
        employees_query = Employee.objects.all()
        if company_filter:
            employees_query = employees_query.filter(company__name__icontains=company_filter)
        
        employees_data = []
        for employee in employees_query:
            employee_data = {
                'id': employee.id,
                'company_id': employee.company.id,
                'name': employee.name,
                'max_hours_per_week': employee.max_hours_per_week,
                'absences': employee.absences,
                'preferred_shifts': employee.preferred_shifts,
            }
            employees_data.append(employee_data)
        
        # Export shifts
        shifts_query = Shift.objects.all()
        if company_filter:
            shifts_query = shifts_query.filter(company__name__icontains=company_filter)
        
        shifts_data = []
        for shift in shifts_query:
            shift_data = {
                'id': shift.id,
                'company_id': shift.company.id,
                'name': shift.name,
                'start': shift.start.isoformat(),
                'end': shift.end.isoformat(),
                'min_staff': shift.min_staff,
                'max_staff': shift.max_staff,
            }
            shifts_data.append(shift_data)
        
        # Export schedule entries if requested
        schedule_data = []
        if include_schedules:
            schedule_query = ScheduleEntry.objects.all()
            if company_filter:
                schedule_query = schedule_query.filter(company__name__icontains=company_filter)
            
            for entry in schedule_query:
                entry_data = {
                    'id': entry.id,
                    'employee_id': entry.employee.id,
                    'date': entry.date.isoformat(),
                    'shift_id': entry.shift.id,
                    'company_id': entry.company.id if entry.company else None,
                    'algorithm': entry.algorithm,
                }
                schedule_data.append(entry_data)
        
        # Export company benchmark statuses
        company_status_query = CompanyBenchmarkStatus.objects.all()
        if company_filter:
            company_status_query = company_status_query.filter(company_name__icontains=company_filter)
        
        company_status_data = []
        for status in company_status_query:
            status_data = {
                'company_name': status.company_name,
                'test_case': status.test_case,
                'completed': status.completed,
                'completed_at': status.completed_at.isoformat() if status.completed_at else None,
                'error_message': status.error_message,
                'created_at': status.created_at.isoformat(),
                'updated_at': status.updated_at.isoformat(),
            }
            company_status_data.append(status_data)
        
        # Create export data structure
        export_data = {
            'metadata': metadata,
            'companies': companies_data,
            'employees': employees_data,
            'shifts': shifts_data,
            'schedule_entries': schedule_data,
            'company_benchmark_statuses': company_status_data,
        }
        
        # Save as JSON
        export_file = os.path.join(output_dir, 'benchmark_export.json')
        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        # Create ZIP file for easy upload
        zip_file = os.path.join(output_dir, 'benchmark_export.zip')
        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(export_file, 'benchmark_export.json')
        
        # Print summary
        self.stdout.write(self.style.SUCCESS(
            f"Export completed successfully!"
        ))
        self.stdout.write(f"Companies exported: {len(companies_data)}")
        self.stdout.write(f"Employees exported: {len(employees_data)}")
        self.stdout.write(f"Shifts exported: {len(shifts_data)}")
        if include_schedules:
            self.stdout.write(f"Schedule entries exported: {len(schedule_data)}")
        else:
            self.stdout.write("Schedule entries: excluded (use --include-schedules to include)")
        
        self.stdout.write(f"\nExport files:")
        self.stdout.write(f"  JSON: {export_file}")
        self.stdout.write(f"  ZIP: {zip_file}")
        
        # Show upload instructions
        self.stdout.write(f"\nTo upload to deployed environment:")
        self.stdout.write(f"1. Upload the ZIP file to your deployed environment")
        self.stdout.write(f"2. Use the upload API endpoint: POST /api/upload-benchmark-results/")
        self.stdout.write(f"3. Or use the web interface at /upload-benchmark/") 