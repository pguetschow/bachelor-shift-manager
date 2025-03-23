import time
from datetime import date, timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from rostering_app.models import ScheduleEntry, Employee, ShiftType


class Command(BaseCommand):
    help = "Compare scheduling approaches by running existing scheduling commands and computing KPIs."

    def handle(self, *args, **options):
        methods = {
            'Linear': 'generate_schedule_linear',
            'Heuristic': 'generate_schedule_heuristic',
            'Genetic Algorithm': 'generate_schedule_genetic'
        }
        results = {}
        self.stdout.write("Comparing scheduling approaches for a 28-day period (2024-02-01 to 2024-02-28)...\n")

        for method_name, command_name in methods.items():
            # Clear previous schedule entries.
            ScheduleEntry.objects.all().delete()

            start_time = time.time()
            # Run the scheduling command (each exists in its own file)
            call_command(command_name, verbosity=0)
            runtime = time.time() - start_time

            kpis = self.compute_kpis()
            results[method_name] = {'runtime': runtime, 'kpis': kpis}
            self.stdout.write(self.style.SUCCESS(f"{method_name} method completed in {runtime:.2f} seconds.\n"))

        self.stdout.write("\n===== Comparison Results =====\n")
        for method, data in results.items():
            self.stdout.write(f"Method: {method}")
            self.stdout.write(f"  Runtime: {data['runtime']:.2f} seconds")
            kpis = data['kpis']
            self.stdout.write(f"  Total Hours Worked: {kpis['total_hours_worked']:.2f}")
            self.stdout.write(f"  Total Possible Hours: {kpis['total_possible_hours']:.2f}")
            self.stdout.write(f"  Max Possible Shift Hours: {kpis['max_possible_shift_hours']:.2f}")
            self.stdout.write(f"  Staff Hour Utilization: {kpis['staff_hour_utilization']:.2f}%")
            self.stdout.write(f"  Staff Maximum Hour Utilization: {kpis['staff_max_utilization']:.2f}%")
            self.stdout.write("  Per Employee KPIs:")
            for emp_name, emp_data in kpis['employees'].items():
                self.stdout.write(
                    f"    {emp_name}: Hours Worked = {emp_data['hours_worked']:.2f}, "
                    f"Utilization = {emp_data['utilization']:.2f}%"
                )
            self.stdout.write("\n")

    def compute_kpis(self):
        """
        Compute KPIs for the schedule over a 28-day period starting on 2024-02-01.
        For each employee:
          - Hours worked = sum(shift duration for each assignment)
          - Utilization = (hours worked / (max_hours_per_week * 4)) * 100
        Overall:
          - Total hours worked = sum(hours worked for all employees)
          - Total possible hours = sum(max_hours_per_week * 4 for each employee)
          - Max possible shift hours = sum(shift.get_duration() * shift.max_staff * 28 for all shifts)
          - Staff hour utilization = (total_hours_worked / total_possible_hours * 100)
          - Staff maximum hour utilization = (total_hours_worked / max_possible_shift_hours * 100)
        """
        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())
        start_date = date(2024, 2, 1)
        num_days = 28
        days = [start_date + timedelta(days=i) for i in range(num_days)]

        total_hours_worked = 0
        total_possible_hours = 0
        max_possible_shift_hours = 0
        employee_kpis = {}

        # Compute maximum possible shift hours across all shifts.
        for shift in shift_types:
            max_possible_shift_hours += shift.get_duration() * shift.max_staff * num_days

        for emp in employees:
            hours_worked = 0
            # Maximum hours available for the employee for 4 weeks.
            max_emp_hours = emp.max_hours_per_week * 4
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
