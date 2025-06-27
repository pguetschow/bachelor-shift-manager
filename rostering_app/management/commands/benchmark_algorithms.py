"""Benchmark different scheduling algorithms across multiple test cases."""
import json
import os
import time
import statistics
import traceback
from datetime import datetime, date, timedelta
from typing import Dict, List, Any

import matplotlib.pyplot as plt
import numpy as np
from django.core.management.base import BaseCommand
from django.db import transaction

from rostering_app.models import ScheduleEntry, Employee, ShiftType

# Import scheduling algorithms
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from scheduling_core.base import SchedulingProblem, Employee as CoreEmployee, ShiftType as CoreShiftType
from scheduling_core.linear_programming import LinearProgrammingScheduler
from scheduling_core.genetic_algorithm import GeneticAlgorithmScheduler
from scheduling_core.simulated_annealing import SimulatedAnnealingScheduler, CoolingSchedule


class Command(BaseCommand):
    help = "Benchmark scheduling algorithms across different company sizes"

    def handle(self, *args, **options):
        # Test configurations
        test_cases = [
            # {
            #     'name': 'small_company',
            #     'display_name': 'Kleines Unternehmen (10 MA, 2 Schichten)',
            #     'employee_fixture': 'rostering_app/fixtures/small_company/employees.json',
            #     'shift_fixture': 'rostering_app/fixtures/small_company/shift_types.json'
            # },
            {
                'name': 'old_company',
                'display_name': 'Altes Unternehmen (30 MA, 3 Schichten)',
                'employee_fixture': 'rostering_app/fixtures/old_company/employees.json',
                'shift_fixture': 'rostering_app/fixtures/old_company/shift_types.json'
            },
            # {
            #     'name': 'medium_company',
            #     'display_name': 'Mittleres Unternehmen (30 MA, 3 Schichten)',
            #     'employee_fixture': 'rostering_app/fixtures/medium_company/employees.json',
            #     'shift_fixture': 'rostering_app/fixtures/medium_company/shift_types.json'
            # },
            # {
            #     'name': 'large_company',
            #     'display_name': 'Großes Unternehmen (100 MA, 3 Schichten)',
            #     'employee_fixture': 'rostering_app/fixtures/large_company/employees.json',
            #     'shift_fixture': 'rostering_app/fixtures/large_company/shift_types.json'
            # }
        ]

        # Algorithm configurations
        algorithms = [
            LinearProgrammingScheduler(),
            # GeneticAlgorithmScheduler(population_size=30, generations=50),
            # SimulatedAnnealingScheduler(CoolingSchedule.EXPONENTIAL),
            # SimulatedAnnealingScheduler(CoolingSchedule.LINEAR),
            # SimulatedAnnealingScheduler(CoolingSchedule.LOGARITHMIC)
        ]

        # Create export directory
        export_dir = 'export'
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)

        # Run benchmarks for each test case
        all_results = {}
        
        for test_case in test_cases:
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"Benchmarking: {test_case['display_name']}")
            self.stdout.write(f"{'='*60}\n")
            
            # Load fixtures
            self._load_fixtures(test_case['employee_fixture'], test_case['shift_fixture'])
            
            # Create problem instance
            problem = self._create_problem()
            
            # Benchmark algorithms
            results = {}
            for algorithm in algorithms:
                self.stdout.write(f"\nTesting {algorithm.name}...")
                
                # Clear previous schedule
                ScheduleEntry.objects.all().delete()
                
                # Time the algorithm
                start_time = time.time()
                try:
                    entries = algorithm.solve(problem)
                    runtime = time.time() - start_time
                    
                    # Save to database
                    self._save_entries(entries)
                    
                    # Calculate KPIs
                    kpis = self._calculate_kpis()
                    
                    results[algorithm.name] = {
                        'runtime': runtime,
                        'kpis': kpis,
                        'status': 'success',
                        'entries_count': len(entries)
                    }
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"✓ {algorithm.name} completed in {runtime:.2f}s"
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
                    # Print the full traceback to the console
                    traceback.print_exc()

            
            # Store results
            all_results[test_case['name']] = {
                'display_name': test_case['display_name'],
                'results': results,
                'problem_size': {
                    'employees': len(problem.employees),
                    'shifts': len(problem.shift_types),
                    'days': (problem.end_date - problem.start_date).days + 1
                }
            }
            
            # Save results for this test case
            self._save_test_results(test_case['name'], results, export_dir)
            
            # Generate graphs for this test case
            self._generate_test_graphs(test_case['name'], results, export_dir)
        
        # Save overall results
        overall_file = os.path.join(export_dir, 'benchmark_results.json')
        with open(overall_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=4, default=str)
        
        # Generate comparison graphs across all test cases
        self._generate_comparison_graphs(all_results, export_dir)
        
        self.stdout.write(self.style.SUCCESS(
            f"\nBenchmark complete! Results saved to {export_dir}/"
        ))

    def _load_fixtures(self, employee_file: str, shift_file: str):
        """Load fixture data into database."""
        # Clear existing data
        with transaction.atomic():
            Employee.objects.all().delete()
            ShiftType.objects.all().delete()
            
            # Load employees
            with open(employee_file, 'r', encoding='utf-8') as f:
                employee_data = json.load(f)
                for item in employee_data:
                    Employee.objects.create(**item['fields'])
            
            # Load shift types
            with open(shift_file, 'r', encoding='utf-8') as f:
                shift_data = json.load(f)
                for item in shift_data:
                    ShiftType.objects.create(**item['fields'])

    def _create_problem(self) -> SchedulingProblem:
        """Create scheduling problem from database."""
        # Convert Django models to core data structures
        employees = []
        for emp in Employee.objects.all():
            employees.append(CoreEmployee(
                id=emp.id,
                name=emp.name,
                max_hours_per_week=emp.max_hours_per_week,
                absence_dates={datetime.strptime(d, '%Y-%m-%d').date() 
                             for d in emp.absences},
                preferred_shifts=emp.preferred_shifts
            ))
        
        shifts = []
        for shift in ShiftType.objects.all():
            shifts.append(CoreShiftType(
                id=shift.id,
                name=shift.name,
                start=shift.start,
                end=shift.end,
                min_staff=shift.min_staff,
                max_staff=shift.max_staff,
                duration=shift.get_duration()
            ))
        
        return SchedulingProblem(
            employees=employees,
            shift_types=shifts,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31)
        )

    def _save_entries(self, entries: List):
        """Save schedule entries to database."""
        with transaction.atomic():
            for entry in entries:
                ScheduleEntry.objects.create(
                    employee_id=entry.employee_id,
                    date=entry.date,
                    shift_type_id=entry.shift_id,
                    archived=False
                )

    def _calculate_kpis(self) -> Dict[str, Any]:
        """Calculate comprehensive KPIs for current schedule."""
        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())
        start_date = date(2025, 1, 1)
        end_date = date(2025, 12, 31)
        num_days = (end_date - start_date).days + 1
        
        # Initialize counters
        total_hours_worked = 0
        employee_hours = []
        employee_shift_counts = []
        shift_coverage_stats = {st.name: {'filled': 0, 'required': st.min_staff * num_days} 
                               for st in shift_types}
        
        # Per-employee metrics
        employee_stats = {}
        constraint_violations = 0
        
        for emp in employees:
            hours_worked = 0
            shifts_worked = 0
            weekly_hours = {}
            
            entries = ScheduleEntry.objects.filter(
                employee=emp, 
                date__gte=start_date, 
                date__lte=end_date,
                archived=False
            )
            
            for entry in entries:
                duration = entry.shift_type.get_duration()
                hours_worked += duration
                shifts_worked += 1
                
                # Track weekly hours
                week_key = entry.date.isocalendar()[:2]
                weekly_hours[week_key] = weekly_hours.get(week_key, 0) + duration
                
                # Update shift coverage
                shift_coverage_stats[entry.shift_type.name]['filled'] += 1
            
            # Check constraint violations
            violations = sum(1 for hours in weekly_hours.values() 
                           if hours > emp.max_hours_per_week)
            constraint_violations += violations
            
            # Store employee stats
            max_possible_hours = emp.max_hours_per_week * 52
            utilization = (hours_worked / max_possible_hours * 100) if max_possible_hours > 0 else 0
            
            employee_stats[emp.name] = {
                'hours_worked': hours_worked,
                'shifts_worked': shifts_worked,
                'utilization': utilization,
                'violations': violations
            }
            
            employee_hours.append(hours_worked)
            employee_shift_counts.append(shifts_worked)
            total_hours_worked += hours_worked
        
        # Calculate fairness metrics
        if employee_hours:
            hours_mean = statistics.mean(employee_hours)
            hours_stdev = statistics.stdev(employee_hours) if len(employee_hours) > 1 else 0
            hours_cv = (hours_stdev / hours_mean * 100) if hours_mean > 0 else 0
            gini = self._calculate_gini(employee_hours)
        else:
            hours_mean = hours_stdev = hours_cv = gini = 0
        
        # Calculate coverage rates
        coverage_rates = {}
        for shift_name, stats in shift_coverage_stats.items():
            coverage_rates[shift_name] = (stats['filled'] / stats['required'] * 100 
                                         if stats['required'] > 0 else 0)
        
        return {
            'total_hours_worked': total_hours_worked,
            'avg_hours_per_employee': hours_mean,
            'hours_std_dev': hours_stdev,
            'hours_cv': hours_cv,
            'gini_coefficient': gini,
            'constraint_violations': constraint_violations,
            'coverage_rates': coverage_rates,
            'min_hours': min(employee_hours) if employee_hours else 0,
            'max_hours': max(employee_hours) if employee_hours else 0
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

    def _generate_test_graphs(self, test_name: str, results: Dict, export_dir: str):
        """Generate graphs for a specific test case."""
        test_dir = os.path.join(export_dir, test_name)
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)
        
        # Filter successful results
        successful = {k: v for k, v in results.items() if v['status'] == 'success'}
        if not successful:
            return
        
        algorithms = list(successful.keys())
        
        # 1. Runtime comparison
        plt.figure(figsize=(10, 6))
        runtimes = [successful[alg]['runtime'] for alg in algorithms]
        bars = plt.bar(algorithms, runtimes)
        plt.title(f'Laufzeitvergleich - {test_name}')
        plt.xlabel('Algorithmus')
        plt.ylabel('Laufzeit (Sekunden)')
        plt.xticks(rotation=45, ha='right')
        
        # Add value labels
        for bar, runtime in zip(bars, runtimes):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{runtime:.1f}', ha='center', va='bottom')
        
        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'runtime_comparison.png'), dpi=300)
        plt.close()
        
        # 2. Fairness comparison
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        # Gini coefficient
        ginis = [successful[alg]['kpis']['gini_coefficient'] for alg in algorithms]
        bars1 = ax1.bar(algorithms, ginis)
        ax1.set_title('Gini-Koeffizient (niedriger = fairer)')
        ax1.set_ylabel('Gini-Koeffizient')
        ax1.set_xticks(range(len(algorithms)))
        ax1.set_xticklabels(algorithms, rotation=45, ha='right')
        
        for bar, val in zip(bars1, ginis):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{val:.3f}', ha='center', va='bottom')
        
        # Standard deviation
        stdevs = [successful[alg]['kpis']['hours_std_dev'] for alg in algorithms]
        bars2 = ax2.bar(algorithms, stdevs)
        ax2.set_title('Standardabweichung Arbeitsstunden')
        ax2.set_ylabel('Stunden')
        ax2.set_xticks(range(len(algorithms)))
        ax2.set_xticklabels(algorithms, rotation=45, ha='right')
        
        for bar, val in zip(bars2, stdevs):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{val:.0f}', ha='center', va='bottom')
        
        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'fairness_comparison.png'), dpi=300)
        plt.close()
        
        # 3. Constraint violations
        plt.figure(figsize=(10, 6))
        violations = [successful[alg]['kpis']['constraint_violations'] for alg in algorithms]
        bars = plt.bar(algorithms, violations, color=['green' if v == 0 else 'red' for v in violations])
        plt.title(f'Constraint-Verletzungen - {test_name}')
        plt.xlabel('Algorithmus')
        plt.ylabel('Anzahl Verletzungen')
        plt.xticks(rotation=45, ha='right')
        
        for bar, val in zip(bars, violations):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{val}', ha='center', va='bottom')
        
        plt.tight_layout()
        plt.savefig(os.path.join(test_dir, 'violations_comparison.png'), dpi=300)
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
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))
        
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
