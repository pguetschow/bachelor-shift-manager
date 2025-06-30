"""""Import benchmark data from SQL dump files."""
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import connection


class Command(BaseCommand):
    help = "Import SQL dump for companies, shifts, employees, and shift results. Drops those tables before import."

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help='Path to SQL dump file (.sql) to import.'
        )

    def handle(self, *args, **options):
        file_path = str(options['file'])
        if not os.path.exists(file_path):
            self.stdout.write(f"File not found: {file_path}")
            return
        if not file_path.endswith('.sql'):
            self.stdout.write("Only .sql files are supported.")
            return

        tables = [
            'rostering_app_scheduleentry',
            'rostering_app_employee',
            'rostering_app_shift',
            'rostering_app_company',
        ]
        self.stdout.write("Dropping relevant tables before import...")
        with connection.cursor() as cursor:
            for table in tables:
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {table};")
                except Exception as e:
                    self.stdout.write(f"Error dropping table {table}: {e}")
        self.stdout.write("Tables dropped. Importing SQL dump...")
        with open(file_path, 'r', encoding='utf-8') as f:
            sql = f.read()
        with connection.cursor() as cursor:
            for statement in sql.split(';'):
                stmt = statement.strip()
                if stmt:
                    try:
                        cursor.execute(stmt)
                    except Exception as e:
                        self.stdout.write(f"Error executing statement: {e}\nStatement: {stmt[:100]}...")
        self.stdout.write("Import completed successfully!")
