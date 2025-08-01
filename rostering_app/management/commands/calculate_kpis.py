"""
Management command to pre-calculate and store KPIs for testing.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from datetime import date

from rostering_app.models import Company, Employee



class Command(BaseCommand):
    help = 'Pre-calculate and store KPIs for all companies and algorithms'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            default=date.today().year,
            help='Year for KPI calculation (default: current year)'
        )
        parser.add_argument(
            '--month',
            type=int,
            default=date.today().month,
            help='Month for KPI calculation (default: current month)'
        )
        parser.add_argument(
            '--company',
            type=int,
            help='Specific company ID to calculate KPIs for'
        )
        parser.add_argument(
            '--algorithm',
            type=str,
            help='Specific algorithm to calculate KPIs for'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recalculation even if KPIs already exist'
        )

    def handle(self, *args, **options):
        year = options['year']
        month = options['month']
        company_id = options['company']
        algorithm = options['algorithm']
        force_recalculate = options['force']

        self.stdout.write(
            self.style.SUCCESS(
                f'Starting KPI calculation for {year}-{month:02d}'
                f'{f" (Company: {company_id})" if company_id else ""}'
                f'{f" (Algorithm: {algorithm})" if algorithm else ""}'
            )
        )

        # Get companies to process
        if company_id:
            companies = Company.objects.filter(id=company_id)
        else:
            companies = Company.objects.all()

        total_companies = companies.count()
        processed_companies = 0

        for company in companies:
            self.stdout.write(f'Processing company: {company.name}')
            
            try:
                # Get available algorithms for this company
                from rostering_app.models import ScheduleEntry
                available_algorithms = ScheduleEntry.objects.filter(
                    company=company
                ).values_list('algorithm', flat=True).distinct()
                available_algorithms = [alg for alg in available_algorithms if alg]
                
                if algorithm:
                    if algorithm in available_algorithms:
                        algorithms_to_process = [algorithm]
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f'Algorithm "{algorithm}" not found for company {company.name}'
                            )
                        )
                        continue
                else:
                    algorithms_to_process = available_algorithms

                for alg in algorithms_to_process:
                    self.stdout.write(f'  Processing algorithm: {alg}')
                    
                    try:
                        # Note: KPI calculation is now done in real-time by the frontend
                        # This command is no longer needed as KPIs are calculated on-demand
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'    ✓ KPI calculation moved to real-time frontend processing'
                            )
                        )
                        
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f'    ✗ Error processing algorithm {alg}: {e}'
                            )
                        )
                
                processed_companies += 1
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'Error processing company {company.name}: {e}'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'KPI calculation completed. Processed {processed_companies}/{total_companies} companies.'
            )
        ) 