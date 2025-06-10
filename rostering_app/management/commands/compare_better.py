import json
import os
import time
import statistics
from datetime import date, timedelta

import matplotlib.pyplot as plt
import numpy as np
from django.core.management import call_command
from django.core.management.base import BaseCommand

from rostering_app.models import ScheduleEntry, Employee, ShiftType


class Command(BaseCommand):
    help = "Compare scheduling approaches by running existing scheduling commands, computing comprehensive KPIs including fairness metrics, saving results as JSON, and generating graphs."

    def handle(self, *args, **options):
        methods = {
            'Linear monatlich rollierend': 'generate_schedule_linear_rolling',
            'Linear Jahresplan': 'generate_schedule_linear',
            'Linear Jahresplan v2': 'shift_scheduling_ilp',
            'Genetischer Algortihmus' : 'genetic_algorithm_scheduler',
            'Simulated Annealing' : 'simulated_annealing_scheduler',
            # 'Heuristic (Greedy)': 'generate_schedule_heuristic',
            # 'Genetic Algorithm': 'generate_schedule_genetic',
        }
        results = {}
        self.stdout.write("Comparing scheduling approaches...\n")

        for method_name, command_name in methods.items():
            # Clear previous schedule entries.
            ScheduleEntry.objects.all().delete()

            start_time = time.time()
            try:
                # Call the scheduling command (each command exists in its own file)
                call_command(command_name, verbosity=0)
                runtime = time.time() - start_time
                
                kpis = self.compute_comprehensive_kpis()
                results[method_name] = {
                    'runtime': runtime, 
                    'kpis': kpis,
                    'status': 'success'
                }
                self.stdout.write(self.style.SUCCESS(
                    f"{method_name} method completed in {runtime:.2f} seconds.\n"
                ))
            except Exception as e:
                runtime = time.time() - start_time
                results[method_name] = {
                    'runtime': runtime,
                    'kpis': None,
                    'status': 'failed',
                    'error': str(e)
                }
                self.stdout.write(self.style.ERROR(
                    f"{method_name} method failed after {runtime:.2f} seconds: {str(e)}\n"
                ))

        # Print comprehensive comparison results.
        self.print_comparison_results(results)

        # Save the results as JSON.
        export_dir = 'export'
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)
        json_file = os.path.join(export_dir, 'schedule_comparison.json')
        with open(json_file, 'w') as f:
            json.dump(results, f, indent=4, default=str)
        self.stdout.write(self.style.SUCCESS(f"Comparison results saved as JSON to {json_file}"))

        # Generate comprehensive graphs.
        successful_results = {k: v for k, v in results.items() if v['status'] == 'success'}
        if successful_results:
            self.generate_comprehensive_graphs(successful_results, export_dir)
            self.stdout.write(self.style.SUCCESS("Graphs generated successfully."))
        else:
            self.stdout.write(self.style.WARNING("No successful results to generate graphs."))

    def compute_comprehensive_kpis(self):
        """
        Compute comprehensive KPIs including fairness metrics for the schedule over the full year 2025.
        """
        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())
        start_date = date(2025, 1, 1)
        end_date = date(2025, 12, 31)
        num_days = (end_date - start_date).days + 1
        days = [start_date + timedelta(days=i) for i in range(num_days)]

        # Basic totals
        total_hours_worked = 0
        total_possible_hours = 0
        max_possible_shift_hours = 0
        min_possible_shift_hours = 0
        employee_kpis = {}
        
        # Data for fairness calculations
        employee_hours = []
        employee_utilizations = []
        employee_shift_counts = []

        # Compute shift coverage statistics
        shift_coverage_stats = {}
        for shift in shift_types:
            shift_coverage_stats[shift.name] = {
                'total_slots': 0,
                'filled_slots': 0,
                'min_required': shift.min_staff * num_days,
                'max_possible': shift.max_staff * num_days
            }

        # Compute maximum and minimum possible shift hours across all shifts over the full year.
        for shift in shift_types:
            max_possible_shift_hours += shift.get_duration() * shift.max_staff * num_days
            min_possible_shift_hours += shift.get_duration() * shift.min_staff * num_days

        weeks = 52  # Full year
        
        # Calculate per-employee metrics
        for emp in employees:
            hours_worked = 0
            shifts_worked = 0
            max_emp_hours = emp.max_hours_per_week * weeks
            
            # Weekly hours tracking for constraint violations
            weekly_hours = {}
            
            entries = ScheduleEntry.objects.filter(employee=emp, date__in=days, archived=False)
            for entry in entries:
                hours_worked += entry.shift_type.get_duration()
                shifts_worked += 1
                
                # Track weekly hours
                iso_year, iso_week, _ = entry.date.isocalendar()
                week_key = (iso_year, iso_week)
                if week_key not in weekly_hours:
                    weekly_hours[week_key] = 0
                weekly_hours[week_key] += entry.shift_type.get_duration()
                
                # Update shift coverage
                shift_name = entry.shift_type.name
                shift_coverage_stats[shift_name]['filled_slots'] += 1

            # Calculate constraint violations
            weekly_violations = sum(1 for hours in weekly_hours.values() 
                                  if hours > emp.max_hours_per_week)
            
            utilization = (hours_worked / max_emp_hours * 100) if max_emp_hours > 0 else 0
            
            employee_kpis[emp.name] = {
                'hours_worked': hours_worked,
                'shifts_worked': shifts_worked,
                'utilization': utilization,
                'max_emp_hours': max_emp_hours,
                'weekly_violations': weekly_violations,
                'avg_weekly_hours': hours_worked / weeks,
                'max_weekly_hours': max(weekly_hours.values()) if weekly_hours else 0
            }
            
            # Collect data for fairness calculations
            employee_hours.append(hours_worked)
            employee_utilizations.append(utilization)
            employee_shift_counts.append(shifts_worked)
            
            total_hours_worked += hours_worked
            total_possible_hours += max_emp_hours

        # Calculate shift coverage percentages
        for shift_name, stats in shift_coverage_stats.items():
            stats['coverage_rate'] = (stats['filled_slots'] / stats['max_possible'] * 100) if stats['max_possible'] > 0 else 0
            stats['min_coverage_rate'] = (stats['filled_slots'] / stats['min_required'] * 100) if stats['min_required'] > 0 else 0

        # Calculate fairness metrics
        fairness_metrics = self.calculate_fairness_metrics(
            employee_hours, employee_utilizations, employee_shift_counts
        )

        # Calculate overall utilization metrics
        staff_hour_utilization = (total_hours_worked / total_possible_hours * 100) if total_possible_hours > 0 else 0
        staff_max_utilization = (total_hours_worked / max_possible_shift_hours * 100) if max_possible_shift_hours > 0 else 0
        staff_min_utilization = (total_hours_worked / min_possible_shift_hours * 100) if min_possible_shift_hours > 0 else 0

        # Count total constraint violations
        total_weekly_violations = sum(emp['weekly_violations'] for emp in employee_kpis.values())

        return {
            # Basic metrics
            'total_hours_worked': total_hours_worked,
            'total_possible_hours': total_possible_hours,
            'max_possible_shift_hours': max_possible_shift_hours,
            'min_possible_shift_hours': min_possible_shift_hours,
            'staff_hour_utilization': staff_hour_utilization,
            'staff_min_utilization': staff_min_utilization,
            'staff_max_utilization': staff_max_utilization,
            
            # Fairness metrics
            'fairness': fairness_metrics,
            
            # Constraint violations
            'constraint_violations': {
                'total_weekly_violations': total_weekly_violations,
                'employees_with_violations': sum(1 for emp in employee_kpis.values() if emp['weekly_violations'] > 0)
            },
            
            # Shift coverage
            'shift_coverage': shift_coverage_stats,
            
            # Employee details
            'employees': employee_kpis,
            
            # Summary statistics
            'summary': {
                'total_employees': len(employees),
                'total_shifts_assigned': sum(emp['shifts_worked'] for emp in employee_kpis.values()),
                'avg_hours_per_employee': statistics.mean(employee_hours) if employee_hours else 0,
                'avg_shifts_per_employee': statistics.mean(employee_shift_counts) if employee_shift_counts else 0
            }
        }

    def calculate_fairness_metrics(self, employee_hours, employee_utilizations, employee_shift_counts):
        """Calculate comprehensive fairness metrics."""
        if not employee_hours:
            return {}
            
        # Hours-based fairness
        hours_mean = statistics.mean(employee_hours)
        hours_stdev = statistics.stdev(employee_hours) if len(employee_hours) > 1 else 0
        hours_cv = (hours_stdev / hours_mean * 100) if hours_mean > 0 else 0  # Coefficient of variation
        hours_range = max(employee_hours) - min(employee_hours)
        
        # Utilization-based fairness
        util_mean = statistics.mean(employee_utilizations)
        util_stdev = statistics.stdev(employee_utilizations) if len(employee_utilizations) > 1 else 0
        util_cv = (util_stdev / util_mean * 100) if util_mean > 0 else 0
        util_range = max(employee_utilizations) - min(employee_utilizations)
        
        # Shift count fairness
        shifts_mean = statistics.mean(employee_shift_counts)
        shifts_stdev = statistics.stdev(employee_shift_counts) if len(employee_shift_counts) > 1 else 0
        shifts_cv = (shifts_stdev / shifts_mean * 100) if shifts_mean > 0 else 0
        shifts_range = max(employee_shift_counts) - min(employee_shift_counts)
        
        # Gini coefficient for hours (inequality measure)
        gini_hours = self.calculate_gini_coefficient(employee_hours)
        
        # Overall fairness score (lower is better)
        # Combines normalized CV of hours and utilization
        fairness_score = (hours_cv + util_cv) / 2
        
        return {
            'hours': {
                'mean': hours_mean,
                'std_dev': hours_stdev,
                'coefficient_of_variation': hours_cv,
                'range': hours_range,
                'min': min(employee_hours),
                'max': max(employee_hours),
                'gini_coefficient': gini_hours
            },
            'utilization': {
                'mean': util_mean,
                'std_dev': util_stdev,
                'coefficient_of_variation': util_cv,
                'range': util_range,
                'min': min(employee_utilizations),
                'max': max(employee_utilizations)
            },
            'shifts': {
                'mean': shifts_mean,
                'std_dev': shifts_stdev,
                'coefficient_of_variation': shifts_cv,
                'range': shifts_range,
                'min': min(employee_shift_counts),
                'max': max(employee_shift_counts)
            },
            'overall_fairness_score': fairness_score
        }

    def calculate_gini_coefficient(self, values):
        """Calculate Gini coefficient (0 = perfect equality, 1 = perfect inequality)."""
        if not values or len(values) == 1:
            return 0
        
        sorted_values = sorted(values)
        n = len(values)
        cumulative_sum = sum((i + 1) * val for i, val in enumerate(sorted_values))
        return (2 * cumulative_sum) / (n * sum(values)) - (n + 1) / n

    def print_comparison_results(self, results):
        """Print comprehensive comparison results."""
        self.stdout.write("\n" + "="*60)
        self.stdout.write("           COMPREHENSIVE COMPARISON RESULTS")
        self.stdout.write("="*60 + "\n")
        
        for method, data in results.items():
            self.stdout.write(f"📊 Method: {method}")
            self.stdout.write(f"   ⏱️  Runtime: {data['runtime']:.2f} seconds")
            
            if data['status'] != 'success':
                self.stdout.write(f"   ❌ Status: {data['status']}")
                if 'error' in data:
                    self.stdout.write(f"   🚫 Error: {data['error']}")
                self.stdout.write("")
                continue
                
            kpis = data['kpis']
            
            # Basic metrics
            self.stdout.write(f"   📈 Total Hours Worked: {kpis['total_hours_worked']:.1f}")
            self.stdout.write(f"   📊 Staff Utilization: {kpis['staff_hour_utilization']:.1f}%")
            self.stdout.write(f"   🎯 Coverage (Min/Max): {kpis['staff_min_utilization']:.1f}% / {kpis['staff_max_utilization']:.1f}%")
            
            # Fairness metrics
            fairness = kpis['fairness']
            self.stdout.write(f"   ⚖️  Fairness Score: {fairness['overall_fairness_score']:.2f} (lower is better)")
            self.stdout.write(f"   📏 Hours Range: {fairness['hours']['min']:.1f} - {fairness['hours']['max']:.1f} ({fairness['hours']['range']:.1f})")
            self.stdout.write(f"   📐 Hours Std Dev: {fairness['hours']['std_dev']:.2f}")
            self.stdout.write(f"   🔢 Gini Coefficient: {fairness['hours']['gini_coefficient']:.3f}")
            
            # Constraint violations
            violations = kpis['constraint_violations']
            self.stdout.write(f"   ⚠️  Weekly Violations: {violations['total_weekly_violations']} ({violations['employees_with_violations']} employees)")
            
            self.stdout.write("")

    def generate_comprehensive_graphs(self, results, export_dir):
        """Generate comprehensive comparison graphs."""
        methods = list(results.keys())

        # Set up the plotting style
        plt.style.use('default')
        colors = plt.cm.Set3(np.linspace(0, 1, len(methods)))

        # Graph 1: Runtime Comparison
        self.create_bar_chart(
            methods,
            [results[m]['runtime'] for m in methods],
            "Vergleich der Laufzeiten",
            "Methode", "Laufzeit (Sekunden)",
            colors, export_dir, 'runtime_comparison.png'
        )

        # Graph 2: Utilization Comparison (Multiple bars)
        staff_util = [results[m]['kpis']['staff_hour_utilization'] for m in methods]
        staff_min_util = [results[m]['kpis']['staff_min_utilization'] for m in methods]
        staff_max_util = [results[m]['kpis']['staff_max_utilization'] for m in methods]

        self.create_grouped_bar_chart(
            methods,
            [staff_util, staff_min_util, staff_max_util],
            ['Auslastung', 'Mindestabdeckung', 'Maximale Abdeckung'],
            "Vergleich der Personalauslastung",
            "Methode", "Auslastung (%)",
            export_dir, 'staff_utilization.png'
        )

        # Graph 3: Fairness Comparison
        fairness_scores = [results[m]['kpis']['fairness']['overall_fairness_score'] for m in methods]
        hours_std_dev = [results[m]['kpis']['fairness']['hours']['std_dev'] for m in methods]
        gini_coeffs = [results[m]['kpis']['fairness']['hours']['gini_coefficient'] for m in methods]

        self.create_grouped_bar_chart(
            methods,
            [fairness_scores, hours_std_dev, [g * 100 for g in gini_coeffs]],  # Scale Gini for visibility
            ['Fairness-Score', 'Standardabweichung Stunden', 'Gini-Koeffizient (×100)'],
            "Vergleich der Fairness-Metriken (niedriger ist besser)",
            "Methode", "Wert",
            export_dir, 'fairness_comparison.png'
        )

        # Graph 4: Total Hours and Violations
        total_hours = [results[m]['kpis']['total_hours_worked'] for m in methods]
        violations = [results[m]['kpis']['constraint_violations']['total_weekly_violations'] for m in methods]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

        # Total hours subplot
        bars1 = ax1.bar(methods, total_hours, color=colors)
        ax1.set_title("Gesamtarbeitsstunden")
        ax1.set_ylabel("Stunden")
        self.add_bar_labels(ax1, bars1)

        # Violations subplot
        bars2 = ax2.bar(methods, violations, color=['red' if v > 0 else 'green' for v in violations])
        ax2.set_title("Verstöße gegen Wochenarbeitszeit")
        ax2.set_ylabel("Anzahl der Verstöße")
        self.add_bar_labels(ax2, bars2)

        plt.tight_layout()
        plt.savefig(os.path.join(export_dir, 'hours_and_violations.png'), dpi=300, bbox_inches='tight')
        plt.close()

        # Graph 5: Employee Distribution (Box plots for first method)
        if methods:
            first_method = methods[0]
            employee_data = results[first_method]['kpis']['employees']
            hours_data = [emp['hours_worked'] for emp in employee_data.values()]
            util_data = [emp['utilization'] for emp in employee_data.values()]

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6))

            ax1.boxplot(hours_data)
            ax1.set_title(f"Verteilung der Arbeitsstunden – {first_method}")
            ax1.set_ylabel("Geleistete Stunden")

            ax2.boxplot(util_data)
            ax2.set_title(f"Verteilung der Auslastung – {first_method}")
            ax2.set_ylabel("Auslastung (%)")

            plt.tight_layout()
            plt.savefig(os.path.join(export_dir, 'employee_distribution.png'), dpi=300, bbox_inches='tight')
            plt.close()

    def create_bar_chart(self, x_labels, values, title, xlabel, ylabel, colors, export_dir, filename):
        """Create a single bar chart."""
        plt.figure(figsize=(10, 6))
        bars = plt.bar(x_labels, values, color=colors)
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        self.add_bar_labels(plt.gca(), bars)
        plt.tight_layout()
        plt.savefig(os.path.join(export_dir, filename), dpi=300, bbox_inches='tight')
        plt.close()

    def create_grouped_bar_chart(self, x_labels, data_series, series_labels, title, xlabel, ylabel, export_dir, filename):
        """Create a grouped bar chart."""
        x = np.arange(len(x_labels))
        width = 0.8 / len(data_series)
        
        plt.figure(figsize=(12, 8))
        
        for i, (data, label) in enumerate(zip(data_series, series_labels)):
            offset = (i - len(data_series)/2 + 0.5) * width
            bars = plt.bar(x + offset, data, width, label=label)
            self.add_bar_labels(plt.gca(), bars, fontsize=8)
        
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xticks(x, x_labels)
        plt.legend()
        
        if 'Utilization' in title:
            plt.axhline(y=100, color='gray', linestyle='--', alpha=0.7, label='100%')
        
        plt.tight_layout()
        plt.savefig(os.path.join(export_dir, filename), dpi=300, bbox_inches='tight')
        plt.close()

    def add_bar_labels(self, ax, bars, fontsize=9):
        """Add value labels on top of bars."""
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height:.1f}' if height >= 1 else f'{height:.2f}',
                   ha='center', va='bottom', fontsize=fontsize)
