from datetime import datetime, timedelta
from collections import defaultdict
import json

from django.core.management.base import BaseCommand
from pulp import LpProblem, LpVariable, lpSum, LpMinimize, LpBinary, PULP_CBC_CMD

from rostering_app.models import Employee, ShiftType, ScheduleEntry


class Command(BaseCommand):
    help = 'Generate employee rostering schedule for a full year with weekly constraints and compute KPIs and export to JSON'

    def handle(self, *args, **kwargs):
        # Archive previous schedule entries.
        ScheduleEntry.objects.filter(archived=False).update(archived=True)

        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())

        # Define scheduling period: full year from 2025-01-01 to 2025-12-31.
        start_date = datetime.strptime('2025-01-01', '%Y-%m-%d').date()
        end_date = datetime.strptime('2025-12-31', '%Y-%m-%d').date()
        num_days = (end_date - start_date).days + 1

        # Build list of days (each day offers all shift types).
        days = []
        for i in range(num_days):
            day_date = start_date + timedelta(days=i)
            days.append({'date': day_date, 'shifts': shift_types})

        # Group days by ISO week for weekly constraints.
        weeks = defaultdict(list)
        for day in days:
            iso_year, iso_week, _ = day['date'].isocalendar()
            weeks[(iso_year, iso_week)].append(day)

        # Setup the optimization problem.
        problem = LpProblem("Employee_Rostering_Year", LpMinimize)
        variables = {}

        # Create decision variables for each employee, day, and shift.
        for employee in employees:
            for day in days:
                for shift in day['shifts']:
                    key = (employee.id, day['date'], shift.id)
                    variables[key] = LpVariable(
                        f"x_{employee.id}_{day['date']}_{shift.id}",
                        0, 1, LpBinary
                    )

        # Helper variables for fairness and tracking
        # Variables for total hours per employee
        employee_total_hours = {}
        for employee in employees:
            employee_total_hours[employee.id] = LpVariable(
                f"total_hours_{employee.id}", 0
            )

        # Variables for overtime/undertime tracking
        employee_overtime = {}
        employee_undertime = {}
        for employee in employees:
            employee_overtime[employee.id] = LpVariable(
                f"overtime_{employee.id}", 0
            )
            employee_undertime[employee.id] = LpVariable(
                f"undertime_{employee.id}", 0
            )

        # Calculate expected average hours per employee based on MAXIMUM staffing
        total_possible_hours = 0
        total_capacity_hours = 0

        for day in days:
            for shift in shift_types:
                # Prefer maximum staffing
                total_possible_hours += shift.get_duration() * shift.max_staff

        # Calculate total capacity of all employees
        for employee in employees:
            total_capacity_hours += employee.max_hours_per_week * 52  # 52 weeks per year

        # Target hours: minimum of what's possible and what employees can handle
        target_total_hours = min(total_possible_hours, total_capacity_hours)
        average_hours_per_employee = target_total_hours / len(employees) if employees else 0

        # CONSTRAINTS

        # 1. Abwesenheiten berücksichtigen
        for employee in employees:
            absence_dates = [datetime.strptime(date_str, '%Y-%m-%d').date()
                             for date_str in employee.absences]
            for absence_date in absence_dates:
                if start_date <= absence_date <= end_date:
                    for shift in shift_types:
                        if (employee.id, absence_date, shift.id) in variables:
                            problem += variables[(employee.id, absence_date, shift.id)] == 0

        # 2. Jeder Mitarbeiter darf nur eine Schicht pro Tag arbeiten
        for employee in employees:
            for day in days:
                day_shifts = []
                for shift in day['shifts']:
                    key = (employee.id, day['date'], shift.id)
                    if key in variables:
                        day_shifts.append(variables[key])
                if day_shifts:
                    problem += lpSum(day_shifts) <= 1

        # 3. Mindest- und Maximalbesetzung pro Schicht einhalten
        for day in days:
            for shift in day['shifts']:
                shift_assignments = []
                for employee in employees:
                    key = (employee.id, day['date'], shift.id)
                    if key in variables:
                        shift_assignments.append(variables[key])

                if shift_assignments:
                    # Mindestbesetzung
                    problem += lpSum(shift_assignments) >= shift.min_staff
                    # Maximalbesetzung
                    problem += lpSum(shift_assignments) <= shift.max_staff

        # 4. Maximale wöchentliche Arbeitszeit einhalten
        for employee in employees:
            for week_key, week_days in weeks.items():
                weekly_hours = []
                for day in week_days:
                    for shift in day['shifts']:
                        key = (employee.id, day['date'], shift.id)
                        if key in variables:
                            weekly_hours.append(
                                variables[key] * shift.get_duration()
                            )

                if weekly_hours:
                    problem += lpSum(weekly_hours) <= employee.max_hours_per_week

        # 5. 11-Stunden-Pause zwischen Schichten
        for employee in employees:
            for i, day in enumerate(days[:-1]):  # Alle Tage außer dem letzten
                next_day = days[i + 1]

                # Für jede Kombination von heutiger und morgiger Schicht prüfen
                for today_shift in day['shifts']:
                    for tomorrow_shift in next_day['shifts']:
                        # Berechne die Zeit zwischen Schichtende heute und Schichtbeginn morgen
                        today_end = datetime.combine(day['date'], today_shift.end)
                        tomorrow_start = datetime.combine(next_day['date'], tomorrow_shift.start)

                        # Wenn Schicht über Mitternacht geht
                        if today_shift.end < today_shift.start:
                            today_end += timedelta(days=1)

                        # Berechne Pause in Stunden
                        pause_hours = (tomorrow_start - today_end).total_seconds() / 3600

                        # Wenn Pause < 11 Stunden, dann nicht beide Schichten erlauben
                        if pause_hours < 11:
                            today_key = (employee.id, day['date'], today_shift.id)
                            tomorrow_key = (employee.id, next_day['date'], tomorrow_shift.id)

                            if today_key in variables and tomorrow_key in variables:
                                problem += (variables[today_key] +
                                            variables[tomorrow_key]) <= 1

        # 6. Berechnung der Gesamtstunden pro Mitarbeiter
        for employee in employees:
            total_hours = []
            for day in days:
                for shift in day['shifts']:
                    key = (employee.id, day['date'], shift.id)
                    if key in variables:
                        total_hours.append(
                            variables[key] * shift.get_duration()
                        )

            if total_hours:
                problem += employee_total_hours[employee.id] == lpSum(total_hours)

        # 7. Über-/Unterzeit Berechnung für Fairness
        # Ziel: Mitarbeiter sollen möglichst nahe an ihrer maximalen Kapazität arbeiten
        for employee in employees:
            max_possible_hours = employee.max_hours_per_week * 52  # 52 Wochen
            target_hours = min(max_possible_hours, average_hours_per_employee)

            problem += (employee_total_hours[employee.id] - target_hours ==
                        employee_overtime[employee.id] - employee_undertime[employee.id])

        # 8. Zusätzlicher Constraint: Nutze verfügbare Kapazität besser aus
        # Ermutige höhere Arbeitszeit pro Mitarbeiter (näher an Maximum)
        for employee in employees:
            max_yearly_hours = employee.max_hours_per_week * 52
            # Soft constraint: Versuche mindestens 80% der maximalen Kapazität zu nutzen
            min_target_hours = max_yearly_hours * 0.8

            # Dies wird über die Zielfunktion optimiert, nicht als harter Constraint

        # ZIELFUNKTION
        # Hauptziel: Maximiere Besetzung (bevorzuge Vollbesetzung)
        maximize_staffing = 0
        for day in days:
            for shift in day['shifts']:
                shift_assignments = []
                for employee in employees:
                    key = (employee.id, day['date'], shift.id)
                    if key in variables:
                        shift_assignments.append(variables[key])

                if shift_assignments:
                    # Belohne jede zusätzliche Person über Mindestbesetzung
                    maximize_staffing += lpSum(shift_assignments)

        # Sekundärziel: Fairness (Unterschiede in Arbeitszeit minimieren)
        fairness_penalty = lpSum([employee_overtime[emp.id] + employee_undertime[emp.id]
                                  for emp in employees])

        # Tertiärziel: Präferenz-Bonus
        preference_bonus = 0
        for employee in employees:
            preferred_shift_names = employee.preferred_shifts
            for day in days:
                for shift in day['shifts']:
                    if shift.name in preferred_shift_names:
                        key = (employee.id, day['date'], shift.id)
                        if key in variables:
                            preference_bonus += variables[key]  # Positive = Belohnung

        # Gewichtete Zielfunktion (Minimierung, daher negative Werte für Maximierung)
        # Priorität: 1. Vollbesetzung, 2. Fairness, 3. Präferenzen
        problem += (-maximize_staffing * 10000 +  # Höchste Priorität: Vollbesetzung
                    fairness_penalty * 100 +  # Mittlere Priorität: Fairness
                    -preference_bonus * 1)  # Niedrigste Priorität: Präferenzen

        # Solve the problem.
        self.stdout.write("Starte Optimierung...")
        problem.solve(PULP_CBC_CMD(msg=True, timeLimit=300))  # 5 Minuten Zeitlimit

        # Check if solution is optimal
        if problem.status != 1:
            self.stdout.write(self.style.ERROR(
                f"Optimierung nicht erfolgreich. Status: {problem.status}"
            ))
            return

        # Prepare JSON output list
        schedule_json = []

        # Calculate KPIs
        kpis = {
            'total_assignments': 0,
            'employee_stats': {},
            'shift_coverage': defaultdict(int),
            'fairness_metrics': {}
        }

        # Save new schedule entries to the database and JSON list.
        for employee in employees:
            employee_hours = 0
            employee_shifts = 0

            for day in days:
                for shift in day['shifts']:
                    var = variables[(employee.id, day['date'], shift.id)]
                    if var.varValue == 1:
                        # DB entry
                        ScheduleEntry.objects.create(
                            employee=employee,
                            date=day['date'],
                            shift_type=shift,
                            archived=False
                        )

                        # JSON record
                        schedule_json.append({
                            "employee_id": employee.id,
                            "employee_name": employee.name,
                            "date": day['date'].isoformat(),
                            "shift_id": shift.id,
                            "shift_name": shift.name,
                            "shift_duration": shift.get_duration()
                        })

                        # Update KPIs
                        employee_hours += shift.get_duration()
                        employee_shifts += 1
                        kpis['total_assignments'] += 1
                        kpis['shift_coverage'][shift.name] += 1

            # Employee statistics
            kpis['employee_stats'][employee.id] = {
                'name': employee.name,
                'total_hours': employee_hours,
                'total_shifts': employee_shifts,
                'max_hours_per_week': employee.max_hours_per_week,
                'utilization_rate': employee_hours / (52 * employee.max_hours_per_week) * 100
            }

        # Calculate fairness metrics
        hours_list = [stats['total_hours'] for stats in kpis['employee_stats'].values()]
        max_hours_list = [stats['max_hours_per_week'] * 52 for stats in kpis['employee_stats'].values()]

        if hours_list:
            kpis['fairness_metrics'] = {
                'average_hours': sum(hours_list) / len(hours_list),
                'min_hours': min(hours_list),
                'max_hours': max(hours_list),
                'hours_std_dev': (sum([(h - sum(hours_list) / len(hours_list)) ** 2
                                       for h in hours_list]) / len(hours_list)) ** 0.5,
                'average_capacity_utilization': sum([h / m for h, m in zip(hours_list, max_hours_list)]) / len(
                    hours_list) * 100,
                'total_possible_hours': total_possible_hours,
                'total_scheduled_hours': sum(hours_list),
                'coverage_rate': sum(hours_list) / total_possible_hours * 100 if total_possible_hours > 0 else 0
            }

        # Write JSON to file
        output_data = {
            'schedule': schedule_json,
            'kpis': kpis,
            'generation_date': datetime.now().isoformat(),
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        }

        output_path = 'yearly_schedule.json'
        with open(output_path, 'w', encoding='utf-8') as json_file:
            json.dump(output_data, json_file, indent=4, ensure_ascii=False)

        # Print summary
        self.stdout.write(self.style.SUCCESS(
            f"Jahresschichtplan erfolgreich generiert und nach {output_path} exportiert."
        ))
        self.stdout.write(f"Gesamte Zuweisungen: {kpis['total_assignments']}")
        self.stdout.write(f"Durchschnittliche Stunden pro Mitarbeiter: {kpis['fairness_metrics']['average_hours']:.1f}")
        self.stdout.write(
            f"Durchschnittliche Kapazitätsauslastung: {kpis['fairness_metrics']['average_capacity_utilization']:.1f}%")
        self.stdout.write(f"Schichtabdeckung: {kpis['fairness_metrics']['coverage_rate']:.1f}%")
        self.stdout.write(f"Fairness (Std. Abweichung): {kpis['fairness_metrics']['hours_std_dev']:.1f}")