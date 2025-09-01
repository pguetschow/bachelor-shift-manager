"""Benchmark different scheduling algorithms across multiple test cases."""
import json
import os
import statistics
from collections import defaultdict
from typing import Set
import time
import traceback
from datetime import date, timedelta
from typing import Dict, List, Any
import numpy as np
from scipy import stats

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

# Define which algorithms are heuristics (non-deterministic)
HEURISTIC_ALGORITHMS = {
    'Genetic Algorithm',
    'Simulated Annealing'
}


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
        parser.add_argument(
            '--runs',
            type=int,
            default=5,
            help='Number of runs for heuristic algorithms',
        )

    def handle(self, *args, **options):
        load_fixtures = options.get('load_fixtures', False)
        algorithm_filter = options.get('algorithm')
        company_filter = options.get('company')
        num_runs = options.get('runs', 20)

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
                    'display_name': 'Größeres Unternehmen (70 MA, 4 Schichten)',
                    'employee_fixture': 'rostering_app/fixtures/bigger_company/employees.json',
                    'shift_fixture': 'rostering_app/fixtures/bigger_company/shifts.json'
                },
                {
                    'name': 'large_company',
                    'display_name': 'Großes Unternehmen (100 MA, 5 Schichten)',
                    'employee_fixture': 'rostering_app/fixtures/large_company/employees.json',
                    'shift_fixture': 'rostering_app/fixtures/large_company/shifts.json'
                },
                {
                    'name': 'tight_company',
                    'display_name': 'Mittleres Unternehmen (eng) (18 MA, 3 Schichten)',
                    'employee_fixture': 'rostering_app/fixtures/tight_company/employees.json',
                    'shift_fixture': 'rostering_app/fixtures/tight_company/shifts.json'
                }
            ]

            if company_filter:
                test_cases = [tc for tc in test_cases if tc['name'] == company_filter]
                if not test_cases:
                    self.stdout.write(self.style.ERROR(f"Company '{company_filter}' not found"))
                    return

            algorithm_classes = [
                # CPScheduler,
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
                    'large_company': 'Großes Unternehmen',
                    'tight_company': 'Knappes Unternehmen'
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
                    
                    # Determine number of runs based on algorithm type
                    runs = num_runs if algorithm.name in HEURISTIC_ALGORITHMS else 1
                    
                    if runs > 1:
                        self.stdout.write(f"Running {algorithm.name} {runs} times (heuristic algorithm)...")
                        import random
                        random.seed(42)  # Use same seed for each run
                        np.random.seed(42)  # Also set numpy random seed
                    
                    run_results = []
                    all_runtimes = []
                    all_kpis = []
                    all_entries_counts = []
                    
                    for run_idx in range(runs):
                        if runs > 1:
                            self.stdout.write(f"  Run {run_idx + 1}/{runs}...")

                        start_time = time.time()
                        try:
                            entries = algorithm.solve(problem)
                            runtime = time.time() - start_time
                            
                            # Only save entries for the first run to avoid database conflicts
                            if run_idx == 0:
                                self._save_entries(entries, algorithm.name)
                            
                            kpis = self._calculate_comprehensive_kpis(company, algorithm.name)
                            
                            run_results.append({
                                'runtime': runtime,
                                'kpis': kpis,
                                'status': 'success',
                                'entries_count': len(entries)
                            })
                            
                            all_runtimes.append(runtime)
                            all_kpis.append(kpis)
                            all_entries_counts.append(len(entries))
                            
                            if runs > 1:
                                self.stdout.write(f"    ✓ Run {run_idx + 1} completed in {runtime:.2f}s")
                            
                        except Exception as e:
                            runtime = time.time() - start_time
                            run_results.append({
                                'runtime': runtime,
                                'kpis': None,
                                'status': 'failed',
                                'error': str(e)
                            })
                            all_runtimes.append(runtime)
                            
                            if runs > 1:
                                self.stdout.write(f"    ✗ Run {run_idx + 1} failed: {str(e)}")
                            else:
                                self.stdout.write(self.style.ERROR(f"✗ {algorithm.name} failed: {str(e)}"))
                                traceback.print_exc()
                    
                    # Calculate statistics for successful runs
                    successful_runs = [r for r in run_results if r['status'] == 'success']
                    if successful_runs:
                        # Calculate runtime statistics
                        runtime_stats = self._calculate_statistics(all_runtimes)
                        
                        # Calculate KPI statistics
                        kpi_stats = self._calculate_kpi_statistics(all_kpis)
                        
                        # Calculate entries count statistics
                        entries_stats = self._calculate_statistics(all_entries_counts)
                        
                        results[algorithm.name] = {
                            'runs': runs,
                            'successful_runs': len(successful_runs),
                            'failed_runs': len(run_results) - len(successful_runs),
                            'runtime_stats': runtime_stats,
                            'kpis_stats': kpi_stats,
                            'entries_count_stats': entries_stats,
                            'individual_runs': run_results,
                            'status': 'success'
                        }
                        
                        avg_runtime = runtime_stats['mean']
                        self.stdout.write(self.style.SUCCESS(
                            f"✓ {algorithm.name} completed {len(successful_runs)}/{runs} runs successfully "
                            f"(avg runtime: {avg_runtime:.2f}s)"
                        ))
                    else:
                        results[algorithm.name] = {
                            'runs': runs,
                            'successful_runs': 0,
                            'failed_runs': len(run_results),
                            'individual_runs': run_results,
                            'status': 'failed'
                        }
                        self.stdout.write(self.style.ERROR(
                            f"✗ {algorithm.name} failed all {runs} runs"
                        ))

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
                json.dump(all_results, f, indent=4, default=str, allow_nan=False)

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
        rest_violations_detailed = kpi_calculator.check_rest_period_violations_detailed(entries, start_date, end_date)
        total_rest_violations = rest_violations_detailed['total_violations']

        # ------------------------------------------------------------------
        # Calculate extended per-employee statistics
        # ------------------------------------------------------------------
        employee_hours: List[float] = []  # actual hours per employee over the year
        expected_hours_list: List[float] = []  # expected contractual hours per employee
        utilizations: List[float] = []  # utilisation ratio (actual/expected)
        utilizations_32: List[float] = []
        utilizations_40: List[float] = []
        overtime_list: List[float] = []  # positive difference between actual and expected
        # Build a lookup for entries per employee to avoid repeated filtering
        entries_by_emp: Dict[int, List[Any]] = defaultdict(list)
        for e in entries:
            entries_by_emp[e.employee.id].append(e)
        for emp in employees:
            emp_entries = entries_by_emp.get(emp.id, [])
            # total actual hours for the employee
            actual = sum(
                kpi_calculator.calculate_shift_hours_in_range(e.shift, e.date, start_date, end_date)
                for e in emp_entries
            )
            employee_hours.append(actual)
            # expected contractual hours (deducting absences if available)
            try:
                expected = kpi_calculator.calculate_expected_yearly_hours(emp, 2025)
            except Exception:
                expected = getattr(emp, 'max_hours_per_week', 0) * 52
            expected_hours_list.append(expected)
            # utilisation ratio
            util = (actual / expected) if expected > 0 else 0.0
            utilizations.append(util)
            # group by contract type
            if getattr(emp, 'max_hours_per_week', 0) == 32:
                utilizations_32.append(util)
            elif getattr(emp, 'max_hours_per_week', 0) == 40:
                utilizations_40.append(util)
            # overtime
            overtime_list.append(max(actual - expected, 0.0))

        # Utilisation statistics
        util_min = min(utilizations) if utilizations else 0.0
        util_max = max(utilizations) if utilizations else 0.0
        util_avg = statistics.mean(utilizations) if utilizations else 0.0
        util_stats_by_contract = {
            '32h': {
                'min': min(utilizations_32) if utilizations_32 else 0.0,
                'max': max(utilizations_32) if utilizations_32 else 0.0,
                'avg': statistics.mean(utilizations_32) if utilizations_32 else 0.0,
            },
            '40h': {
                'min': min(utilizations_40) if utilizations_40 else 0.0,
                'max': max(utilizations_40) if utilizations_40 else 0.0,
                'avg': statistics.mean(utilizations_40) if utilizations_40 else 0.0,
            },
        }

        # Fairness metrics based on actual hours
        if employee_hours:
            hours_mean = statistics.mean(employee_hours)
            hours_stdev = statistics.stdev(employee_hours) if len(employee_hours) > 1 else 0.0
            hours_cv = (hours_stdev / hours_mean * 100) if hours_mean > 0 else 0.0
            gini = self._calculate_gini(employee_hours)
            # Jain fairness index
            sum_hours = sum(employee_hours)
            sum_sq_hours = sum(h * h for h in employee_hours)
            jain_index = (sum_hours * sum_hours) / (len(employee_hours) * sum_sq_hours) if sum_sq_hours > 0 else 0.0
            # Variance (population)
            variance_hours = statistics.pvariance(employee_hours) if len(employee_hours) > 1 else 0.0
            # Gini coefficient on overtime
            gini_overtime = self._calculate_gini(overtime_list) if overtime_list else 0.0
        else:
            hours_mean = hours_stdev = hours_cv = gini = jain_index = variance_hours = gini_overtime = 0.0

        # Preference satisfaction calculation
        total_assigned = 0
        pref_matches = 0

        entries_by_emp: Dict[int, List[ScheduleEntry]] = defaultdict(list)
        for e in entries:
            entries_by_emp[e.employee.id].append(e)

        for emp in employees:
            preferred = set(getattr(emp, "preferred_shifts", []))
            if not preferred:
                continue

            emp_entries = entries_by_emp.get(emp.id, [])
            total_assigned += len(emp_entries)
            pref_matches += sum(
                1 for e in emp_entries if e.shift.name in preferred
            )

        preference_satisfaction = (pref_matches / total_assigned) if total_assigned else 0.0

        # Average shift utilisation across all shifts and days
        if coverage_stats:
            coverage_percentages = [stat['coverage_percentage'] for stat in coverage_stats if stat.get('coverage_percentage') is not None]
            avg_shift_utilisation = (sum(coverage_percentages) / len(coverage_percentages) / 100) if coverage_percentages else 0.0
        else:
            avg_shift_utilisation = 0.0

        # Robustness: expected extra understaff percentage from Monte Carlo absence simulation
        try:
            ea = EnhancedAnalytics(company, entries, employees, shifts)
            robustness = ea.absence_impact()
        except Exception:
            robustness = 0.0

        return {
            'monthly_stats': monthly_stats,
            'coverage_stats': coverage_stats,
            'constraint_violations': {
                'rest_period_violations': total_rest_violations,
                'total_violations':  total_rest_violations,
                'rest_period_violations_detailed': rest_violations_detailed
            },
            'fairness_metrics': {
                'gini_coefficient': gini,
                'hours_std_dev': hours_stdev,
                'hours_cv': hours_cv,
                'min_hours': min(employee_hours) if employee_hours else 0.0,
                'max_hours': max(employee_hours) if employee_hours else 0.0,
                'avg_hours': hours_mean,
                'jain_index': jain_index,
                'gini_overtime': gini_overtime,
                'variance_hours': variance_hours
            },
            'utilization': {
                'min': util_min,
                'max': util_max,
                'avg': util_avg,
                'by_contract': util_stats_by_contract
            },
            'average_shift_utilization': avg_shift_utilisation,
            'preference_satisfaction': preference_satisfaction,
            'robustness_extra_under_pct': robustness,
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

    def _calculate_statistics(self, values: List[float], confidence_level: float = 0.95) -> Dict[str, Any]:
        """Calculate mean, variance, and confidence interval for a list of values."""
        if not values:
            return {
                'mean': 0.0,
                'variance': 0.0,
                'std_dev': 0.0,
                'confidence_interval': (0.0, 0.0),
                'min': 0.0,
                'max': 0.0,
                'count': 0
            }
        
        values_array = np.array(values)
        mean = float(np.mean(values_array))
        
        # Calculate variance and standard deviation only if we have more than one value
        if len(values) > 1:
            variance = float(np.var(values_array, ddof=1))  # Sample variance
            std_dev = float(np.std(values_array, ddof=1))   # Sample standard deviation
            
            # Treat very small variances as zero (practically identical values)
            # This handles floating-point precision issues where values are essentially the same
            # Use relative threshold based on mean value
            relative_threshold = max(abs(mean) * 1e-10, 1e-10)
            if variance < relative_threshold:  # Threshold for "practically identical"
                variance = 0.0
                std_dev = 0.0
        else:
            variance = 0.0
            std_dev = 0.0
        
        # Ensure no NaN values
        if np.isnan(mean):
            mean = 0.0
        if np.isnan(variance):
            variance = 0.0
        if np.isnan(std_dev):
            std_dev = 0.0
        
        # Calculate confidence interval
        if len(values) > 1 and variance > 0:
            try:
                sem = stats.sem(values_array)
                if sem > relative_threshold:  # Only calculate if standard error is meaningfully positive
                    confidence_interval = stats.t.interval(
                        confidence_level, 
                        len(values) - 1, 
                        loc=mean, 
                        scale=sem
                    )
                    confidence_interval = (float(confidence_interval[0]), float(confidence_interval[1]))
                    # Check for NaN values in confidence interval
                    if np.isnan(confidence_interval[0]) or np.isnan(confidence_interval[1]):
                        confidence_interval = (mean, mean)
                else:
                    # Standard error is too small, treat as identical values
                    confidence_interval = (mean, mean)
            except (ValueError, RuntimeWarning):
                # Fallback if confidence interval calculation fails
                confidence_interval = (mean, mean)
        else:
            # If variance is 0 (all values identical) or only one value, use mean as interval
            confidence_interval = (mean, mean)
        
        min_val = float(np.min(values_array))
        max_val = float(np.max(values_array))
        
        # Ensure no NaN values in min/max
        if np.isnan(min_val):
            min_val = mean
        if np.isnan(max_val):
            max_val = mean
        
        return {
            'mean': mean,
            'variance': variance,
            'std_dev': std_dev,
            'confidence_interval': confidence_interval,
            'min': min_val,
            'max': max_val,
            'count': len(values)
        }

    def _calculate_nested_statistics(self, data: Dict[str, List[float]], confidence_level: float = 0.95) -> Dict[str, Any]:
        """Calculate statistics for nested data structures."""
        result = {}
        for key, values in data.items():
            if isinstance(values, list) and all(isinstance(v, (int, float)) for v in values):
                result[key] = self._calculate_statistics(values, confidence_level)
            elif isinstance(values, dict):
                result[key] = self._calculate_nested_statistics(values, confidence_level)
            else:
                result[key] = values
        return result

    def _calculate_kpi_statistics(self, kpi_list: List[Dict[str, Any]], confidence_level: float = 0.95) -> Dict[str, Any]:
        """Calculate statistics for KPI data across multiple runs."""
        if not kpi_list:
            return {}
        
        # Extract all numeric values from KPIs
        kpi_values = defaultdict(list)
        
        for kpis in kpi_list:
            if not kpis:
                continue
            self._extract_numeric_values(kpis, kpi_values)
        
        # Special handling for coverage_stats
        coverage_stats = self._calculate_coverage_statistics(kpi_list, confidence_level)
        
        # Calculate statistics for each metric
        result = {}
        for metric_name, values in kpi_values.items():
            if values:  # Only calculate if we have values
                # Debug: Print some examples of values that are causing issues
                if len(values) > 1 and any('fairness_metrics' in metric_name for _ in [1]):
                    unique_values = len(set(values))
                    if unique_values == 1:
                        self.stdout.write(f"DEBUG: {metric_name} has {len(values)} identical values: {values[0]}")
                    elif unique_values < len(values) * 0.1:  # Less than 10% unique values
                        self.stdout.write(f"DEBUG: {metric_name} has {unique_values} unique values out of {len(values)} total")
                
                result[metric_name] = self._calculate_statistics(values, confidence_level)
        
        # Add coverage statistics to result
        if coverage_stats:
            result['coverage_stats'] = coverage_stats
        
        return result

    def _calculate_coverage_statistics(self, kpi_list: List[Dict[str, Any]], confidence_level: float = 0.95) -> Dict[str, Any]:
        """Calculate statistics for coverage data across multiple runs."""
        if not kpi_list:
            return {}
        
        # Collect coverage data from all runs
        all_coverage_data = []
        for kpis in kpi_list:
            if kpis and 'coverage_stats' in kpis:
                all_coverage_data.append(kpis['coverage_stats'])
        
        if not all_coverage_data:
            return {}
        
        # Group coverage percentages by shift name
        shift_coverage_data = defaultdict(list)
        
        for coverage_stats in all_coverage_data:
            for shift_stat in coverage_stats:
                shift_name = shift_stat['shift']['name']
                coverage_percentage = shift_stat['coverage_percentage']
                shift_coverage_data[shift_name].append(coverage_percentage)
        
        # Calculate statistics for each shift
        result = {}
        for shift_name, coverage_values in shift_coverage_data.items():
            if coverage_values:
                result[shift_name] = self._calculate_statistics(coverage_values, confidence_level)
        
        return result

    def _extract_numeric_values(self, data: Any, kpi_values: Dict[str, List[float]], prefix: str = ""):
        """Recursively extract numeric values from nested KPI data."""
        if isinstance(data, dict):
            for key, value in data.items():
                new_prefix = f"{prefix}.{key}" if prefix else key
                self._extract_numeric_values(value, kpi_values, new_prefix)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                new_prefix = f"{prefix}[{i}]" if prefix else f"[{i}]"
                self._extract_numeric_values(item, kpi_values, new_prefix)
        elif isinstance(data, (int, float)):
            kpi_values[prefix].append(float(data))

    def _save_test_results(self, test_name: str, results: Dict, export_dir: str):
        test_dir = os.path.join(export_dir, test_name)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)

        results_file = os.path.join(test_dir, 'results.json')
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=4, default=str, allow_nan=False)

    def _generate_enhanced_test_graphs_with_analytics(self, test_name: str, results: Dict, export_dir: str, company):
        self.stdout.write(f"Generating graphs for {test_name}...")

        all_entries = ScheduleEntry.objects.filter(company=company)
        employees = list(Employee.objects.filter(company=company))
        shifts = list(Shift.objects.filter(company=company))

        analytics = EnhancedAnalytics(company, all_entries, employees, shifts)
        analytics.generate_algorithm_comparison_graphs(results, export_dir, test_name)

        self.stdout.write(self.style.SUCCESS(f"Generated enhanced graphs for {test_name}"))
