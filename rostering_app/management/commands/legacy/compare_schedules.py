import json
import os
import time
from datetime import date, timedelta

import matplotlib.pyplot as plt
from django.core.management import call_command
from django.core.management.base import BaseCommand

from rostering_app.models import ScheduleEntry, Employee, ShiftType


class Command(BaseCommand):
    help = "Compare scheduling approaches by running existing scheduling commands, computing KPIs on a yearly basis, saving results as JSON, and generating graphs."

    def handle(self, *args, **options):
        methods = {
            'Linear': 'generate_schedule_linear',
            'Linear Claude': 'shift_scheduling_ilp',
            # 'Linear Better': 'generate_schedule_linear_better',
            # 'Heuristic (Greedy)': 'generate_schedule_heuristic',
            # 'Genetic Algorithm': 'generate_schedule_genetic',
            'genetic_algorithm_scheduler' : 'genetic_algorithm_scheduler',
            'simulated_annealing_scheduler' : 'simulated_annealing_scheduler',
        }
        results = {}
        self.stdout.write("Comparing scheduling approaches...\n")

        for method_name, command_name in methods.items():
            # Clear previous schedule entries.
            ScheduleEntry.objects.all().delete()

            start_time = time.time()
            # Call the scheduling command (each command exists in its own file)
            call_command(command_name, verbosity=0)
            runtime = time.time() - start_time

            kpis = self.compute_kpis()
            results[method_name] = {'runtime': runtime, 'kpis': kpis}
            self.stdout.write(self.style.SUCCESS(f"{method_name} method completed in {runtime:.2f} seconds.\n"))

        # Print comparison results.
        self.stdout.write("\n===== Comparison Results =====\n")
        for method, data in results.items():
            self.stdout.write(f"Method: {method}")
            self.stdout.write(f"  Runtime: {data['runtime']:.2f} seconds")
            kpis = data['kpis']
            self.stdout.write(f"  Total Hours Worked: {kpis['total_hours_worked']:.2f}")
            self.stdout.write(f"  Total Possible Hours: {kpis['total_possible_hours']:.2f}")
            self.stdout.write(f"  Max Possible Shift Hours: {kpis['max_possible_shift_hours']:.2f}")
            self.stdout.write(f"  Min Possible Shift Hours: {kpis['min_possible_shift_hours']:.2f}")
            self.stdout.write(f"  Staff Hour Utilization: {kpis['staff_hour_utilization']:.2f}%")
            self.stdout.write(f"  Staff Minimum Hour Utilization: {kpis['staff_min_utilization']:.2f}%")
            self.stdout.write(f"  Staff Maximum Hour Utilization: {kpis['staff_max_utilization']:.2f}%")
            self.stdout.write("  Per Employee KPIs:")
            for emp_name, emp_data in kpis['employees'].items():
                self.stdout.write(
                    f"    {emp_name}: Hours Worked = {emp_data['hours_worked']:.2f}, "
                    f"Utilization = {emp_data['utilization']:.2f}%"
                )
            self.stdout.write("\n")

        # Save the results as JSON.
        export_dir = 'export'
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)
        json_file = os.path.join(export_dir, 'schedule_comparison.json')
        with open(json_file, 'w') as f:
            json.dump(results, f, indent=4, default=str)
        self.stdout.write(self.style.SUCCESS(f"Comparison results saved as JSON to {json_file}"))

        # Generate graphs.
        self.generate_graphs(results, export_dir)
        self.stdout.write(self.style.SUCCESS("Graphs generated successfully."))

    def compute_kpis(self):
        """
        Compute KPIs for the schedule over the full year 2025 (2025-01-01 to 2025-12-31).
        For each employee:
          - Hours worked = sum(shift duration for each assignment)
          - Utilization = (hours worked / (max_hours_per_week * number_of_weeks)) * 100
        Overall:
          - Total hours worked = sum(hours worked for all employees)
          - Total possible hours = sum(max_hours_per_week * (num_days/7) for each employee)
          - Max possible shift hours = sum(shift.get_duration() * shift.max_staff * num_days for all shifts)
          - Min possible shift hours = sum(shift.get_duration() * shift.min_staff * num_days for all shifts)
          - Staff hour utilization = (total_hours_worked / total_possible_hours * 100)
          - Staff minimum hour utilization = (total_hours_worked / min_possible_shift_hours * 100)
          - Staff maximum hour utilization = (total_hours_worked / max_possible_shift_hours * 100)
        """
        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())
        start_date = date(2025, 1, 1)
        end_date = date(2025, 12, 31)
        num_days = (end_date - start_date).days + 1
        days = [start_date + timedelta(days=i) for i in range(num_days)]

        total_hours_worked = 0
        total_possible_hours = 0
        max_possible_shift_hours = 0
        min_possible_shift_hours = 0
        employee_kpis = {}

        # Compute maximum and minimum possible shift hours across all shifts over the full year.
        for shift in shift_types:
            max_possible_shift_hours += shift.get_duration() * shift.max_staff * num_days
            min_possible_shift_hours += shift.get_duration() * shift.min_staff * num_days

        # Total number of weeks in the period.
        # weeks = round(num_days / 7.0)
        weeks = 52
        for emp in employees:
            hours_worked = 0
            # Maximum hours available for the employee for the full year.
            max_emp_hours = emp.max_hours_per_week * weeks
            entries = ScheduleEntry.objects.filter(employee=emp, date__in=days, archived=False)
            for entry in entries:
                hours_worked += entry.shift_type.get_duration()
            utilization = (hours_worked / max_emp_hours * 100) if max_emp_hours > 0 else 0
            employee_kpis[emp.name] = {
                'hours_worked': hours_worked,
                'utilization': utilization,
                'max_emp_hours': max_emp_hours,
            }
            total_hours_worked += hours_worked
            total_possible_hours += max_emp_hours

        staff_hour_utilization = (total_hours_worked / total_possible_hours * 100) if total_possible_hours > 0 else 0
        staff_max_utilization = (
                    total_hours_worked / max_possible_shift_hours * 100) if max_possible_shift_hours > 0 else 0
        staff_min_utilization = (
                    total_hours_worked / min_possible_shift_hours * 100) if min_possible_shift_hours > 0 else 0

        return {
            'total_hours_worked': total_hours_worked,
            'total_possible_hours': total_possible_hours,
            'max_possible_shift_hours': max_possible_shift_hours,
            'min_possible_shift_hours': min_possible_shift_hours,
            'staff_hour_utilization': staff_hour_utilization,
            'staff_min_utilization': staff_min_utilization,
            'staff_max_utilization': staff_max_utilization,
            'employees': employee_kpis,
        }

    def generate_graphs(self, results, export_dir):
        methods = list(results.keys())

        # Graph 1: Runtime Comparison.
        runtimes = [results[m]['runtime'] for m in methods]
        plt.figure(figsize=(8, 6))
        bars = plt.bar(methods, runtimes, color=['blue', 'green', 'orange'])
        plt.title("Runtime Comparison")
        plt.xlabel("Method")
        plt.ylabel("Runtime (seconds)")
        # Add labels above bars.
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width() / 2, height,
                     f'{height:.2f}', ha='center', va='bottom')
        plt.savefig(os.path.join(export_dir, 'runtime_comparison.png'))
        plt.close()

        # Graph 2: Total Hours Worked Comparison.
        total_hours = [results[m]['kpis']['total_hours_worked'] for m in methods]
        plt.figure(figsize=(8, 6))
        bars = plt.bar(methods, total_hours, color=['blue', 'green', 'orange'])
        plt.title("Total Hours Worked Comparison")
        plt.xlabel("Method")
        plt.ylabel("Total Hours Worked")
        # Add labels above bars.
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width() / 2, height,
                     f'{height:.2f}', ha='center', va='bottom')
        plt.savefig(os.path.join(export_dir, 'total_hours_worked.png'))
        plt.close()

        # Graph 3: Staff Utilization Comparison.
        staff_util = [results[m]['kpis']['staff_hour_utilization'] for m in methods]
        staff_min_util = [results[m]['kpis']['staff_min_utilization'] for m in methods]
        staff_max_util = [results[m]['kpis']['staff_max_utilization'] for m in methods]
        x = range(len(methods))
        width = 0.25  # Adjusted for three bars per group.

        plt.figure(figsize=(8, 6))
        bars1 = plt.bar([i - width for i in x], staff_util, width=width, label='Staff Hour Utilization (Worked vs Workforce Potential)', color='blue')
        bars2 = plt.bar(x, staff_min_util, width=width, label='Staff Min Hour Utilization', color='red')
        bars3 = plt.bar([i + width for i in x], staff_max_util, width=width, label='Staff Max Hour Utilization',
                        color='green')
        plt.xticks(x, methods)
        plt.title("Staff Utilization Comparison")
        plt.xlabel("Method")
        plt.ylabel("Utilization (%)")

        # Add horizontal dotted line for 100% utilization.
        plt.axhline(y=100, color='gray', linestyle='--', linewidth=1)

        # Add labels above each bar in all three groups.
        for bars in [bars1, bars2, bars3]:
            for bar in bars:
                height = bar.get_height()
                plt.text(bar.get_x() + bar.get_width() / 2, height,
                         f'{height:.2f}%', ha='center', va='bottom', fontsize=8)

        plt.legend()
        plt.savefig(os.path.join(export_dir, 'staff_utilization.png'))
        plt.close()
