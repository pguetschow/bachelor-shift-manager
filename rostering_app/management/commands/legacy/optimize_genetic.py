import os
import time
import json
import statistics
from datetime import date, timedelta

import matplotlib.pyplot as plt
from django.core.management import call_command
from django.core.management.base import BaseCommand
from rostering_app.models import ScheduleEntry, Employee, ShiftType


class Command(BaseCommand):
    help = "Run linear method baseline once, then run the genetic algorithm with parameters, and compare their KPIs."

    def add_arguments(self, parser):
        parser.add_argument(
            '--population_size',
            type=int,
            default=20,
            help="Population size for the genetic algorithm (default: 20)"
        )
        parser.add_argument(
            '--generations',
            type=int,
            default=50,
            help="Number of generations for the genetic algorithm (default: 50)"
        )
        parser.add_argument(
            '--mutation_rate',
            type=float,
            default=0.1,
            help="Mutation rate for the genetic algorithm (default: 0.1)"
        )

    def handle(self, *args, **options):
        pop_size = options.get("population_size")
        generations = options.get("generations")
        mutation_rate = options.get("mutation_rate")

        self.stdout.write("Running linear method baseline...\n")
        # Clear previous schedule entries and run the linear method.
        ScheduleEntry.objects.all().delete()
        t0 = time.time()
        call_command("generate_schedule_linear", verbosity=0)
        linear_runtime = time.time() - t0
        linear_kpis = self.compute_kpis()
        linear_variance = self.compute_employee_variance(linear_kpis['employees'])
        self.stdout.write(self.style.SUCCESS(
            f"Linear baseline: runtime={linear_runtime:.2f} sec, variance={linear_variance:.2f}\n"
        ))

        self.stdout.write("Running genetic algorithm with parameters:\n")
        self.stdout.write(f"  Population Size: {pop_size}\n")
        self.stdout.write(f"  Generations: {generations}\n")
        self.stdout.write(f"  Mutation Rate: {mutation_rate}\n")
        # Clear schedule entries and run the genetic algorithm.
        ScheduleEntry.objects.all().delete()
        t0 = time.time()
        # Pass parameters to the genetic algorithm command.
        call_command("generate_schedule_genetic",
                     population_size=pop_size,
                     generations=generations,
                     mutation_rate=mutation_rate,
                     verbosity=0)
        ga_runtime = time.time() - t0
        ga_kpis = self.compute_kpis()
        ga_variance = self.compute_employee_variance(ga_kpis['employees'])
        self.stdout.write(self.style.SUCCESS(
            f"Genetic algorithm: runtime={ga_runtime:.2f} sec, variance={ga_variance:.2f}\n"
        ))

        # Compare which method produced a schedule with lower employee variance.
        if ga_variance < linear_variance:
            self.stdout.write(
                self.style.SUCCESS("Genetic algorithm produced a fairer schedule than linear baseline.\n"))
        else:
            self.stdout.write(
                self.style.WARNING("Linear baseline produced a fairer schedule than genetic algorithm.\n"))

        # Save results as JSON and generate graphs.
        results = {
            "linear": {
                "runtime": linear_runtime,
                "kpis": linear_kpis,
                "variance": linear_variance
            },
            "genetic": {
                "runtime": ga_runtime,
                "kpis": ga_kpis,
                "variance": ga_variance,
                "parameters": {
                    "population_size": pop_size,
                    "generations": generations,
                    "mutation_rate": mutation_rate
                }
            }
        }
        export_dir = 'export'
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)
        json_file = os.path.join(export_dir, 'optimize_genetic_results.json')
        with open(json_file, 'w') as f:
            json.dump(results, f, indent=4, default=str)
        self.stdout.write(self.style.SUCCESS(f"Results saved as JSON to {json_file}\n"))
        self.generate_graphs(results, export_dir)
        self.stdout.write(self.style.SUCCESS("Graphs generated successfully.\n"))

    def compute_kpis(self):
        """
        Compute KPIs for a 28-day schedule starting on 2025-01-01.
        For each employee:
          - Hours worked: sum(shift duration for each assignment)
          - Utilization: (hours worked / (max_hours_per_week * 4)) * 100
        Overall:
          - Total hours worked: sum(hours worked for all employees)
          - Total possible hours: sum(max_hours_per_week * 4 for each employee)
          - Max possible shift hours: sum(shift.get_duration() * shift.max_staff * 28 for all shifts)
          - Staff hour utilization: (total_hours_worked / total_possible_hours * 100)
          - Staff maximum hour utilization: (total_hours_worked / max_possible_shift_hours * 100)
        """
        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())
        start_date = date(2025, 1, 1)
        num_days = 28
        days = [start_date + timedelta(days=i) for i in range(num_days)]

        total_hours_worked = 0
        total_possible_hours = 0
        max_possible_shift_hours = 0
        employee_kpis = {}

        for shift in shift_types:
            max_possible_shift_hours += shift.get_duration() * shift.max_staff * num_days

        for emp in employees:
            hours_worked = 0
            max_emp_hours = emp.max_hours_per_week * 4  # for 4 weeks
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

        return {
            'total_hours_worked': total_hours_worked,
            'total_possible_hours': total_possible_hours,
            'max_possible_shift_hours': max_possible_shift_hours,
            'staff_hour_utilization': staff_hour_utilization,
            'staff_max_utilization': staff_max_utilization,
            'employees': employee_kpis,
        }

    def compute_employee_variance(self, employee_kpis):
        """
        Compute the variance of hours worked across employees.
        Lower variance indicates a fairer schedule.
        """
        hours = [data['hours_worked'] for data in employee_kpis.values()]
        if len(hours) > 1:
            return statistics.variance(hours)
        return 0

    def generate_graphs(self, results, export_dir):
        methods = ['linear', 'genetic']
        # Graph 1: Variance Comparison.
        variances = [results[m]['variance'] for m in methods]
        plt.figure(figsize=(8, 6))
        plt.bar(methods, variances, color=['blue', 'green'])
        plt.title("Employee Hours Variance Comparison")
        plt.xlabel("Method")
        plt.ylabel("Variance of Hours Worked")
        plt.savefig(os.path.join(export_dir, 'variance_comparison_genetic.png'))
        plt.close()

        # Graph 2: Total Hours Worked Comparison.
        total_hours = [results[m]['kpis']['total_hours_worked'] for m in methods]
        plt.figure(figsize=(8, 6))
        plt.bar(methods, total_hours, color=['blue', 'green'])
        plt.title("Total Hours Worked Comparison")
        plt.xlabel("Method")
        plt.ylabel("Total Hours Worked")
        plt.savefig(os.path.join(export_dir, 'total_hours_comparison_genetic.png'))
        plt.close()

        # Graph 3: Staff Utilization Comparison.
        staff_util = [results[m]['kpis']['staff_hour_utilization'] for m in methods]
        staff_max_util = [results[m]['kpis']['staff_max_utilization'] for m in methods]
        x = range(len(methods))
        width = 0.35
        plt.figure(figsize=(8, 6))
        plt.bar([i - width / 2 for i in x], staff_util, width=width, label='Staff Hour Utilization', color='blue')
        plt.bar([i + width / 2 for i in x], staff_max_util, width=width, label='Staff Max Utilization', color='green')
        plt.xticks(x, methods)
        plt.title("Staff Utilization Comparison")
        plt.xlabel("Method")
        plt.ylabel("Utilization (%)")
        plt.legend()
        plt.savefig(os.path.join(export_dir, 'staff_utilization_comparison_genetic.png'))
        plt.close()
