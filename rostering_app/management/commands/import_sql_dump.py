"""Import benchmark data from SQL dump files."""
import os
import zipfile
import tempfile
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import connection, transaction


class Command(BaseCommand):
    help = "Import benchmark data from SQL dump files"

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help='Path to SQL dump file or ZIP file containing SQL dump',
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing data before import',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without actually importing',
        )

    def handle(self, *args, **options):
        file_path = options['file']
        clear_existing = options['clear_existing']
        dry_run = options['dry_run']
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f"File not found: {file_path}"))
            return
        
        # Extract SQL file if it's a ZIP
        sql_file = self._extract_sql_file(file_path)
        
        if not sql_file:
            self.stdout.write(self.style.ERROR("No SQL file found in the provided file"))
            return
        
        try:
            # Read and parse the SQL file
            sql_statements = self._parse_sql_file(sql_file)
            
            if dry_run:
                self._show_dry_run_summary(sql_statements)
                return
            
            # Import the data
            import_results = self._import_sql_statements(sql_statements, clear_existing)
            
            # Print results
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
            # Clean up temporary file if created
            if sql_file != file_path and os.path.exists(sql_file):
                os.remove(sql_file)

    def _extract_sql_file(self, file_path):
        """Extract SQL file from ZIP or return the file path if it's already a SQL file."""
        if file_path.endswith('.zip'):
            # Extract from ZIP
            with zipfile.ZipFile(file_path, 'r') as zipf:
                sql_files = [f for f in zipf.namelist() if f.endswith('.sql')]
                if not sql_files:
                    return None
                
                # Extract the first SQL file
                sql_filename = sql_files[0]
                temp_dir = tempfile.mkdtemp()
                zipf.extract(sql_filename, temp_dir)
                return os.path.join(temp_dir, sql_filename)
        elif file_path.endswith('.sql'):
            # Already a SQL file
            return file_path
        else:
            return None

    def _parse_sql_file(self, sql_file):
        """Parse SQL file and return list of statements."""
        with open(sql_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split into individual statements
        statements = []
        current_statement = ""
        in_string = False
        escape_next = False
        
        for char in content:
            if escape_next:
                current_statement += char
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                current_statement += char
                continue
            
            if char == "'" and not escape_next:
                in_string = not in_string
            
            if char == ';' and not in_string:
                current_statement += char
                statement = current_statement.strip()
                if statement and not statement.startswith('--'):
                    statements.append(statement)
                current_statement = ""
            else:
                current_statement += char
        
        # Add any remaining statement
        if current_statement.strip() and not current_statement.strip().startswith('--'):
            statements.append(current_statement.strip())
        
        return statements

    def _show_dry_run_summary(self, statements):
        """Show what would be imported without actually importing."""
        self.stdout.write("DRY RUN - No data will be imported")
        self.stdout.write(f"Found {len(statements)} SQL statements")
        
        # Count different types of statements
        insert_count = sum(1 for s in statements if s.upper().startswith('INSERT'))
        create_count = sum(1 for s in statements if s.upper().startswith('CREATE'))
        other_count = len(statements) - insert_count - create_count
        
        self.stdout.write(f"  INSERT statements: {insert_count}")
        self.stdout.write(f"  CREATE statements: {create_count}")
        self.stdout.write(f"  Other statements: {other_count}")
        
        # Show table names from INSERT statements
        tables = set()
        for statement in statements:
            if statement.upper().startswith('INSERT INTO'):
                # Extract table name from INSERT INTO table_name
                parts = statement.split()
                if len(parts) >= 3:
                    table_name = parts[2].strip('`"[]')
                    tables.add(table_name)
        
        if tables:
            self.stdout.write("Tables that would be populated:")
            for table in sorted(tables):
                self.stdout.write(f"  - {table}")

    def _import_sql_statements(self, statements, clear_existing):
        """Import SQL statements into the database."""
        import_results = {
            'tables_processed': set(),
            'statements_executed': 0,
            'errors': []
        }
        
        with transaction.atomic():
            # Clear existing data if requested
            if clear_existing:
                self._clear_existing_data()
            
            # Execute statements
            for statement in statements:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(statement)
                        
                        # Track which tables are being processed
                        if statement.upper().startswith('INSERT INTO'):
                            parts = statement.split()
                            if len(parts) >= 3:
                                table_name = parts[2].strip('`"[]')
                                import_results['tables_processed'].add(table_name)
                        
                        import_results['statements_executed'] += 1
                        
                except Exception as e:
                    error_msg = f"Statement failed: {str(e)[:100]}..."
                    import_results['errors'].append(error_msg)
                    self.stdout.write(self.style.WARNING(error_msg))
        
        import_results['tables_processed'] = len(import_results['tables_processed'])
        return import_results

    def _clear_existing_data(self):
        """Clear existing benchmark data from the database."""
        self.stdout.write("Clearing existing benchmark data...")
        
        with connection.cursor() as cursor:
            # Clear data in reverse dependency order
            cursor.execute("DELETE FROM rostering_app_scheduleentry")
            cursor.execute("DELETE FROM rostering_app_employee")
            cursor.execute("DELETE FROM rostering_app_shift")
            cursor.execute("DELETE FROM rostering_app_company")
            cursor.execute("DELETE FROM rostering_app_companybenchmarkstatus")
            cursor.execute("DELETE FROM rostering_app_benchmarkstatus")
        
        self.stdout.write("Existing data cleared") 