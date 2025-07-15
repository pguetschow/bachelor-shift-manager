"""Import SQL dump to production database using DSN string."""
import os
import sys
import zipfile
import tempfile
import subprocess
from urllib.parse import urlparse
from django.core.management.base import BaseCommand
import shutil


class Command(BaseCommand):
    help = "Import SQL dump to production database using DSN connection string."

    def add_arguments(self, parser):
        parser.add_argument(
            'dump_file',
            type=str,
            help='Path to SQL dump file (.sql or .zip containing .sql)',
        )
        parser.add_argument(
            '--dsn',
            type=str,
            help='Database DSN string (e.g., mysql://user:pass@host:port/db)',
        )

    def parse_dsn(self, dsn):
        """Parse DSN string into connection components."""
        try:
            parsed = urlparse(dsn)

            if parsed.scheme != 'mysql':
                raise ValueError("DSN must start with 'mysql://'")

            config = {
                'host': parsed.hostname,
                'port': str(parsed.port or 3306),
                'user': parsed.username,
                'password': parsed.password,
                'database': parsed.path.lstrip('/') if parsed.path else '',
            }

            return config

        except Exception as e:
            raise ValueError(f"Failed to parse DSN: {str(e)}")

    def build_mysql_command(self, config):
        """Build MySQL command without SSL options to avoid compatibility issues."""
        cmd = [
            'mysql',
            f'-h{config["host"]}',
            f'-P{config["port"]}',
            f'-u{config["user"]}',
            f'-p{config["password"]}',
            config['database']
        ]
        return cmd

    def handle(self, *args, **options):
        dump_file = options['dump_file']
        dsn = options['dsn']

        if not os.path.exists(dump_file):
            self.stdout.write(
                self.style.ERROR(f"Dump file not found: {dump_file}")
            )
            return

        # Get DSN from options or environment
        if not dsn:
            dsn = os.environ.get('DATABASE_URL')
            if not dsn:
                self.stdout.write(
                    self.style.ERROR(
                        "No DSN provided. Use --dsn or set DATABASE_URL environment variable.\n"
                        "Example: mysql://user:pass@host:port/database"
                    )
                )
                return

        try:
            db_config = self.parse_dsn(dsn)
        except ValueError as e:
            self.stdout.write(self.style.ERROR(str(e)))
            return

        self.stdout.write(f"Importing to: {db_config['host']}:{db_config['port']}/{db_config['database']}")

        # Handle ZIP file extraction
        sql_file_path = dump_file
        temp_dir = None

        if dump_file.endswith('.zip'):
            self.stdout.write("Extracting ZIP file...")
            temp_dir = tempfile.mkdtemp()
            try:
                with zipfile.ZipFile(dump_file, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                    # Look for SQL file in extracted contents
                    extracted_files = os.listdir(temp_dir)
                    sql_files = [f for f in extracted_files if f.endswith('.sql')]
                    if not sql_files:
                        self.stdout.write(
                            self.style.ERROR("No SQL file found in ZIP archive")
                        )
                        return
                    sql_file_path = os.path.join(temp_dir, sql_files[0])
                    self.stdout.write(f"Found SQL file: {sql_files[0]}")
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed to extract ZIP file: {str(e)}")
                )
                return

        # Build MySQL command
        mysql_cmd = self.build_mysql_command(db_config)

        # Import SQL dump
        self.stdout.write(f"Importing SQL dump from {sql_file_path}...")
        try:
            with open(sql_file_path, 'r', encoding='utf-8') as f:
                import_process = subprocess.Popen(
                    mysql_cmd,
                    stdin=f,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                stdout, stderr = import_process.communicate()

                if import_process.returncode != 0:
                    self.stdout.write(
                        self.style.ERROR(f"Import failed: {stderr}")
                    )
                    raise Exception(f"MySQL import failed: {stderr}")
                else:
                    self.stdout.write(
                        self.style.SUCCESS("SQL dump imported successfully!")
                    )
                    if stdout:
                        self.stdout.write(f"Output: {stdout}")

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Import failed: {str(e)}")
            )
            raise
        finally:
            # Clean up temporary directory
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                self.stdout.write("Cleaned up temporary files.")

        self.stdout.write(
            self.style.SUCCESS("Import completed!")
        )