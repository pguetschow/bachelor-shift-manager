"""Export benchmark data as SQL dump for easy import/export."""
import os
import sys
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import connection


class Command(BaseCommand):
    help = "Export benchmark data as SQL dump for easy import/export"

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
        parser.add_argument(
            '--data-only',
            action='store_true',
            help='Export only data, not schema (for importing into existing database)',
        )

    def handle(self, *args, **options):
        output_dir = options['output_dir']
        include_schedules = options['include_schedules']
        company_filter = options.get('company')
        data_only = options['data_only']
        
        # Create output directory
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Get database path
        db_path = settings.DATABASES['default']['NAME']
        if not os.path.exists(db_path):
            self.stdout.write(self.style.ERROR(f"Database file not found: {db_path}"))
            return
        
        # Determine tables to export
        tables = [
            'rostering_app_company',
            'rostering_app_shift', 
            'rostering_app_employee',
            'rostering_app_benchmarkstatus',
            'rostering_app_companybenchmarkstatus',
        ]
        
        if include_schedules:
            tables.append('rostering_app_scheduleentry')
        
        # Build SQLite dump command
        dump_file = os.path.join(output_dir, 'benchmark_dump.sql')
        
        # Create temporary database with filtered data if company filter is specified
        if company_filter:
            self.stdout.write(f"Filtering data for company: {company_filter}")
            temp_db_path = os.path.join(output_dir, 'temp_filtered.db')
            
            # Create filtered dump using SQLite commands
            self._create_filtered_dump(db_path, temp_db_path, company_filter, tables, data_only)
            source_db = temp_db_path
        else:
            source_db = db_path
        
        # Create the SQL dump
        try:
            if data_only:
                # Export only data (INSERT statements)
                self._export_data_only(source_db, dump_file, tables)
            else:
                # Export schema and data
                self._export_full_dump(source_db, dump_file, tables)
            
            # Create ZIP file for easy upload
            zip_file = os.path.join(output_dir, 'benchmark_dump.zip')
            self._create_zip_file(dump_file, zip_file)
            
            # Clean up temporary database if created
            if company_filter and os.path.exists(temp_db_path):
                os.remove(temp_db_path)
            
            # Print summary
            self.stdout.write(self.style.SUCCESS(f"SQL dump exported successfully!"))
            self.stdout.write(f"SQL file: {dump_file}")
            self.stdout.write(f"ZIP file: {zip_file}")
            
            # Show file sizes
            sql_size = os.path.getsize(dump_file) / (1024 * 1024)  # MB
            zip_size = os.path.getsize(zip_file) / (1024 * 1024)  # MB
            self.stdout.write(f"SQL file size: {sql_size:.2f} MB")
            self.stdout.write(f"ZIP file size: {zip_size:.2f} MB")
            
            self.stdout.write(f"\nTo import this dump:")
            self.stdout.write(f"1. Upload the ZIP file to your deployed environment")
            self.stdout.write(f"2. Use the import command: python manage.py import_sql_dump --file benchmark_dump.zip")
            self.stdout.write(f"3. Or use the web interface at /upload-benchmark/")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Export failed: {str(e)}"))
            # Clean up on error
            if company_filter and os.path.exists(temp_db_path):
                os.remove(temp_db_path)
            raise

    def _create_filtered_dump(self, source_db, temp_db, company_filter, tables, data_only):
        """Create a temporary database with filtered data."""
        import sqlite3
        
        # Connect to source database
        source_conn = sqlite3.connect(source_db)
        temp_conn = sqlite3.connect(temp_db)
        
        try:
            # Copy schema
            source_conn.backup(temp_conn)
            
            # Clear all data from temp database
            temp_conn.execute("DELETE FROM rostering_app_company")
            temp_conn.execute("DELETE FROM rostering_app_shift")
            temp_conn.execute("DELETE FROM rostering_app_employee")
            temp_conn.execute("DELETE FROM rostering_app_scheduleentry")
            
            # Find matching companies
            cursor = source_conn.execute(
                "SELECT id FROM rostering_app_company WHERE name LIKE ?", 
                (f'%{company_filter}%',)
            )
            company_ids = [row[0] for row in cursor.fetchall()]
            
            if not company_ids:
                self.stdout.write(self.style.WARNING(f"No companies found matching: {company_filter}"))
                return
            
            # Copy filtered data
            for company_id in company_ids:
                # Copy company
                cursor = source_conn.execute(
                    "SELECT * FROM rostering_app_company WHERE id = ?", (company_id,)
                )
                company_data = cursor.fetchone()
                if company_data:
                    temp_conn.execute(
                        "INSERT INTO rostering_app_company VALUES (?, ?, ?, ?, ?, ?, ?)", 
                        company_data
                    )
                
                # Copy shifts for this company
                cursor = source_conn.execute(
                    "SELECT * FROM rostering_app_shift WHERE company_id = ?", (company_id,)
                )
                for shift_data in cursor.fetchall():
                    temp_conn.execute(
                        "INSERT INTO rostering_app_shift VALUES (?, ?, ?, ?, ?, ?, ?)", 
                        shift_data
                    )
                
                # Copy employees for this company
                cursor = source_conn.execute(
                    "SELECT * FROM rostering_app_employee WHERE company_id = ?", (company_id,)
                )
                for employee_data in cursor.fetchall():
                    temp_conn.execute(
                        "INSERT INTO rostering_app_employee VALUES (?, ?, ?, ?, ?, ?)", 
                        employee_data
                    )
                
                # Copy schedule entries for this company
                cursor = source_conn.execute(
                    "SELECT * FROM rostering_app_scheduleentry WHERE company_id = ?", (company_id,)
                )
                for schedule_data in cursor.fetchall():
                    temp_conn.execute(
                        "INSERT INTO rostering_app_scheduleentry VALUES (?, ?, ?, ?, ?, ?)", 
                        schedule_data
                    )
            
            temp_conn.commit()
            
        finally:
            source_conn.close()
            temp_conn.close()

    def _export_data_only(self, db_path, dump_file, tables):
        """Export only data (INSERT statements) without schema."""
        with open(dump_file, 'w', encoding='utf-8') as f:
            f.write(f"-- Benchmark Data Export\n")
            f.write(f"-- Exported at: {datetime.now().isoformat()}\n")
            f.write(f"-- Data only export (no schema)\n\n")
            
            import sqlite3
            conn = sqlite3.connect(db_path)
            
            try:
                for table in tables:
                    if not self._table_exists(conn, table):
                        continue
                    
                    f.write(f"-- Data for table: {table}\n")
                    
                    cursor = conn.execute(f"SELECT * FROM {table}")
                    columns = [description[0] for description in cursor.description]
                    
                    for row in cursor.fetchall():
                        values = []
                        for value in row:
                            if value is None:
                                values.append('NULL')
                            elif isinstance(value, str):
                                # Escape single quotes
                                escaped_value = value.replace("'", "''")
                                values.append(f"'{escaped_value}'")
                            else:
                                values.append(str(value))
                        
                        f.write(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(values)});\n")
                    
                    f.write(f"\n")
                    
            finally:
                conn.close()

    def _export_full_dump(self, db_path, dump_file, tables):
        """Export full schema and data using Python's built-in SQLite."""
        import sqlite3
        
        with open(dump_file, 'w', encoding='utf-8') as f:
            f.write(f"-- Benchmark Full Export\n")
            f.write(f"-- Exported at: {datetime.now().isoformat()}\n")
            f.write(f"-- Full schema and data export\n\n")
            
            conn = sqlite3.connect(db_path)
            
            try:
                # Export schema
                f.write("-- Schema\n")
                cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
                for row in cursor.fetchall():
                    if row[0]:  # sql can be None for some system tables
                        f.write(f"{row[0]};\n")
                f.write("\n")
                
                # Export data for each table
                for table in tables:
                    if not self._table_exists(conn, table):
                        continue
                    
                    f.write(f"-- Data for table: {table}\n")
                    
                    cursor = conn.execute(f"SELECT * FROM {table}")
                    columns = [description[0] for description in cursor.description]
                    
                    for row in cursor.fetchall():
                        values = []
                        for value in row:
                            if value is None:
                                values.append('NULL')
                            elif isinstance(value, str):
                                # Escape single quotes
                                escaped_value = value.replace("'", "''")
                                values.append(f"'{escaped_value}'")
                            else:
                                values.append(str(value))
                        
                        f.write(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(values)});\n")
                    
                    f.write(f"\n")
                    
            finally:
                conn.close()

    def _create_zip_file(self, sql_file, zip_file):
        """Create ZIP file containing the SQL dump."""
        import zipfile
        
        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(sql_file, 'benchmark_dump.sql')

    def _table_exists(self, conn, table_name):
        """Check if a table exists in the database."""
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", 
            (table_name,)
        )
        return cursor.fetchone() is not None 