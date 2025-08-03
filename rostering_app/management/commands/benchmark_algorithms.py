"""Benchmark different scheduling algorithms across multiple test cases."""
import json
import os
import statistics
import time
import traceback
from datetime import date, timedelta
from typing import Dict, List, Any

from django.core.management.base import BaseCommand
from django.db import transaction

from rostering_app.converters import employees_to_core, shifts_to_core
from rostering_app.models import ScheduleEntry, Employee, Shift, Company
from rostering_app.services.enhanced_analytics import EnhancedAnalytics
from rostering_app.services.kpi_calculator import KPICalculator
from scheduling_core import ILPScheduler
from scheduling_core.base import SchedulingProblem
from scheduling_core.genetic_algorithm import GeneticAlgorithmScheduler
from scheduling_core.simulated_annealing_compact import SimulatedAnnealingScheduler


class Command(BaseCommand):
    help = "Benchmark scheduling algorithms across different company sizes"

    def add_arguments(self, parser):
        parser.add_argument(
            '--load-fixtures',
            action='store_true',
            help='Load fixtures into database (clears existing data)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force the benchmark to run even if it is already in progress',
        )
        parser.add_argument(
            '--algorithm',
            type=str,
            help='Run only specific algorithm (LinearProgramming, GeneticAlgorithm, SimulatedAnnealing)',
        )
        parser.add_argument(
            '--company',
            type=str,
            help='Run only specific company (small_company, medium_company, large_company)',
        )

    def handle(self, *args, **options):
        load_fixtures = options.get('load_fixtures', False)
        algorithm_filter = options.get('algorithm')
        company_filter = options.get('company')

        try:
            test_cases = [
                {
                    'name': 'small_company',
                    'display_name': 'Kleines Unternehmen (10 MA, 2 Schichten)',
                    'employee_fixture': 'rostering_app/fixtures/small_company/employees.json',
                    'shift_fixture': 'rostering_app/fixtures/small_company/shifts.json'
                },
                {
                    'name': 'medium_company',
                    'display_name': 'Mittleres Unternehmen (30 MA, 3 Schichten)',
                    'employee_fixture': 'rostering_app/fixtures/medium_company/employees.json',
                    'shift_fixture': 'rostering_app/fixtures/medium_company/shifts.json'
                },
                {
                    'name': 'bigger_company',
                    'display_name': 'Größeres Unternehmen (60 MA, 4 Schichten)',
                    'employee_fixture': 'rostering_app/fixtures/bigger_company/employees.json',
                    'shift_fixture': 'rostering_app/fixtures/bigger_company/shifts.json'
                },
                {
                    'name': 'large_company',
                    'display_name': 'Großes Unternehmen (100 MA, 5 Schichten)',
                    'employee_fixture': 'rostering_app/fixtures/large_company/employees.json',
                    'shift_fixture': 'rostering_app/fixtures/large_company/shifts.json'
                }
            ]

            if company_filter:
                test_cases = [tc for tc in test_cases if tc['name'] == company_filter]
                if not test_cases:
                    self.stdout.write(self.style.ERROR(f"Company '{company_filter}' not found"))
                    return

            algorithm_classes = [
                ILPScheduler,
                GeneticAlgorithmScheduler,
                SimulatedAnnealingScheduler,
            ]

            if algorithm_filter:
                algorithm_map = {
                    'LinearProgramming': ILPScheduler,
                    'GeneticAlgorithm': GeneticAlgorithmScheduler,
                    'CompactSA': SimulatedAnnealingScheduler,
                }
                if algorithm_filter in algorithm_map:
                    algorithm_classes = [algorithm_map[algorithm_filter]]
                else:
                    self.stdout.write(self.style.ERROR(f"Algorithm '{algorithm_filter}' not found"))
                    return

            export_dir = 'export'
            if not os.path.exists(export_dir):
                os.makedirs(export_dir)

            if load_fixtures:
                ScheduleEntry.objects.all().delete()

                Employee.objects.all().delete()
                Shift.objects.all().delete()
                Company.objects.all().delete()

                self.stdout.write("Cleared database")

                # Load company fixtures first
                self._load_company_fixtures('rostering_app/fixtures/companies.json')
                self.stdout.write(f"Loaded {Company.objects.count()} companies")

                for test_case in test_cases:
                    self._load_fixtures(test_case['employee_fixture'], test_case['shift_fixture'])

                self.stdout.write(
                    f"Loaded {Employee.objects.count()} employees and {Shift.objects.count()} shifts total")
            else:
                self.stdout.write("Using existing database data (no fixtures loaded)")

            all_results = {}

            for test_case in test_cases:
                self.stdout.write(f"\n{'=' * 60}")
                self.stdout.write(f"Benchmarking: {test_case['display_name']}")
                self.stdout.write(f"{'=' * 60}\n")

                company_name_mapping = {
                    'small_company': 'Kleines Unternehmen',
                    'medium_company': 'Mittleres Unternehmen',
                    'bigger_company': 'Größeres Unternehmen',
                    'large_company': 'Großes Unternehmen'
                }

                company_name = company_name_mapping.get(test_case['name'])
                self.stdout.write(f"Looking for company: '{company_name}' for test case '{test_case['name']}'")

                if company_name:
                    company = Company.objects.filter(name=company_name).first()
                else:
                    company = Company.objects.filter(name__icontains=test_case['name'].split('_')[0]).first()

                self.stdout.write(f"Using company: {company.name if company else 'NOT FOUND'}")
                if company:
                    self.stdout.write(f"Company settings: sunday_is_workday={company.sunday_is_workday}")

                if not company:
                    self.stdout.write(self.style.ERROR(f"Company not found for test case {test_case['name']}"))
                    continue

                problem = self._create_problem(company)
                self.stdout.write(
                    f"Problem created with {len(problem.employees)} employees and {len(problem.shifts)} shifts")

                algorithms = []
                for algorithm_class in algorithm_classes:
                    algorithms.append(algorithm_class(sundays_off=not company.sunday_is_workday))

                results = {}
                for algorithm in algorithms:
                    self.stdout.write(f"\nTesting {algorithm.name}...")
                    self._clear_algorithm_company_entries(company, algorithm.name)
                    start_time = time.time()
                    try:
                        entries = algorithm.solve(problem)
                        runtime = time.time() - start_time
                        self._save_entries(entries, algorithm.name)
                        kpis = self._calculate_comprehensive_kpis(company, algorithm.name)

                        results[algorithm.name] = {
                            'runtime': runtime,
                            'kpis': kpis,
                            'status': 'success',
                            'entries_count': len(entries)
                        }

                        self.stdout.write(self.style.SUCCESS(
                            f"✓ {algorithm.name} completed in {runtime:.2f}s with {len(entries)} entries"
                        ))

                    except Exception as e:
                        runtime = time.time() - start_time
                        results[algorithm.name] = {
                            'runtime': runtime,
                            'kpis': None,
                            'status': 'failed',
                            'error': str(e)
                        }
                        self.stdout.write(self.style.ERROR(
                            f"✗ {algorithm.name} failed: {str(e)}"
                        ))
                        traceback.print_exc()

                all_results[test_case['name']] = {
                    'display_name': test_case['display_name'],
                    'results': results,
                    'problem_size': {
                        'employees': len(problem.employees),
                        'shifts': len(problem.shifts),
                        'days': (problem.end_date - problem.start_date).days + 1
                    }
                }

                self._save_test_results(test_case['name'], results, export_dir)
                self._generate_enhanced_test_graphs_with_analytics(test_case['name'], results, export_dir, company)

            overall_file = os.path.join(export_dir, 'benchmark_results.json')
            with open(overall_file, 'w', encoding='utf-8') as f:
                json.dump(all_results, f, indent=4, default=str)

            EnhancedAnalytics.generate_comparison_graphs_across_test_cases(all_results, export_dir)

            self.stdout.write(self.style.SUCCESS(
                f"\nBenchmark complete! Results saved to {export_dir}/"
            ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f"Benchmark failed: {str(e)}"
            ))
            traceback.print_exc()
            raise

    def _clear_algorithm_company_entries(self, company, algorithm_name):
        deleted_count = ScheduleEntry.objects.filter(
            company=company,
            algorithm=algorithm_name
        ).delete()[0]

        if deleted_count > 0:
            self.stdout.write(f"Cleared {deleted_count} existing entries for {algorithm_name} at {company.name}")

    def _load_fixtures(self, employee_file: str, shift_file: str):
        with open(employee_file, 'r', encoding='utf-8') as f:
            employee_data = json.load(f)
            for item in employee_data:
                fields = item['fields']
                if 'company' in fields:
                    fields['company'] = Company.objects.get(pk=fields['company'])
                Employee.objects.create(**fields)
        with open(shift_file, 'r', encoding='utf-8') as f:
            shift_data = json.load(f)
            for item in shift_data:
                fields = item['fields']
                if 'company' in fields:
                    fields['company'] = Company.objects.get(pk=fields['company'])
                Shift.objects.create(**fields)

    def _load_company_fixtures(self, company_file: str):
        with open(company_file, 'r', encoding='utf-8') as f:
            company_data = json.load(f)
            for item in company_data:
                fields = item['fields']
                pk = item.get('pk')
                if pk is not None:
                    Company.objects.create(pk=pk, **fields)
                else:
                    Company.objects.create(**fields)

    def _create_problem(self, company) -> SchedulingProblem:
        company_employees = Employee.objects.filter(company=company)
        self.stdout.write(f"Found {company_employees.count()} employees for company {company.name}")
        employees = employees_to_core(company_employees)

        company_shifts = Shift.objects.filter(company=company)
        self.stdout.write(f"Found {company_shifts.count()} shifts for company {company.name}")
        shifts = shifts_to_core(company_shifts)

        return SchedulingProblem(
            employees=employees,
            shifts=shifts,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            company=company
        )

    def _save_entries(self, entries: List, algorithm_name: str = ''):
        with transaction.atomic():
            for entry in entries:
                employee = Employee.objects.get(id=entry.employee_id)
                company = employee.company
                ScheduleEntry.objects.create(
                    employee_id=entry.employee_id,
                    date=entry.date,
                    shift_id=entry.shift_id,
                    company=company,
                    algorithm=algorithm_name
                )

    def _calculate_comprehensive_kpis(self, company, algorithm_name) -> Dict[str, Any]:
        employees = list(Employee.objects.filter(company=company))
        shifts = list(Shift.objects.filter(company=company))
        start_date = date(2025, 1, 1)
        end_date = date(2025, 12, 31)

        from rostering_app.utils import get_working_days_in_range
        working_days = get_working_days_in_range(start_date, end_date, company)
        total_working_days = len(working_days)

        kpi_calculator = KPICalculator(company)
        entries = ScheduleEntry.objects.filter(
            company=company,
            algorithm=algorithm_name,
            date__gte=start_date,
            date__lte=end_date
        )

        monthly_stats = {}
        for month in range(1, 13):
            month_start = date(2025, month, 1)
            month_end = date(2025, month, 28)
            while month_end.month == month:
                month_end += timedelta(days=1)
            month_end -= timedelta(days=1)

            company_analytics = kpi_calculator.calculate_company_analytics(
                entries, 2025, month, algorithm_name
            )

            contract_32h = []
            contract_40h = []

            for emp in employees:
                emp_entries = [e for e in entries if e.employee.id == emp.id and month_start <= e.date <= month_end]
                emp_hours = sum(
                    kpi_calculator.calculate_shift_hours_in_month(e.shift, e.date, month_start, month_end)
                    for e in emp_entries
                )

                if emp.max_hours_per_week == 32:
                    contract_32h.append(emp_hours)
                elif emp.max_hours_per_week == 40:
                    contract_40h.append(emp_hours)

            monthly_stats[month] = {
                'contract_32h_avg': statistics.mean(contract_32h) if contract_32h else 0,
                'contract_40h_avg': statistics.mean(contract_40h) if contract_40h else 0,
                'contract_32h_count': len(contract_32h),
                'contract_40h_count': len(contract_40h),
                'company_analytics': company_analytics
            }

        coverage_stats = kpi_calculator.calculate_coverage_stats(entries, start_date, end_date)
        weekly_violations_detailed = kpi_calculator.check_weekly_hours_violations_detailed(entries, start_date,
                                                                                           end_date)
        rest_violations_detailed = kpi_calculator.check_rest_period_violations_detailed(entries, start_date, end_date)
        total_weekly_violations = weekly_violations_detailed['total_violations']
        total_rest_violations = rest_violations_detailed['total_violations']

        # Calculate fairness metrics
        employee_hours = []
        for emp in employees:
            emp_entries = [e for e in entries if e.employee.id == emp.id]
            emp_hours = sum(
                kpi_calculator.calculate_shift_hours_in_range(e.shift, e.date, start_date, end_date)
                for e in emp_entries
            )
            employee_hours.append(emp_hours)

        if employee_hours:
            hours_mean = statistics.mean(employee_hours)
            hours_stdev = statistics.stdev(employee_hours) if len(employee_hours) > 1 else 0
            hours_cv = (hours_stdev / hours_mean * 100) if hours_mean > 0 else 0
            gini = self._calculate_gini(employee_hours)
        else:
            hours_mean = hours_stdev = hours_cv = gini = 0

        return {
            'monthly_stats': monthly_stats,
            'coverage_stats': coverage_stats,
            'constraint_violations': {
                'weekly_violations': total_weekly_violations,
                'rest_period_violations': total_rest_violations,
                'total_violations': total_weekly_violations + total_rest_violations,
                'weekly_violations_detailed': weekly_violations_detailed,
                'rest_period_violations_detailed': rest_violations_detailed
            },
            'fairness_metrics': {
                'gini_coefficient': gini,
                'hours_std_dev': hours_stdev,
                'hours_cv': hours_cv,
                'min_hours': min(employee_hours) if employee_hours else 0,
                'max_hours': max(employee_hours) if employee_hours else 0,
                'avg_hours': hours_mean
            },
            'total_working_days': total_working_days,
            'total_employees': len(employees),
            'total_shifts': len(shifts)
        }

    def _calculate_gini(self, values: List[float]) -> float:
        n = len(values)
        total = sum(values)
        if n == 0 or total == 0:
            return 0.0
        if n == 1:
            return 0.0
        sorted_values = sorted(values)
        cumsum = sum((i + 1) * val for i, val in enumerate(sorted_values))
        return (2 * cumsum) / (n * total) - (n + 1) / n

    def _save_test_results(self, test_name: str, results: Dict, export_dir: str):
        test_dir = os.path.join(export_dir, test_name)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        results_file = os.path.join(test_dir, 'results.json')
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=4, default=str)

    def _generate_enhanced_test_graphs_with_analytics(self, test_name: str, results: Dict, export_dir: str, company):
        self.stdout.write(f"Generating graphs for {test_name}...")

        all_entries = ScheduleEntry.objects.filter(company=company)
        employees = list(Employee.objects.filter(company=company))
        shifts = list(Shift.objects.filter(company=company))

        analytics = EnhancedAnalytics(company, all_entries, employees, shifts)
        analytics.generate_algorithm_comparison_graphs(results, export_dir, test_name)

        self.stdout.write(self.style.SUCCESS(f"Generated enhanced graphs for {test_name}"))
