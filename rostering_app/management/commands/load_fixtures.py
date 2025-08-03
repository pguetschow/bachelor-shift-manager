import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Load all fixtures for the application'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reload fixtures even if data exists',
        )

    def handle(self, *args, **options):
        force = options['force']

        self.stdout.write(
            self.style.SUCCESS('Loading fixtures...')
        )

        # Get the fixtures directory
        fixtures_dir = os.path.join(settings.BASE_DIR, 'rostering_app', 'fixtures')

        try:
            # Load companies first
            companies_fixture = os.path.join(fixtures_dir, 'companies.json')
            if os.path.exists(companies_fixture):
                self.stdout.write('Loading companies...')
                call_command('loaddata', companies_fixture, verbosity=1)

            # Load company-specific fixtures
            company_dirs = ['small_company', 'medium_company', 'large_company']

            for company_dir in company_dirs:
                company_path = os.path.join(fixtures_dir, company_dir)
                if os.path.exists(company_path):
                    self.stdout.write(f'Loading {company_dir} fixtures...')

                    # Load employees
                    employees_fixture = os.path.join(company_path, 'employees.json')
                    if os.path.exists(employees_fixture):
                        call_command('loaddata', employees_fixture, verbosity=1)

                    # Load shifts
                    shifts_fixture = os.path.join(company_path, 'shifts.json')
                    if os.path.exists(shifts_fixture):
                        call_command('loaddata', shifts_fixture, verbosity=1)

            self.stdout.write(
                self.style.SUCCESS('All fixtures loaded successfully!')
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error loading fixtures: {e}')
            )
            raise
