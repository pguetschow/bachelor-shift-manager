from datetime import datetime, timedelta
from collections import defaultdict

from django.core.management.base import BaseCommand
from pulp import LpProblem, LpVariable, lpSum, LpMinimize, LpBinary, LpContinuous, PULP_CBC_CMD

from rostering_app.models import Employee, ShiftType, ScheduleEntry


class Command(BaseCommand):
    help = ("Erstellt einen Jahresdienstplan in 12 monatlichen Durchgängen. "
            "Dabei werden harte Constraints (Mindestbesetzung, max. eine Schicht pro Tag, "
            "11-Stunden-Pause, Abwesenheiten, vertragliche Wochenarbeitszeit) und weiche Ziele "
            "(Vollbesetzung, Fairness, bevorzugte Schichten) berücksichtigt. "
            "Arbeitszeitdefizite werden als Carry‑Over in den Folgemonat übernommen; Übergangstage "
            "zwischen Monaten werden besonders behandelt.")

    def handle(self, *args, **kwargs):
        # Archiviere alte Dienstplaneinträge
        ScheduleEntry.objects.filter(archived=False).update(archived=True)

        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())

        # Jahreszeitraum: 2024-01-01 bis 2024-12-31
        start_date = datetime.strptime('2024-01-01', '%Y-%m-%d').date()
        end_date = datetime.strptime('2024-12-31', '%Y-%m-%d').date()
        num_days = (end_date - start_date).days + 1

        # Erzeuge Liste aller Tage: Jeder Tag enthält alle verfügbaren ShiftTypes.
        days = []
        for i in range(num_days):
            day_date = start_date + timedelta(days=i)
            days.append({'date': day_date, 'shifts': shift_types})

        # Gruppiere Tage nach ISO-Woche (wird innerhalb des Monats später gebraucht)
        weeks = defaultdict(list)
        for day in days:
            iso_year, iso_week, _ = day['date'].isocalendar()
            weeks[(iso_year, iso_week)].append(day)

        # Initialisiere Carry‑Over: Für jeden Mitarbeiter wird gespeichert, wie viel Differenz (Ist - Soll)
        # bereits entstanden ist, um im Folgemonat ausgeglichen zu werden.
        carryover = {employee.id: 0 for employee in employees}

        # Speichert die Schicht, die ein Mitarbeiter am letzten Tag des Vormonats zugewiesen bekam,
        # um Übergangsbeschränkungen (11-Stunden-Pause) am Monatswechsel berücksichtigen zu können.
        last_day_assignment = {}

        # Durchlaufe alle 12 Monate
        for month in range(1, 13):
            # Filtere alle Tage, die zum aktuellen Monat gehören
            month_days = [day for day in days if day['date'].month == month]
            # Falls in diesem Monat keine Tage vorhanden sind, diesen Durchlauf überspringen.
            if not month_days:
                self.stdout.write(self.style.WARNING(f"Kein Planungstag für Monat {month} gefunden, überspringe diesen Monat."))
                continue

            # Erstelle ein neues Optimierungsproblem für den Monat
            monthly_problem = LpProblem(f"Employee_Rostering_Month_{month}", LpMinimize)

            # --- Definition der Entscheidungsvariablen ---

            # x: Binärvariable, ob Mitarbeiter i an Tag d in Shift s arbeitet.
            monthly_x = {}
            for employee in employees:
                for day in month_days:
                    for shift in day['shifts']:
                        key = (employee.id, day['date'], shift.id)
                        monthly_x[key] = LpVariable(
                            f"x_{employee.id}_{day['date']}_{shift.id}",
                            0, 1, LpBinary
                        )

            # u: Hilfsvariable für unbesetzte Positionen, sodass
            # Summe(x) + u = shift.max_staff.
            monthly_u = {}
            for day in month_days:
                for shift in day['shifts']:
                    key = (day['date'], shift.id)
                    monthly_u[key] = LpVariable(
                        f"u_{day['date']}_{shift.id}",
                        0, None, LpContinuous
                    )

            # H_actual: Tatsächlich gearbeitete Stunden im Monat für jeden Mitarbeiter.
            monthly_H_actual = {}
            for employee in employees:
                monthly_H_actual[employee.id] = LpVariable(
                    f"H_actual_{employee.id}_m{month}",
                    0, None, LpContinuous
                )

            # Fairnessvariablen: d_plus und d_minus messen Über- bzw. Unterabweichungen vom Ziel.
            monthly_d_plus = {}
            monthly_d_minus = {}
            for employee in employees:
                monthly_d_plus[employee.id] = LpVariable(
                    f"d_plus_{employee.id}_m{month}",
                    0, None, LpContinuous
                )
                monthly_d_minus[employee.id] = LpVariable(
                    f"d_minus_{employee.id}_m{month}",
                    0, None, LpContinuous
                )

            # Globale Variable für die durchschnittliche Auslastung in diesem Monat.
            alpha_month = LpVariable(f"alpha_m{month}", 0, 1, LpContinuous)

            # ------------------ Harte Constraints für den Monat ------------------

            # (a) Staffing-Constraints: Für jeden Tag und jede Schicht soll gelten:
            # Sum(x) + u = shift.max_staff und Sum(x) >= shift.min_staff.
            for day in month_days:
                for shift in day['shifts']:
                    key_us = (day['date'], shift.id)
                    monthly_problem += lpSum(
                        monthly_x[(employee.id, day['date'], shift.id)]
                        for employee in employees
                    ) + monthly_u[key_us] == shift.max_staff, f"FullStaff_{day['date']}_{shift.id}"
                    monthly_problem += lpSum(
                        monthly_x[(employee.id, day['date'], shift.id)]
                        for employee in employees
                    ) >= shift.min_staff, f"MinStaff_{day['date']}_{shift.id}"

            # (b) Maximal eine Schicht pro Tag pro Mitarbeiter und Berücksichtigung von Abwesenheiten.
            for employee in employees:
                for day in month_days:
                    monthly_problem += lpSum(
                        monthly_x[(employee.id, day['date'], shift.id)]
                        for shift in day['shifts']
                    ) <= 1, f"OneShiftPerDay_{employee.id}_{day['date']}"
                    if day['date'].isoformat() in employee.absences:
                        for shift in day['shifts']:
                            monthly_problem += monthly_x[(employee.id, day['date'], shift.id)] == 0, \
                                               f"Absence_{employee.id}_{day['date']}_{shift.id}"

            # (c) 11-Stunden-Pause: Zwischen aufeinanderfolgenden Tagen innerhalb des Monats.
            for employee in employees:
                for i, day in enumerate(month_days[:-1]):
                    next_day = month_days[i+1]
                    # Beispiel: Falls LateShift an Tag d belegt, darf am Folgetag keine EarlyShift erfolgen.
                    for shift in day['shifts']:
                        if shift.name == "LateShift":
                            for shift_next in next_day['shifts']:
                                if shift_next.name == "EarlyShift":
                                    monthly_problem += monthly_x[(employee.id, day['date'], shift.id)] + \
                                                       monthly_x[(employee.id, next_day['date'], shift_next.id)] <= 1, \
                                                       f"Rest_LateToEarly_{employee.id}_{day['date']}_{next_day['date']}_{shift.id}_{shift_next.id}"
                    # Ebenso: Falls NightShift belegt, dann weder EarlyShift noch LateShift am nächsten Tag.
                    for shift in day['shifts']:
                        if shift.name == "NightShift":
                            for shift_next in next_day['shifts']:
                                if shift_next.name in ["EarlyShift", "LateShift"]:
                                    monthly_problem += monthly_x[(employee.id, day['date'], shift.id)] + \
                                                       monthly_x[(employee.id, next_day['date'], shift_next.id)] <= 1, \
                                                       f"Rest_NightTo_{employee.id}_{day['date']}_{next_day['date']}_{shift.id}_{shift_next.id}"

            # (d) Übergang von Vormonat zu aktuellem Monat:
            # An den ersten Tag des Monats werden Übergangsregeln angewendet,
            # falls im Vormonat Schichten belegt wurden.
            first_day = month_days[0]
            for employee in employees:
                if employee.id in last_day_assignment:
                    last_shift = last_day_assignment[employee.id]  # Letzte Schicht im Vormonat
                    if last_shift.name == "LateShift":
                        for shift in first_day['shifts']:
                            if shift.name == "EarlyShift":
                                monthly_problem += monthly_x[(employee.id, first_day['date'], shift.id)] == 0, \
                                                   f"Transition_Rest_LateToEarly_{employee.id}_{first_day['date']}_{shift.id}"
                    if last_shift.name == "NightShift":
                        for shift in first_day['shifts']:
                            if shift.name in ["EarlyShift", "LateShift"]:
                                monthly_problem += monthly_x[(employee.id, first_day['date'], shift.id)] == 0, \
                                                   f"Transition_Rest_NightTo_{employee.id}_{first_day['date']}_{shift.id}"

            # (e) Wöchentliche maximale Arbeitszeit: Nur für Wochen, die vollständig im aktuellen Monat liegen.
            month_weeks = defaultdict(list)
            for day in month_days:
                iso_year, iso_week, _ = day['date'].isocalendar()
                month_weeks[(iso_year, iso_week)].append(day)
            for employee in employees:
                for week_key, week_days in month_weeks.items():
                    if all(day['date'].month == month for day in week_days):
                        monthly_problem += lpSum(
                            monthly_x[(employee.id, day['date'], shift.id)] * shift.get_duration()
                            for day in week_days for shift in day['shifts']
                        ) <= employee.max_hours_per_week, f"MaxWeekly_{employee.id}_week_{week_key}"

            # (f) Berechnung der im Monat gearbeiteten Stunden für jeden Mitarbeiter.
            for employee in employees:
                monthly_problem += monthly_H_actual[employee.id] == lpSum(
                    monthly_x[(employee.id, day['date'], shift.id)] * shift.get_duration()
                    for day in month_days for shift in day['shifts']
                ), f"MonthlyHours_{employee.id}"

            # ------------------ Fairness-Constraints für den Monat ------------------
            # Das monatliche Soll wird als proportionaler Anteil der vertraglichen Wochenstunden berechnet:
            # monthly_target = employee.max_hours_per_week * (Anzahl Tage im Monat / 7)
            for employee in employees:
                monthly_target = employee.max_hours_per_week * (len(month_days) / 7)
                monthly_problem += monthly_H_actual[employee.id] - (monthly_target - carryover.get(employee.id, 0)) == \
                                   monthly_d_plus[employee.id] - monthly_d_minus[employee.id], \
                                   f"Fairness_{employee.id}_m{month}"
            total_monthly_contract = sum(employee.max_hours_per_week * (len(month_days) / 7) for employee in employees)
            monthly_problem += lpSum(monthly_H_actual[employee.id] for employee in employees) == \
                               alpha_month * total_monthly_contract, f"AvgUtilization_m{month}"

            # ------------------ Zielfunktion für den Monat ------------------
            lambda1 = 1000  # Hohe Strafe für unbesetzte Schichten (u)
            lambda2 = 10    # Strafe für Fairnessabweichungen (d_plus + d_minus)
            lambda3 = 5     # Bonus für erfüllte Präferenzen

            preferred_bonus = lpSum(
                monthly_x[(employee.id, day['date'], shift.id)]
                for employee in employees
                for day in month_days
                for shift in day['shifts']
                if shift.name in employee.preferred_shifts
            )
            objective_month = (
                lambda1 * lpSum(monthly_u[(day['date'], shift.id)] for day in month_days for shift in day['shifts']) +
                lambda2 * lpSum(monthly_d_plus[employee.id] + monthly_d_minus[employee.id] for employee in employees) -
                lambda3 * preferred_bonus
            )
            monthly_problem += objective_month, f"Objective_m{month}"

            # Lösen des monatlichen Optimierungsproblems
            monthly_problem.solve(PULP_CBC_CMD(msg=True))

            # Aktualisiere das Carry‑Over für jeden Mitarbeiter
            for employee in employees:
                monthly_target = employee.max_hours_per_week * (len(month_days) / 7)
                prev_carry = carryover.get(employee.id, 0)
                carryover[employee.id] = prev_carry + (monthly_H_actual[employee.id].varValue - monthly_target)

            # Speichere die letzte zugewiesene Schicht am letzten Tag des Monats (für Übergänge)
            last_day = max(month_days, key=lambda d: d['date'])
            for employee in employees:
                for shift in last_day['shifts']:
                    key = (employee.id, last_day['date'], shift.id)
                    if monthly_x[key].varValue == 1:
                        last_day_assignment[employee.id] = shift
                        break

            # Schreibe die Zuweisungen des Monats in die Datenbank
            for employee in employees:
                for day in month_days:
                    for shift in day['shifts']:
                        key = (employee.id, day['date'], shift.id)
                        if monthly_x[key].varValue == 1:
                            ScheduleEntry.objects.create(
                                employee=employee,
                                date=day['date'],
                                shift_type=shift,
                                archived=False
                            )

            self.stdout.write(self.style.SUCCESS(f"Monat {month} erfolgreich geplant."))

        self.stdout.write(self.style.SUCCESS("Jahresdienstplan (monatlich ausgerollt) erfolgreich generiert."))
