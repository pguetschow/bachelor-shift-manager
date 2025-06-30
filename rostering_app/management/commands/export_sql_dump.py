"""Export full database (schema + data) as SQL dump for easy import/export."""
import os
import sys
import sqlite3
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Export full database (schema + data) as SQL dump for easy import/export"

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

        db_path = settings.DATABASES['default']['NAME']
        if not os.path.exists(db_path):
            self.stdout.write(self.style.ERROR(f"Database file not found: {db_path}"))
            return

        dump_file = os.path.join(output_dir, 'benchmark_dump.sql')
        zip_file = os.path.join(output_dir, 'benchmark_dump.zip')

        # Use Python's sqlite3 module to dump full schema + data
        try:
            self.stdout.write(f"Exporting full database to {dump_file}...")
            with open(dump_file, 'w', encoding='utf-8') as f:
                conn = sqlite3.connect(db_path)
                for line in conn.iterdump():
                    f.write('%s\n' % line)
                conn.close()

            # Create ZIP file for easy upload
            self._create_zip_file(dump_file, zip_file)

            self.stdout.write(self.style.SUCCESS(f"SQL dump exported successfully!"))
            self.stdout.write(f"SQL file: {dump_file}")
            self.stdout.write(f"ZIP file: {zip_file}")
            sql_size = os.path.getsize(dump_file) / (1024 * 1024)
            zip_size = os.path.getsize(zip_file) / (1024 * 1024)
            self.stdout.write(f"SQL file size: {sql_size:.2f} MB")
            self.stdout.write(f"ZIP file size: {zip_size:.2f} MB")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Export failed: {str(e)}"))
            raise

    def _create_zip_file(self, sql_file, zip_file):
        """Create ZIP file containing the SQL dump."""
        import zipfile
        
        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(sql_file, 'benchmark_dump.sql') 