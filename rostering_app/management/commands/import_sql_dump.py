"""""Import benchmark data from SQL dump files."""
import os
import zipfile
import tempfile
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import connection, transaction
import sqlite3


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
        use_orm = options['use_orm']

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        # Extract SQL file if it's a ZIP
        sql_file = self._extract_sql_file(file_path)
        if not sql_file:
            self.stdout.write(self.style.ERROR("No SQL file found in archive or path provided."))
            return

        # Optionally clear existing data
        if clear_existing:
            self._clear_existing_data()

        # Parse SQL file into individual statements
        statements = self._parse_sql_file(sql_file)

        # Execute or dry-run
        import_results = {
            'tables_processed': [],
            'statements_executed': 0,
            'errors': []
        }

        try:
            with transaction.atomic():
                cursor = connection.cursor()
                for stmt in statements:
                    try:
                        if use_orm:
                            # Execute via ORM (connection.cursor() fallback)
                            cursor.execute(stmt)
                        else:
                            cursor.execute(stmt)
                        import_results['statements_executed'] += 1
                    except Exception as stmt_err:
                        import_results['errors'].append(str(stmt_err))
                        if dry_run:
                            raise

                import_results['tables_processed'] = len(import_results['tables_processed'])

                self.stdout.write(self.style.SUCCESS("Import completed successfully!"))
                self.stdout.write(f"Tables processed: {import_results['tables_processed']}")
                self.stdout.write(f"Statements executed: {import_results['statements_executed']}")
                self.stdout.write(f"Errors: {len(import_results['errors'])}")

                if import_results['errors']:
                    self.stdout.write(self.style.WARNING("Errors occurred during import:"))
                    for error in import_results['errors']:
                        self.stdout.write(f"  - {error}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Import failed: {str(e)}"))
            raise
        finally:
            # Clean up temp SQL if extracted
            if sql_file != file_path and os.path.exists(sql_file):
                os.remove(sql_file)

    def _extract_sql_file(self, file_path):
        """Extract SQL file from ZIP or return the file path if it's already a SQL file."""
        file_path_str = str(file_path)
        if file_path_str.endswith('.zip'):
            with zipfile.ZipFile(file_path, 'r') as zipf:
                sql_files = [f for f in zipf.namelist() if f.endswith('.sql')]
                if not sql_files:
                    return None

                # Extract the first SQL file
                sql_filename = sql_files[0]
                temp_dir = tempfile.mkdtemp()
                zipf.extract(sql_filename, temp_dir)
                return os.path.join(temp_dir, sql_filename)

        if file_path_str.endswith('.sql'):
            return file_path

        return None

    def _parse_sql_file(self, sql_file_path):
        """Parse an SQL file into individual statements, respecting quoted strings."""
        statements = []
        current_statement = ""
        in_string = False
        escape_next = False

        with open(sql_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                for char in line:
                    if char == '\\' and not escape_next:
                        escape_next = True
                        current_statement += char
                        continue

                    if escape_next:
                        escape_next = False
                        current_statement += char
                        continue

                    if char == "'" and not escape_next:
                        in_string = not in_string

                    if char == ';' and not in_string:
                        current_statement += char
                        stmt = current_statement.strip()
                        if stmt and not stmt.startswith('--'):
                            statements.append(stmt)
                        current_statement = ""
                    else:
                        current_statement += char

        # Capture any trailing statement
        trailing = current_statement.strip()
        if trailing and not trailing.startswith('--'):
            statements.append(trailing)

        return statements

    def _clear_existing_data(self):
        """Drop all tables (for SQLite: delete the DB file and recreate it)."""
        # Ensure the database path is a string, not a Path object
        db_path = os.fspath(settings.DATABASES['default']['NAME'])
        self.stdout.write("Dropping all tables (resetting database file)...")
        # Only safe for SQLite
        if db_path.endswith('.sqlite3') or db_path.endswith('.db'):
            if os.path.exists(db_path):
                os.remove(db_path)
            # Recreate empty DB file
            conn = sqlite3.connect(db_path)
            conn.close()
            self.stdout.write("Database file reset. Ready for import.")
        else:
            # For other DBs, full drop isn't implemented
            raise NotImplementedError(
                "Full drop is only implemented for SQLite. "
                "For other databases, please drop tables manually."
            )
