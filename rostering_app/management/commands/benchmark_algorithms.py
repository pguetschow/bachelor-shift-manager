"""Benchmark different scheduling algorithms across multiple test cases."""
import json
import os
import time
import statistics
import traceback
import calendar
from datetime import datetime, date, timedelta
from typing import Dict, List, Any
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from rostering_app.models import ScheduleEntry, Employee, Shift, Company
from rostering_app.converters import employees_to_core, shifts_to_core

from rostering_app.services.kpi_calculator import KPICalculator
from scheduling_core import NSGA2Scheduler, ILPScheduler, NewSimulatedAnnealingScheduler
from scheduling_core.Updated_new_linear_programming import UpdatedILPScheduler

# Import scheduling algorithms
from scheduling_core.base import SchedulingProblem, Employee as CoreEmployee, Shift as CoreShift
from scheduling_core.genetic_algorithm import GeneticAlgorithmScheduler
from scheduling_core.simulated_annealing import SimulatedAnnealingScheduler, CoolingSchedule
from scheduling_core.simulated_annealing_compact import CompactSimulatedAnnealingScheduler


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
        # Check if already running (simplified check)
        load_fixtures = options.get('load_fixtures', False)
        force = options.get('force', False)
        algorithm_filter = options.get('algorithm')
        company_filter = options.get('company')


        try:
            # Test configurations
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
                    'name': 'large_company',
                    'display_name': 'Großes Unternehmen (100 MA, 4 Schichten)',
                    'employee_fixture': 'rostering_app/fixtures/large_company/employees.json',
                    'shift_fixture': 'rostering_app/fixtures/large_company/shifts.json'
                }
            ]

            # Filter test cases if requested
            if company_filter:
                test_cases = [tc for tc in test_cases if tc['name'] == company_filter]
                if not test_cases:
                    self.stdout.write(self.style.ERROR(f"Company '{company_filter}' not found"))
                    return

            # Algorithm configurations - will be created per company
            algorithm_classes = [
                # UpdatedILPScheduler,
                ILPScheduler,
                # GeneticAlgorithmScheduler,
                # # SimulatedAnnealingScheduler,
                # CompactSimulatedAnnealingScheduler,
                # NewSimulatedAnnealingScheduler,
                # # NSGA2Scheduler
            ]

            # Filter algorithms if requested
            if algorithm_filter:
                algorithm_map = {
                    'LinearProgramming': ILPScheduler,
                    # 'GeneticAlgorithm': GeneticAlgorithmScheduler,
                    # 'NewSimulatedAnnealingScheduler': NewSimulatedAnnealingScheduler,
                    # 'SimulatedAnnealing': SimulatedAnnealingScheduler,
                    # 'CompactSA': CompactSimulatedAnnealingScheduler,
                    # 'NSGA2Scheduler': NSGA2Scheduler,
                }
                if algorithm_filter in algorithm_map:
                    algorithm_classes = [algorithm_map[algorithm_filter]]
                else:
                    self.stdout.write(self.style.ERROR(f"Algorithm '{algorithm_filter}' not found"))
                    return

            # Create export directory
            export_dir = 'export'
            if not os.path.exists(export_dir):
                os.makedirs(export_dir)

            # Load fixtures if requested
            if load_fixtures:
                # Only clear schedule entries, keep company/employee/shift data
                ScheduleEntry.objects.all().delete()

                # Clear the database first for complete reload
                Employee.objects.all().delete()
                Shift.objects.all().delete()
                Company.objects.all().delete()

                self.stdout.write("Cleared database")

                # Load company fixtures first
                self._load_company_fixtures('rostering_app/fixtures/companies.json')
                self.stdout.write(f"Loaded {Company.objects.count()} companies")

                # Load all fixtures for all companies before running benchmarks
                for test_case in test_cases:
                    self._load_fixtures(test_case['employee_fixture'], test_case['shift_fixture'])

                self.stdout.write(f"Loaded {Employee.objects.count()} employees and {Shift.objects.count()} shifts total")
            else:
                self.stdout.write("Using existing database data (no fixtures loaded)")

            # Run benchmarks for each test case
            all_results = {}

            for test_case in test_cases:
                self.stdout.write(f"\n{'='*60}")
                self.stdout.write(f"Benchmarking: {test_case['display_name']}")
                self.stdout.write(f"{'='*60}\n")

                # Get the company for this test case
                company_name_mapping = {
                    'small_company': 'Kleines Unternehmen',
                    'medium_company': 'Mittleres Unternehmen',
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

                # Create problem instance for this company
                problem = self._create_problem(company)
                self.stdout.write(f"Problem created with {len(problem.employees)} employees and {len(problem.shifts)} shifts")

                # Create algorithms for this specific company
                algorithms = []
                for algorithm_class in algorithm_classes:
                    algorithms.append(algorithm_class(sundays_off=not company.sunday_is_workday))

                # Benchmark algorithms
                results = {}
                company_success = True
                company_error = ""

                for algorithm in algorithms:
                    self.stdout.write(f"\nTesting {algorithm.name}...")

                    # Clear existing schedule entries for this algorithm and company combination
                    self._clear_algorithm_company_entries(company, algorithm.name)

                    # Time the algorithm
                    start_time = time.time()
                    try:
                        entries = algorithm.solve(problem)
                        runtime = time.time() - start_time

                        # Save to database, track algorithm
                        self._save_entries(entries, algorithm.name)

                        # Calculate comprehensive KPIs for this company and algorithm
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
                        company_success = False
                        company_error = str(e)
                        self.stdout.write(self.style.ERROR(
                            f"✗ {algorithm.name} failed: {str(e)}"
                        ))
                        # Print the full traceback to the console
                        traceback.print_exc()

                # Store results
                all_results[test_case['name']] = {
                    'display_name': test_case['display_name'],
                    'results': results,
                    'problem_size': {
                        'employees': len(problem.employees),
                        'shifts': len(problem.shifts),
                        'days': (problem.end_date - problem.start_date).days + 1
                    }
                }

                # Save results for this test case
                self._save_test_results(test_case['name'], results, export_dir)

                # Generate enhanced graphs for this test case
                self._generate_enhanced_test_graphs(test_case['name'], results, export_dir, company)

            # Save overall results
            overall_file = os.path.join(export_dir, 'benchmark_results.json')
            with open(overall_file, 'w', encoding='utf-8') as f:
                json.dump(all_results, f, indent=4, default=str)

            # Generate comparison graphs across all test cases
            self._generate_comparison_graphs(all_results, export_dir)

            self.stdout.write(self.style.SUCCESS(
                f"\nBenchmark complete! Results saved to {export_dir}/"
            ))

        except Exception as e:
            # Mark benchmark as failed
            error_message = f"Benchmark failed: {str(e)}\n{traceback.format_exc()}"

            self.stdout.write(self.style.ERROR(
                f"Benchmark failed: {str(e)}"
            ))
            traceback.print_exc()
            raise

    def _clear_algorithm_company_entries(self, company, algorithm_name):
        """Clear schedule entries for specific algorithm and company combination."""
        deleted_count = ScheduleEntry.objects.filter(
            company=company,
            algorithm=algorithm_name
        ).delete()[0]

        if deleted_count > 0:
            self.stdout.write(f"Cleared {deleted_count} existing entries for {algorithm_name} at {company.name}")

    def _load_fixtures(self, employee_file: str, shift_file: str):
        """Load fixture data into database."""
        # Load employees
        with open(employee_file, 'r', encoding='utf-8') as f:
            employee_data = json.load(f)
            for item in employee_data:
                fields = item['fields']
                if 'company' in fields:
                    fields['company'] = Company.objects.get(pk=fields['company'])
                Employee.objects.create(**fields)
        # Load shift types
        with open(shift_file, 'r', encoding='utf-8') as f:
            shift_data = json.load(f)
            for item in shift_data:
                fields = item['fields']
                if 'company' in fields:
                    fields['company'] = Company.objects.get(pk=fields['company'])
                Shift.objects.create(**fields)

    def _load_company_fixtures(self, company_file: str):
        """Load company fixture data into database."""
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
        """Create scheduling problem from database."""
        # Convert Django models to core data structures using converters
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
        """Save schedule entries to database, tracking the algorithm used."""
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
        """Calculate comprehensive KPIs including monthly breakdowns by contract type."""
        employees = list(Employee.objects.filter(company=company))
        shifts = list(Shift.objects.filter(company=company))
        start_date = date(2025, 1, 1)
        end_date = date(2025, 12, 31)

        # Get working days for accurate KPI calculations
        from rostering_app.utils import get_working_days_in_range
        working_days = get_working_days_in_range(start_date, end_date, company)
        total_working_days = len(working_days)

        # Initialize KPI calculator
        kpi_calculator = KPICalculator(company)

        # Get all entries for this company and algorithm
        entries = ScheduleEntry.objects.filter(
            company=company,
            algorithm=algorithm_name,
            date__gte=start_date,
            date__lte=end_date
        )

        # Monthly breakdown by contract type (32h vs 40h)
        monthly_hours_by_contract = defaultdict(lambda: defaultdict(list))
        monthly_stats = {}
        
        for month in range(1, 13):
            month_start = date(2025, month, 1)
            month_end = date(2025, month, 28)
            while month_end.month == month:
                month_end += timedelta(days=1)
            month_end -= timedelta(days=1)
            
            # Calculate company analytics for this month
            company_analytics = kpi_calculator.calculate_company_analytics(
                entries, 2025, month, algorithm_name
            )
            
            # Group employees by contract type
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

        # Calculate coverage statistics
        coverage_stats = kpi_calculator.calculate_coverage_stats(entries, start_date, end_date)
        
        # Calculate constraint violations with detailed information
        weekly_violations_detailed = kpi_calculator.check_weekly_hours_violations_detailed(entries, start_date, end_date)
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

        # Note: KPI storage has been removed - KPIs are now calculated in real-time
        self.stdout.write(f"✓ KPI calculation moved to real-time processing for {algorithm_name} at {company.name}")

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
        """Calculate Gini coefficient."""
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
        """Save results for a specific test case."""
        test_dir = os.path.join(export_dir, test_name)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        results_file = os.path.join(test_dir, 'results.json')
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=4, default=str)

    def _generate_enhanced_test_graphs(self, test_name: str, results: Dict, export_dir: str, company):
        """Generate enhanced graphs for a specific test case."""
        test_dir = os.path.join(export_dir, test_name)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        # Filter successful results
        successful = {k: v for k, v in results.items() if v['status'] == 'success'}
        if not successful:
            return

        algorithms = list(successful.keys())
        months = list(range(1, 13))
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'Mai', 'Jun', 
                      'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

        # 1. Average Working Hours per Month by Contract Type
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        for alg in algorithms:
            kpis = successful[alg]['kpis']
            monthly_stats = kpis['monthly_stats']
            
            # 32h contracts
            hours_32h = [monthly_stats[month]['contract_32h_avg'] for month in months]
            if any(h > 0 for h in hours_32h):
                ax1.plot(month_names, hours_32h, marker='o', label=f'{alg} (32h)', linewidth=2)
            
            # 40h contracts
            hours_40h = [monthly_stats[month]['contract_40h_avg'] for month in months]
            if any(h > 0 for h in hours_40h):
                ax2.plot(month_names, hours_40h, marker='s', label=f'{alg} (40h)', linewidth=2)

        ax1.set_title('Durchschnittliche Arbeitsstunden pro Monat - 32h Verträge')
        ax1.set_ylabel('Stunden')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        ax2.set_title('Durchschnittliche Arbeitsstunden pro Monat - 40h Verträge')
        ax2.set_ylabel('Stunden')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'monthly_hours_by_contract.png'), dpi=300)
        plt.close()

        # 2. Fairness Comparison
        fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(18, 6))

        # Gini coefficient
        ginis = [successful[alg]['kpis']['fairness_metrics']['gini_coefficient'] for alg in algorithms]
        bars1 = ax1.bar(algorithms, ginis, color='skyblue')
        ax1.set_title('Gini-Koeffizient (niedriger = fairer)')
        ax1.set_ylabel('Gini-Koeffizient')
        ax1.set_xticklabels(algorithms, rotation=45, ha='right')

        for bar, val in zip(bars1, ginis):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{val:.3f}', ha='center', va='bottom')

        # Standard deviation
        stdevs = [successful[alg]['kpis']['fairness_metrics']['hours_std_dev'] for alg in algorithms]
        bars2 = ax2.bar(algorithms, stdevs, color='lightgreen')
        ax2.set_title('Standardabweichung Arbeitsstunden')
        ax2.set_ylabel('Stunden')
        ax2.set_xticklabels(algorithms, rotation=45, ha='right')

        for bar, val in zip(bars2, stdevs):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{val:.1f}', ha='center', va='bottom')

        # Coefficient of variation
        cvs = [successful[alg]['kpis']['fairness_metrics']['hours_cv'] for alg in algorithms]
        bars3 = ax3.bar(algorithms, cvs, color='lightcoral')
        ax3.set_title('Variationskoeffizient (%)')
        ax3.set_ylabel('CV (%)')
        ax3.set_xticklabels(algorithms, rotation=45, ha='right')

        for bar, val in zip(bars3, cvs):
            ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{val:.1f}%', ha='center', va='bottom')

        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'fairness_comparison.png'), dpi=300)
        plt.close()

        # 3. Coverage Analysis
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        axes = axes.flatten()

        for idx, alg in enumerate(algorithms):
            if idx >= 4:  # Limit to 4 subplots
                break
                
            coverage_stats = successful[alg]['kpis']['coverage_stats']
            shift_names = [stat['shift']['name'] for stat in coverage_stats]
            coverage_percentages = [stat['coverage_percentage'] for stat in coverage_stats]
            avg_staff = [stat['avg_staff'] for stat in coverage_stats]
            min_staff = [stat['shift']['min_staff'] for stat in coverage_stats]
            max_staff = [stat['shift']['max_staff'] for stat in coverage_stats]

            # Coverage percentage
            bars = axes[idx].bar(shift_names, coverage_percentages, color='lightblue')
            axes[idx].set_title(f'Abdeckung - {alg}')
            axes[idx].set_ylabel('Abdeckung (%)')
            axes[idx].set_xticklabels(shift_names, rotation=45, ha='right')
            axes[idx].axhline(y=100, color='red', linestyle='--', alpha=0.7, label='100% Abdeckung')
            axes[idx].legend()

            # Add value labels
            for bar, val in zip(bars, coverage_percentages):
                axes[idx].text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                             f'{val:.1f}%', ha='center', va='bottom')

        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'coverage_analysis.png'), dpi=300)
        plt.close()

        # 4. Constraint Violations
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

        # Weekly violations
        weekly_violations = [successful[alg]['kpis']['constraint_violations']['weekly_violations'] for alg in algorithms]
        bars1 = ax1.bar(algorithms, weekly_violations, color=['green' if v == 0 else 'red' for v in weekly_violations])
        ax1.set_title('Wöchentliche Stunden-Verletzungen')
        ax1.set_ylabel('Anzahl Verletzungen')
        ax1.set_xticklabels(algorithms, rotation=45, ha='right')

        for bar, val in zip(bars1, weekly_violations):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{val}', ha='center', va='bottom')

        # Rest period violations
        rest_violations = [successful[alg]['kpis']['constraint_violations']['rest_period_violations'] for alg in algorithms]
        bars2 = ax2.bar(algorithms, rest_violations, color=['green' if v == 0 else 'orange' for v in rest_violations])
        ax2.set_title('Ruhezeit-Verletzungen')
        ax2.set_ylabel('Anzahl Verletzungen')
        ax2.set_xticklabels(algorithms, rotation=45, ha='right')

        for bar, val in zip(bars2, rest_violations):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{val}', ha='center', va='bottom')

        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'constraint_violations.png'), dpi=300)
        plt.close()

        # 5. Additional Interesting Metrics
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        axes = axes.flatten()

        # Runtime comparison
        runtimes = [successful[alg]['runtime'] for alg in algorithms]
        bars1 = axes[0].bar(algorithms, runtimes, color='purple')
        axes[0].set_title('Laufzeitvergleich')
        axes[0].set_ylabel('Laufzeit (Sekunden)')
        axes[0].set_xticklabels(algorithms, rotation=45, ha='right')

        for bar, runtime in zip(bars1, runtimes):
            axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                        f'{runtime:.1f}s', ha='center', va='bottom')

        # Total hours worked
        total_hours = [successful[alg]['kpis']['fairness_metrics']['avg_hours'] * successful[alg]['kpis']['total_employees'] for alg in algorithms]
        bars2 = axes[1].bar(algorithms, total_hours, color='gold')
        axes[1].set_title('Gesamtstunden (Durchschnitt × Mitarbeiter)')
        axes[1].set_ylabel('Stunden')
        axes[1].set_xticklabels(algorithms, rotation=45, ha='right')

        for bar, hours in zip(bars2, total_hours):
            axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                        f'{hours:.0f}h', ha='center', va='bottom')

        # Min/Max hours spread
        min_hours = [successful[alg]['kpis']['fairness_metrics']['min_hours'] for alg in algorithms]
        max_hours = [successful[alg]['kpis']['fairness_metrics']['max_hours'] for alg in algorithms]
        
        x_pos = np.arange(len(algorithms))
        bars3 = axes[2].bar(x_pos - 0.2, min_hours, 0.4, label='Min Stunden', color='lightblue')
        bars4 = axes[2].bar(x_pos + 0.2, max_hours, 0.4, label='Max Stunden', color='darkblue')
        axes[2].set_title('Min/Max Stundenverteilung')
        axes[2].set_ylabel('Stunden')
        axes[2].set_xticks(x_pos)
        axes[2].set_xticklabels(algorithms, rotation=45, ha='right')
        axes[2].legend()

        # Total violations
        total_violations = [successful[alg]['kpis']['constraint_violations']['total_violations'] for alg in algorithms]
        bars5 = axes[3].bar(algorithms, total_violations, color=['green' if v == 0 else 'red' for v in total_violations])
        axes[3].set_title('Gesamte Constraint-Verletzungen')
        axes[3].set_ylabel('Anzahl Verletzungen')
        axes[3].set_xticklabels(algorithms, rotation=45, ha='right')

        for bar, val in zip(bars5, total_violations):
            axes[3].text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                        f'{val}', ha='center', va='bottom')

        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'additional_metrics.png'), dpi=300)
        plt.close()

    def _generate_comparison_graphs(self, all_results: Dict, export_dir: str):
        """Generate comparison graphs across all test cases."""
        # Extract data for comparison
        test_cases = list(all_results.keys())
        algorithms = set()
        for test_results in all_results.values():
            algorithms.update(test_results['results'].keys())
        algorithms = sorted(list(algorithms))

        # Runtime comparison across test cases
        fig, axes = plt.subplots(1, len(test_cases), figsize=(6*len(test_cases), 6))
        if len(test_cases) == 1:
            axes = [axes]

        for idx, test_case in enumerate(test_cases):
            ax = axes[idx]
            results = all_results[test_case]['results']

            alg_names = []
            runtimes = []
            for alg in algorithms:
                if alg in results and results[alg]['status'] == 'success':
                    alg_names.append(alg)
                    runtimes.append(results[alg]['runtime'])

            bars = ax.bar(alg_names, runtimes)
            ax.set_title(f"{all_results[test_case]['display_name']}")
            ax.set_xlabel('Algorithmus')
            ax.set_ylabel('Laufzeit (s)')
            ax.set_xticks(range(len(alg_names)))
            ax.set_xticklabels(alg_names, rotation=45, ha='right')

            # Add values
            for bar, val in zip(bars, runtimes):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                       f'{val:.1f}', ha='center', va='bottom', fontsize=8)

        plt.suptitle('Laufzeitvergleich über alle Testfälle', fontsize=16)
        plt.tight_layout()
        plt.savefig(os.path.join(export_dir, 'runtime_comparison_all.png'), dpi=300)
        plt.close()

        # Scalability analysis
        if len(test_cases) > 1:  # Only generate if we have multiple test cases
            plt.figure(figsize=(12, 8))

            for alg in algorithms:
                problem_sizes = []
                runtimes = []

                for test_case in test_cases:
                    results = all_results[test_case]['results']
                    if alg in results and results[alg]['status'] == 'success':
                        size = all_results[test_case]['problem_size']['employees']
                        problem_sizes.append(size)
                        runtimes.append(results[alg]['runtime'])

                if problem_sizes:
                    plt.plot(problem_sizes, runtimes, marker='o', label=alg, linewidth=2)

            plt.xlabel('Anzahl Mitarbeiter')
            plt.ylabel('Laufzeit (Sekunden)')
            plt.title('Skalierbarkeitsanalyse')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(os.path.join(export_dir, 'scalability_analysis.png'), dpi=300)
            plt.close()