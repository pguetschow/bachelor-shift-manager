"""""Import benchmark data from SQL dump files."""
import os
import zipfile
import tempfile
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import connection, transaction
from django.core.management import call_command
from django.apps import apps
from rostering_app.models import Company, Shift, Employee, ScheduleEntry


class Command(BaseCommand):
    help = "Import benchmark data from SQL dump files"

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help='Path to SQL dump file or ZIP archive containing SQL dumps.'
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing data before import.'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Parse and validate statements without executing them.'
        )
        parser.add_argument(
            '--use-orm',
            action='store_true',
            help='Use Django ORM instead of raw SQL (more reliable).'
        )

    def handle(self, *args, **options):
        file_path = str(options['file'])
        clear_existing = options['clear_existing']
        dry_run = options['dry_run']

        if not os.path.exists(file_path):
            self.stdout.write(f"File not found: {file_path}")
            return

        # Extract JSON file if it's a ZIP
        json_file = self._extract_json_file(file_path)
        if not json_file:
            self.stdout.write("No JSON file found in archive or path provided.")
            return

        # Optionally clear existing data
        if clear_existing:
            self._clear_existing_data()

        # Import data using loaddata
        try:
            if dry_run:
                self.stdout.write(f"Dry run: Data would be loaded from {json_file}")
            else:
                call_command('loaddata', json_file, verbosity=1)
                self.stdout.write("Import completed successfully!")
        except Exception as e:
            self.stdout.write(f"Import failed: {str(e)}")
            raise
        finally:
            # Clean up temp JSON if extracted
            if json_file != file_path and os.path.exists(json_file):
                os.remove(json_file)

    def _extract_json_file(self, file_path):
        """Extract JSON file from ZIP or return the file path if it's already a JSON file."""
        file_path_str = str(file_path)
        if file_path_str.endswith('.zip'):
            with zipfile.ZipFile(file_path, 'r') as zipf:
                json_files = [f for f in zipf.namelist() if f.endswith('.json')]
                if not json_files:
                    return None
                # Extract the first JSON file
                json_filename = json_files[0]
                temp_dir = tempfile.mkdtemp()
                zipf.extract(json_filename, temp_dir)
                return os.path.join(temp_dir, json_filename)
        if file_path_str.endswith('.json'):
            return file_path
        return None

    def _clear_existing_data(self):
        """Delete all data from Company, Shift, Employee, and ScheduleEntry using Django ORM."""
        self.stdout.write("Deleting all data from Company, Shift, Employee, and ScheduleEntry...")
        ScheduleEntry.objects.all().delete()
        Employee.objects.all().delete()
        Shift.objects.all().delete()
        Company.objects.all().delete()
        self.stdout.write("All relevant data deleted. Ready for import.")
