"""Export full database (schema + data) as SQL dump for easy import/export."""
import os
import sys
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.management import call_command
import io


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

        dump_file = os.path.join(output_dir, 'benchmark_dump.json')
        zip_file = os.path.join(output_dir, 'benchmark_dump.zip')

        try:
            self.stdout.write(f"Exporting full database to {dump_file}...")
            with open(dump_file, 'w', encoding='utf-8') as f:
                out = io.StringIO()
                call_command(
                    'dumpdata',
                    'rostering_app.Company',
                    'rostering_app.Shift',
                    'rostering_app.Employee',
                    'rostering_app.ScheduleEntry',
                    format='json',
                    use_natural_foreign=True,
                    use_natural_primary=True,
                    stdout=out
                )
                f.write(out.getvalue())

            self._create_zip_file(dump_file, zip_file)

            self.stdout.write(f"Data exported successfully!")
            self.stdout.write(f"JSON file: {dump_file}")
            self.stdout.write(f"ZIP file: {zip_file}")
            json_size = os.path.getsize(dump_file) / (1024 * 1024)
            zip_size = os.path.getsize(zip_file) / (1024 * 1024)
            self.stdout.write(f"JSON file size: {json_size:.2f} MB")
            self.stdout.write(f"ZIP file size: {zip_size:.2f} MB")
        except Exception as e:
            self.stdout.write(f"Export failed: {str(e)}")
            raise

    def _create_zip_file(self, sql_file, zip_file):
        """Create ZIP file containing the SQL dump."""
        import zipfile
        
        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(sql_file, 'benchmark_dump.json') 