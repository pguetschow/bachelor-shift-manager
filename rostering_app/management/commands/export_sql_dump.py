"""Export full database (schema + data) as SQL dump for easy import/export."""
import os
import sys
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.management import call_command
import io
import subprocess
import zipfile


class Command(BaseCommand):
    help = "Export only companies, shifts, employees, and shift results as SQL dump for import/upload."

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default='benchmark_export',
            help='Output directory for export files (default: benchmark_export)',
        )

    def handle(self, *args, **options):
        output_dir = options['output_dir']
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        dump_file = os.path.join(output_dir, 'benchmark_dump.sql')
        zip_file = os.path.join(output_dir, 'benchmark_dump.zip')

        db_name = settings.DATABASES['default']['NAME']
        db_user = settings.DATABASES['default']['USER']
        db_password = settings.DATABASES['default']['PASSWORD']
        db_host = settings.DATABASES['default']['HOST']
        db_port = str(settings.DATABASES['default'].get('PORT', 3306))
        tables = [
            'rostering_app_company',
            'rostering_app_shift',
            'rostering_app_employee',
            'rostering_app_scheduleentry',
        ]

        mysqldump_cmd = [
            'mysqldump',
            f'-h{db_host}',
            f'-P{db_port}',
            f'-u{db_user}',
            f'-p{db_password}',
            '--skip-lock-tables',
            '--single-transaction',
            '--add-drop-table',
            db_name,
        ] + tables

        self.stdout.write(f"Exporting tables to {dump_file}...")
        try:
            with open(dump_file, 'w', encoding='utf-8') as f:
                subprocess.run(mysqldump_cmd, check=True, stdout=f)
            self.stdout.write(f"SQL dump exported successfully!")
        except Exception as e:
            self.stdout.write(f"Export failed: {str(e)}")
            raise

        # Zip the SQL file
        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(dump_file, 'benchmark_dump.sql')
        self.stdout.write(f"ZIP file created: {zip_file}") 