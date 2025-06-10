from datetime import datetime, timedelta
from collections import defaultdict
import json
import random
import copy

from django.core.management.base import BaseCommand
from rostering_app.models import Employee, ShiftType, ScheduleEntry


class Individual:
    """Repräsentiert ein Individuum (Lösung) in der Population"""

    def __init__(self):
        # (date, shift_id) -> [employee_id, ...]
        self.genes = {}
        self.fitness = float('inf')  # Niedrigere Werte = bessere Fitness

    def copy(self):
        new_individual = Individual()
        new_individual.genes = {k: v.copy() for k, v in self.genes.items()}
        new_individual.fitness = self.fitness
        return new_individual


class Command(BaseCommand):
    help = 'Generate employee rostering schedule using Genetic Algorithm'

    def __init__(self):
        super().__init__()
        self.employees = []
        self.emp_by_id = {}
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
        # Vorschlag 1: Abwesenheiten vorkalkulieren
        for emp in self.employees:
            emp.absence_dates = {datetime.strptime(d, '%Y-%m-%d').date() for d in emp.absences}
        # Map für schnellen Zugriff
        self.emp_by_id = {emp.id: emp for emp in self.employees}

        self.shift_types = list(ShiftType.objects.all())
        # Vorschlag 1: Schichtdauer einmalig speichern
        for st in self.shift_types:
            st.duration = st.get_duration()

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

        # Run Genetic Algorithm
        self.stdout.write("Starte Genetischen Algorithmus...")
        best_solution = self.genetic_algorithm()

        # Save results
        self.save_solution(best_solution)
        self.stdout.write(self.style.SUCCESS("Genetischer Algorithmus abgeschlossen!"))

    def create_random_individual(self):
        """Erstelle ein zufälliges Individuum - schnelle Version"""
        individual = Individual()

        # Vorschlag 1: tägliche Verfügbarkeit nur IDs
        daily_availability = {}
        for day in self.days:
            available_ids = []
            for emp in self.employees:
                if day['date'] not in emp.absence_dates:
                    available_ids.append(emp.id)
            daily_availability[day['date']] = available_ids

        # Schnelle Zuweisung ohne komplexe Constraint-Checks
        for day in self.days:
            avail = daily_availability[day['date']].copy()
            random.shuffle(avail)
            used = set()
            for shift in day['shifts']:
                key = (day['date'], shift.id)
                candidates = [eid for eid in avail if eid not in used]
                if candidates:
                    count = random.randint(0, min(shift.max_staff, len(candidates)))
                    selected = random.sample(candidates, count)
                    individual.genes[key] = selected
                    used.update(selected)
                else:
                    individual.genes[key] = []
        return individual

    def is_employee_potentially_available(self, emp_id, date):
        """Verfügbarkeit nur anhand Vorberechneter Abwesenheiten"""
        emp = self.emp_by_id[emp_id]
        return date not in emp.absence_dates

    def evaluate_fitness(self, individual):
        """Berechne Fitness eines Individuums (niedrigere Werte = besser)"""
        penalty = 0

        # 1. Mindest-/Maximalbesetzung
        for day in self.days:
            for shift in day['shifts']:
                key = (day['date'], shift.id)
                assigned = len(individual.genes.get(key, []))
                if assigned < shift.min_staff:
                    penalty += (shift.min_staff - assigned) * 10000
                elif assigned > shift.max_staff:
                    penalty += (assigned - shift.max_staff) * 10000

        # 2. Ein Mitarbeiter pro Tag
        for day in self.days:
            count_per_emp = defaultdict(int)
            for shift in day['shifts']:
                for eid in individual.genes.get((day['date'], shift.id), []):
                    count_per_emp[eid] += 1
            for cnt in count_per_emp.values():
                if cnt > 1:
                    penalty += (cnt - 1) * 5000

        # 3. Wöchentliche Arbeitszeit
        for emp in self.employees:
            for week_key, week_days in self.weeks.items():
                hours = 0
                for day in week_days:
                    for shift in day['shifts']:
                        if emp.id in individual.genes.get((day['date'], shift.id), []):
                            hours += shift.duration
                if hours > emp.max_hours_per_week:
                    penalty += (hours - emp.max_hours_per_week) * 1000

        # 4. 11-Stunden-Regel
        penalty += self.check_rest_period_violations(individual) * 5000

        # 5. Abwesenheiten
        for day in self.days:
            for shift in day['shifts']:
                for eid in individual.genes.get((day['date'], shift.id), []):
                    if day['date'] in self.emp_by_id[eid].absence_dates:
                        penalty += 10000

        # Soft Constraints
        # 6. Fairness
        emp_hours = defaultdict(int)
        for (date, sid), eids in individual.genes.items():
            shift = next(s for s in self.shift_types if s.id == sid)
            for eid in eids:
                emp_hours[eid] += shift.duration
        if emp_hours:
            vals = list(emp_hours.values())
            avg = sum(vals) / len(vals)
            for h in vals:
                penalty += abs(h - avg)

        # 7. Präferenzen
        bonus = 0
        for (date, sid), eids in individual.genes.items():
            shift = next(s for s in self.shift_types if s.id == sid)
            for eid in eids:
                if shift.name in self.emp_by_id[eid].preferred_shifts:
                    bonus += 10
        penalty -= bonus

        # 8. Besetzungsgrad
        coverage = sum(len(eids) for eids in individual.genes.values())
        penalty -= coverage * 5

        individual.fitness = penalty
        return penalty

    def check_rest_period_violations(self, individual):
        violations = 0
        for i in range(len(self.days) - 1):
            today = self.days[i]
            tomorrow = self.days[i+1]
            for emp in self.employees:
                # Schichten-ID-Listen
                today_shifts = [s for s in today['shifts'] if emp.id in individual.genes.get((today['date'], s.id), [])]
                tomorrow_shifts = [s for s in tomorrow['shifts'] if emp.id in individual.genes.get((tomorrow['date'], s.id), [])]
                for ts in today_shifts:
                    end_dt = datetime.combine(today['date'], ts.end)
                    if ts.end < ts.start:
                        end_dt += timedelta(days=1)
                    for nts in tomorrow_shifts:
                        start_dt = datetime.combine(tomorrow['date'], nts.start)
                        pause = (start_dt - end_dt).total_seconds() / 3600
                        if pause < 11:
                            violations += 1
        return violations

    def tournament_selection(self, population, tournament_size=3):
        tournament = random.sample(population, min(tournament_size, len(population)))
        return min(tournament, key=lambda x: x.fitness)

    def crossover(self, p1, p2):
        c1, c2 = Individual(), Individual()
        for k in p1.genes:
            if random.random() < 0.5:
                c1.genes[k] = p1.genes[k].copy()
                c2.genes[k] = p2.genes[k].copy()
            else:
                c1.genes[k] = p2.genes[k].copy()
                c2.genes[k] = p1.genes[k].copy()
        return c1, c2

    def mutate(self, ind, mutation_rate=0.1):
        for k in list(ind.genes.keys()):
            if random.random() < mutation_rate:
                date, sid = k
                shift = next(s for s in self.shift_types if s.id == sid)
                staff = ind.genes[k]
                avail = [eid for eid in self.emp_by_id if eid not in staff and self.is_employee_potentially_available(eid, date)]
                mtype = random.choice(['add','remove','replace'])
                if mtype=='add' and len(staff)<shift.max_staff and avail:
                    staff.append(random.choice(avail))
                elif mtype=='remove' and len(staff)>shift.min_staff:
                    staff.remove(random.choice(staff))
                elif mtype=='replace' and staff and avail:
                    old = random.choice(staff)
                    rep = random.choice(avail)
                    staff[staff.index(old)] = rep
                ind.genes[k] = staff

    def evaluate_fitness_fast(self, individual):
        penalty = 0
        # Min/Max
        for day in self.days:
            for shift in day['shifts']:
                cnt = len(individual.genes.get((day['date'], shift.id), []))
                if cnt < shift.min_staff:
                    penalty += (shift.min_staff-cnt)*10000
                elif cnt>shift.max_staff:
                    penalty += (cnt-shift.max_staff)*10000
        # Ein pro Tag
        viol=0
        for day in self.days:
            c=defaultdict(int)
            for shift in day['shifts']:
                for eid in individual.genes.get((day['date'], shift.id), []): c[eid]+=1
            for v in c.values():
                if v>1: viol += v-1
        penalty += viol*5000
        # einfache Fairness
        total = sum(len(v) for v in individual.genes.values())
        penalty -= total*5
        individual.fitness = penalty
        return penalty

    def genetic_algorithm(self):
        population_size, num_generations = 20, 50
        mutation_rate, crossover_rate = 0.2, 0.8
        elitism_size = 2

        self.stdout.write("Erstelle initiale Population...")
        population = []
        for _ in range(population_size):
            ind = self.create_random_individual()
            self.evaluate_fitness_fast(ind)
            population.append(ind)
        population.sort(key=lambda x: x.fitness)
        best = population[0].copy()

        for gen in range(num_generations):
            new_pop = [population[i].copy() for i in range(elitism_size)]
            while len(new_pop) < population_size:
                p1 = self.tournament_selection(population)
                p2 = self.tournament_selection(population)
                if random.random()<crossover_rate:
                    c1,c2 = self.crossover(p1,p2)
                else:
                    c1,c2 = p1.copy(), p2.copy()
                self.mutate(c1,mutation_rate)
                if len(new_pop)+1<population_size:
                    self.mutate(c2,mutation_rate)
                if gen>10:
                    self.evaluate_fitness(c1)
                    if len(new_pop)+1<population_size: self.evaluate_fitness(c2)
                else:
                    self.evaluate_fitness_fast(c1)
                    if len(new_pop)+1<population_size: self.evaluate_fitness_fast(c2)
                new_pop.append(c1)
                if len(new_pop)<population_size: new_pop.append(c2)
            population = sorted(new_pop, key=lambda x: x.fitness)[:population_size]
            if population[0].fitness<best.fitness:
                best = population[0].copy()
                self.evaluate_fitness(best)
        self.evaluate_fitness(best)
        return best

    def save_solution(self, individual):
        schedule_json, kpis = [], {
            'total_assignments':0, 'employee_stats':{}, 'shift_coverage':defaultdict(int), 'fairness_metrics':{}
        }
        emp_hours, emp_shifts = defaultdict(int), defaultdict(int)
        for (date, sid), eids in individual.genes.items():
            shift = next(s for s in self.shift_types if s.id==sid)
            for eid in eids:
                emp = self.emp_by_id[eid]
                ScheduleEntry.objects.create(
                    employee=emp, date=date, shift_type=shift, archived=False
                )
                schedule_json.append({
                    'employee_id':eid,
                    'employee_name':emp.name,
                    'date':date.isoformat(),
                    'shift_id':sid,
                    'shift_name':shift.name,
                    'shift_duration':shift.duration
                })
                emp_hours[eid]+=shift.duration
                emp_shifts[eid]+=1
                kpis['total_assignments']+=1
                kpis['shift_coverage'][shift.name]+=1
        # Stats
        for emp in self.employees:
            h=emp_hours[emp.id]
            kpis['employee_stats'][emp.id] = {
                'name':emp.name,
                'total_hours':h,
                'total_shifts':emp_shifts[emp.id],
                'max_hours_per_week':emp.max_hours_per_week,
                'utilization_rate':(h/(52*emp.max_hours_per_week)*100) if emp.max_hours_per_week>0 else 0
            }
        hours_list=list(emp_hours.values())
        if hours_list:
            avg=sum(hours_list)/len(hours_list)
            kpis['fairness_metrics']={
                'average_hours':avg,
                'min_hours':min(hours_list),
                'max_hours':max(hours_list),
                'hours_std_dev':(sum((h-avg)**2 for h in hours_list)/len(hours_list))**0.5
            }
        output={
            'schedule':schedule_json,'kpis':kpis,
            'generation_date':datetime.now().isoformat(),
            'algorithm':'Genetic Algorithm',
            'period':{'start_date':self.start_date.isoformat(),'end_date':self.end_date.isoformat()}
        }
        path='yearly_schedule_ga.json'
        with open(path,'w',encoding='utf-8') as f: json.dump(output,f,indent=4,ensure_ascii=False)
        self.stdout.write(self.style.SUCCESS(f"Ergebnis nach {path} exportiert"))
        self.stdout.write(f"Gesamte Zuweisungen: {kpis['total_assignments']}")
        if 'average_hours' in kpis['fairness_metrics']:
            self.stdout.write(f"Durchschnittliche Stunden: {kpis['fairness_metrics']['average_hours']:.1f}")
            self.stdout.write(f"Std. Abweichung: {kpis['fairness_metrics']['hours_std_dev']:.1f}")
