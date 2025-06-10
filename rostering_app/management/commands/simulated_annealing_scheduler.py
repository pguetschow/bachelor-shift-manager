from datetime import datetime, timedelta
from collections import defaultdict
import json
import random
import math
import copy

from django.core.management.base import BaseCommand
from rostering_app.models import Employee, ShiftType, ScheduleEntry


class Command(BaseCommand):
    help = 'Generate employee rostering schedule using Simulated Annealing'

    def __init__(self):
        super().__init__()
        self.employees = []
        self.shift_types = []
        self.days = []
        self.weeks = defaultdict(list)
        self.start_date = None
        self.end_date = None

    def handle(self, *args, **kwargs):
        # Archive previous schedule entries
        ScheduleEntry.objects.filter(archived=False).update(archived=True)

        # Initialize data
        self.employees = list(Employee.objects.all())
        self.shift_types = list(ShiftType.objects.all())
        
        # Define scheduling period
        self.start_date = datetime.strptime('2025-01-01', '%Y-%m-%d').date()
        self.end_date = datetime.strptime('2025-12-31', '%Y-%m-%d').date()
        num_days = (self.end_date - self.start_date).days + 1

        # Build list of days
        self.days = []
        for i in range(num_days):
            day_date = self.start_date + timedelta(days=i)
            self.days.append({'date': day_date, 'shifts': self.shift_types})

        # Group days by ISO week
        for day in self.days:
            iso_year, iso_week, _ = day['date'].isocalendar()
            self.weeks[(iso_year, iso_week)].append(day)

        # Run Simulated Annealing
        self.stdout.write("Starte Simulated Annealing Optimierung...")
        best_solution = self.simulated_annealing()
        
        # Save results
        self.save_solution(best_solution)
        self.stdout.write(self.style.SUCCESS("Simulated Annealing abgeschlossen!"))

    def create_initial_solution(self):
        """Erstelle eine initiale, gültige Lösung"""
        solution = {}
        
        # Initialisiere alle Zuweisungen mit 0
        for day in self.days:
            for shift in day['shifts']:
                solution[(day['date'], shift.id)] = []
        
        # Greedy-Ansatz für initiale Lösung
        for day in self.days:
            for shift in day['shifts']:
                # Verfügbare Mitarbeiter für diesen Tag/Schicht
                available_employees = []
                
                for employee in self.employees:
                    if self.is_employee_available(employee, day['date'], shift, solution):
                        available_employees.append(employee)
                
                # Zufällige Auswahl zwischen min_staff und max_staff
                if available_employees:
                    target_staff = random.randint(shift.min_staff, 
                                                min(shift.max_staff, len(available_employees)))
                    selected = random.sample(available_employees, target_staff)
                    solution[(day['date'], shift.id)] = selected
        
        return solution

    def is_employee_available(self, employee, date, shift, current_solution):
        """Prüfe ob Mitarbeiter verfügbar ist"""
        # Prüfe Abwesenheit
        absence_dates = [datetime.strptime(date_str, '%Y-%m-%d').date()
                        for date_str in employee.absences]
        if date in absence_dates:
            return False
        
        # Prüfe ob bereits an diesem Tag eingeteilt
        for existing_shift in self.shift_types:
            if employee in current_solution.get((date, existing_shift.id), []):
                return False
        
        # Prüfe wöchentliche Arbeitszeit
        iso_year, iso_week, _ = date.isocalendar()
        week_days = self.weeks[(iso_year, iso_week)]
        current_weekly_hours = 0
        
        for day in week_days:
            for s in day['shifts']:
                if employee in current_solution.get((day['date'], s.id), []):
                    current_weekly_hours += s.get_duration()
        
        if current_weekly_hours + shift.get_duration() > employee.max_hours_per_week:
            return False
        
        # Prüfe 11-Stunden-Regel
        if not self.check_rest_period(employee, date, shift, current_solution):
            return False
        
        return True

    def check_rest_period(self, employee, date, shift, solution):
        """Prüfe 11-Stunden-Pause zwischen Schichten"""
        # Prüfe vorherigen Tag
        prev_date = date - timedelta(days=1)
        for prev_shift in self.shift_types:
            if employee in solution.get((prev_date, prev_shift.id), []):
                prev_end = datetime.combine(prev_date, prev_shift.end)
                if prev_shift.end < prev_shift.start:  # Nachtschicht
                    prev_end += timedelta(days=1)
                
                curr_start = datetime.combine(date, shift.start)
                pause_hours = (curr_start - prev_end).total_seconds() / 3600
                
                if pause_hours < 11:
                    return False
        
        # Prüfe nächsten Tag
        next_date = date + timedelta(days=1)
        for next_shift in self.shift_types:
            if employee in solution.get((next_date, next_shift.id), []):
                curr_end = datetime.combine(date, shift.end)
                if shift.end < shift.start:  # Nachtschicht
                    curr_end += timedelta(days=1)
                
                next_start = datetime.combine(next_date, next_shift.start)
                pause_hours = (next_start - curr_end).total_seconds() / 3600
                
                if pause_hours < 11:
                    return False
        
        return True

    def evaluate_solution(self, solution):
        """Bewerte die Qualität einer Lösung (niedrigere Werte = besser)"""
        penalty = 0
        
        # Penalty für nicht erfüllte Mindestbesetzung
        for day in self.days:
            for shift in day['shifts']:
                assigned = len(solution.get((day['date'], shift.id), []))
                if assigned < shift.min_staff:
                    penalty += (shift.min_staff - assigned) * 10000
        
        # Penalty für Überschreitung der Maximalbesetzung
        for day in self.days:
            for shift in day['shifts']:
                assigned = len(solution.get((day['date'], shift.id), []))
                if assigned > shift.max_staff:
                    penalty += (assigned - shift.max_staff) * 10000
        
        # Fairness-Penalty (Unterschiede in Arbeitszeit)
        employee_hours = defaultdict(int)
        for day in self.days:
            for shift in day['shifts']:
                for employee in solution.get((day['date'], shift.id), []):
                    employee_hours[employee.id] += shift.get_duration()
        
        if employee_hours:
            hours_list = list(employee_hours.values())
            avg_hours = sum(hours_list) / len(hours_list)
            for hours in hours_list:
                penalty += abs(hours - avg_hours) * 10
        
        # Belohnung für Präferenzen
        preference_bonus = 0
        for day in self.days:
            for shift in day['shifts']:
                for employee in solution.get((day['date'], shift.id), []):
                    if shift.name in employee.preferred_shifts:
                        preference_bonus += 1
        
        penalty -= preference_bonus
        
        # Belohnung für höhere Besetzung (näher an Maximum)
        staffing_bonus = 0
        for day in self.days:
            for shift in day['shifts']:
                assigned = len(solution.get((day['date'], shift.id), []))
                staffing_bonus += assigned
        
        penalty -= staffing_bonus * 10
        
        return penalty

    def get_neighbor(self, solution):
        """Generiere eine Nachbarlösung durch kleine Änderungen"""
        new_solution = copy.deepcopy(solution)
        
        # Wähle zufällige Änderung
        change_type = random.choice(['add', 'remove', 'swap', 'move'])
        
        # Zufälliger Tag und Schicht
        day = random.choice(self.days)
        shift = random.choice(day['shifts'])
        key = (day['date'], shift.id)
        
        if change_type == 'add':
            # Füge Mitarbeiter hinzu
            current_staff = new_solution.get(key, [])
            if len(current_staff) < shift.max_staff:
                available = []
                for emp in self.employees:
                    if emp not in current_staff and self.is_employee_available(emp, day['date'], shift, new_solution):
                        available.append(emp)
                
                if available:
                    selected = random.choice(available)
                    new_solution[key] = current_staff + [selected]
        
        elif change_type == 'remove':
            # Entferne Mitarbeiter
            current_staff = new_solution.get(key, [])
            if len(current_staff) > shift.min_staff:
                if current_staff:
                    to_remove = random.choice(current_staff)
                    new_solution[key] = [emp for emp in current_staff if emp != to_remove]
        
        elif change_type == 'swap':
            # Tausche zwei Mitarbeiter zwischen Schichten
            day2 = random.choice(self.days)
            shift2 = random.choice(day2['shifts'])
            key2 = (day2['date'], shift2.id)
            
            staff1 = new_solution.get(key, [])
            staff2 = new_solution.get(key2, [])
            
            if staff1 and staff2:
                emp1 = random.choice(staff1)
                emp2 = random.choice(staff2)
                
                # Temporärer Tausch
                new_staff1 = [emp2 if emp == emp1 else emp for emp in staff1]
                new_staff2 = [emp1 if emp == emp2 else emp for emp in staff2]
                
                # Prüfe Gültigkeit
                temp_solution = copy.deepcopy(new_solution)
                temp_solution[key] = new_staff1
                temp_solution[key2] = new_staff2
                
                if (self.is_employee_available(emp2, day['date'], shift, temp_solution) and
                    self.is_employee_available(emp1, day2['date'], shift2, temp_solution)):
                    new_solution[key] = new_staff1
                    new_solution[key2] = new_staff2
        
        elif change_type == 'move':
            # Bewege Mitarbeiter von einer Schicht zur anderen
            current_staff = new_solution.get(key, [])
            if len(current_staff) > shift.min_staff:
                if current_staff:
                    to_move = random.choice(current_staff)
                    new_solution[key] = [emp for emp in current_staff if emp != to_move]
                    
                    # Finde neuen Platz
                    other_day = random.choice(self.days)
                    other_shift = random.choice(other_day['shifts'])
                    other_key = (other_day['date'], other_shift.id)
                    other_staff = new_solution.get(other_key, [])
                    
                    if (len(other_staff) < other_shift.max_staff and
                        self.is_employee_available(to_move, other_day['date'], other_shift, new_solution)):
                        new_solution[other_key] = other_staff + [to_move]
                    else:
                        # Rückgängig machen
                        new_solution[key] = current_staff
        
        return new_solution

    def simulated_annealing(self):
        """Hauptalgorithmus für Simulated Annealing"""
        current_solution = self.create_initial_solution()
        current_cost = self.evaluate_solution(current_solution)
        
        best_solution = copy.deepcopy(current_solution)
        best_cost = current_cost
        
        # SA Parameter
        initial_temp = 10000
        final_temp = 1
        cooling_rate = 0.995
        max_iterations = 10000
        
        temperature = initial_temp
        
        for iteration in range(max_iterations):
            # Generiere Nachbarlösung
            new_solution = self.get_neighbor(current_solution)
            new_cost = self.evaluate_solution(new_solution)
            
            # Akzeptanzkriterium
            if new_cost < current_cost:
                # Bessere Lösung -> akzeptieren
                current_solution = new_solution
                current_cost = new_cost
                
                if new_cost < best_cost:
                    best_solution = copy.deepcopy(new_solution)
                    best_cost = new_cost
            else:
                # Schlechtere Lösung -> mit Wahrscheinlichkeit akzeptieren
                delta = new_cost - current_cost
                probability = math.exp(-delta / temperature)
                
                if random.random() < probability:
                    current_solution = new_solution
                    current_cost = new_cost
            
            # Temperatur reduzieren
            temperature *= cooling_rate
            
            # Progress output
            if iteration % 1000 == 0:
                self.stdout.write(f"Iteration {iteration}: Beste Kosten = {best_cost:.1f}, Temperatur = {temperature:.1f}")
            
            # Stopping criterion
            if temperature < final_temp:
                break
        
        self.stdout.write(f"Simulated Annealing beendet. Beste Kosten: {best_cost:.1f}")
        return best_solution

    def save_solution(self, solution):
        """Speichere die Lösung in der Datenbank und als JSON"""
        schedule_json = []
        kpis = {
            'total_assignments': 0,
            'employee_stats': {},
            'shift_coverage': defaultdict(int),
            'fairness_metrics': {}
        }
        
        employee_hours = defaultdict(int)
        employee_shifts = defaultdict(int)
        
        # Speichere Zuweisungen
        for day in self.days:
            for shift in day['shifts']:
                assigned_employees = solution.get((day['date'], shift.id), [])
                
                for employee in assigned_employees:
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
                    employee_hours[employee.id] += shift.get_duration()
                    employee_shifts[employee.id] += 1
                    kpis['total_assignments'] += 1
                    kpis['shift_coverage'][shift.name] += 1
        
        # Employee statistics
        for employee in self.employees:
            kpis['employee_stats'][employee.id] = {
                'name': employee.name,
                'total_hours': employee_hours[employee.id],
                'total_shifts': employee_shifts[employee.id],
                'max_hours_per_week': employee.max_hours_per_week,
                'utilization_rate': employee_hours[employee.id] / (52 * employee.max_hours_per_week) * 100
            }
        
        # Fairness metrics
        hours_list = [employee_hours[emp.id] for emp in self.employees]
        if hours_list:
            avg_hours = sum(hours_list) / len(hours_list)
            kpis['fairness_metrics'] = {
                'average_hours': avg_hours,
                'min_hours': min(hours_list),
                'max_hours': max(hours_list),
                'hours_std_dev': (sum([(h - avg_hours) ** 2 for h in hours_list]) / len(hours_list)) ** 0.5
            }
        
        # Export to JSON
        output_data = {
            'schedule': schedule_json,
            'kpis': kpis,
            'generation_date': datetime.now().isoformat(),
            'algorithm': 'Simulated Annealing',
            'period': {
                'start_date': self.start_date.isoformat(),
                'end_date': self.end_date.isoformat()
            }
        }
        
        output_path = 'yearly_schedule_sa.json'
        with open(output_path, 'w', encoding='utf-8') as json_file:
            json.dump(output_data, json_file, indent=4, ensure_ascii=False)
        
        self.stdout.write(self.style.SUCCESS(f"Ergebnis nach {output_path} exportiert"))
        self.stdout.write(f"Gesamte Zuweisungen: {kpis['total_assignments']}")
        if 'average_hours' in kpis['fairness_metrics']:
            self.stdout.write(f"Durchschnittliche Stunden: {kpis['fairness_metrics']['average_hours']:.1f}")
            self.stdout.write(f"Std. Abweichung: {kpis['fairness_metrics']['hours_std_dev']:.1f}")
