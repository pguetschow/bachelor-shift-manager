from datetime import datetime, timedelta, time
from collections import defaultdict
import json
import random
import math
import copy
import time
import statistics
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from rostering_app.models import Employee, ShiftType, ScheduleEntry


class Command(BaseCommand):
    help = 'Generate employee rostering schedule using Simulated Annealing'

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
        self.emp_by_id = {emp.id: emp for emp in self.employees}

        self.shift_types = list(ShiftType.objects.all())
        # Vorschlag 2: Schichtdauer einmalig speichern
        for st in self.shift_types:
            st.duration = st.get_duration()

        # Define scheduling period
        self.start_date = datetime.strptime('2025-01-01', '%Y-%m-%d').date()
        self.end_date = datetime.strptime('2025-12-31', '%Y-%m-%d').date()
        total_days = (self.end_date - self.start_date).days + 1

        # Build days and weeks
        for i in range(total_days):
            d = self.start_date + timedelta(days=i)
            self.days.append({'date': d, 'shifts': self.shift_types})
            iso = d.isocalendar()
            self.weeks[(iso[0], iso[1])].append(d)

        self.stdout.write("Starte Simulated Annealing Optimierung...")

        start_time = time.time()
        best = self.simulated_annealing_exponential()
        # best = self.simulated_annealing()
        runtime = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(f"Simulated Annealing abgeschlossen in: {runtime:.2f} "))
        self.save_solution(best)


    def create_initial_solution(self):
        """Erstelle eine initiale, gültige Lösung als Mapping (date,shift_id)->[employee_ids]"""
        sol = {(day['date'], st.id): [] for day in self.days for st in day['shifts']}

        for day in self.days:
            date = day['date']
            for st in day['shifts']:
                key = (date, st.id)
                avail = [eid for eid in self.emp_by_id if self.is_employee_available(eid, date, st, sol)]
                if avail:
                    count = random.randint(st.min_staff, min(st.max_staff, len(avail)))
                    sol[key] = random.sample(avail, count)
        return sol

    def is_employee_available(self, eid, date, shift, sol):
        emp = self.emp_by_id[eid]
        # Abwesenheit
        if date in emp.absence_dates:
            return False
        # Einteilung am gleichen Tag
        for st in self.shift_types:
            if eid in sol.get((date, st.id), []):
                return False
        # Wöchentliche Stunden
        week = tuple(date.isocalendar()[:2])
        hrs = 0
        for d in self.weeks[week]:
            for st in self.shift_types:
                if eid in sol.get((d, st.id), []):
                    hrs += st.duration
        if hrs + shift.duration > emp.max_hours_per_week:
            return False
        # 11-Stunden-Regel
        if not self.check_rest_period(eid, date, shift, sol):
            return False
        return True

    def check_rest_period(self, eid, date, shift, sol):
        """11-Stunden-Pause zwischen Tagen prüfen"""
        # Vorheriger Tag
        prev = date - timedelta(days=1)
        for st in self.shift_types:
            if eid in sol.get((prev, st.id), []):
                end_prev = datetime.combine(prev, st.end)
                if st.end < st.start:
                    end_prev += timedelta(days=1)
                start_cur = datetime.combine(date, shift.start)
                if (start_cur - end_prev).total_seconds()/3600 < 11:
                    return False
        # Nächster Tag
        nxt = date + timedelta(days=1)
        for st in self.shift_types:
            if eid in sol.get((nxt, st.id), []):
                end_cur = datetime.combine(date, shift.end)
                if shift.end < shift.start:
                    end_cur += timedelta(days=1)
                start_nxt = datetime.combine(nxt, st.start)
                if (start_nxt - end_cur).total_seconds()/3600 < 11:
                    return False
        return True

    def evaluate_solution(self, sol):
        penalty = 0
        # Min/Max Besetzung
        for day in self.days:
            for st in day['shifts']:
                cnt = len(sol.get((day['date'], st.id), []))
                if cnt < st.min_staff:
                    penalty += (st.min_staff - cnt) * 10000
                if cnt > st.max_staff:
                    penalty += (cnt - st.max_staff) * 10000
        # Fairness
        emp_hrs = defaultdict(int)
        for key, eids in sol.items():
            sid = key[1]
            st = next(s for s in self.shift_types if s.id == sid)
            for eid in eids:
                emp_hrs[eid] += st.duration
        if emp_hrs:
            avg = sum(emp_hrs.values())/len(emp_hrs)
            for h in emp_hrs.values(): penalty += abs(h - avg) * 10
        # Präferenzen
        bonus = 0
        for key, eids in sol.items():
            st = next(s for s in self.shift_types if s.id == key[1])
            for eid in eids:
                if st.name in self.emp_by_id[eid].preferred_shifts:
                    bonus += 1
        penalty -= bonus
        # Besetzungsbonus
        for eids in sol.values(): penalty -= len(eids) * 10
        return penalty

    def get_neighbor(self, sol):
        new = {k: v.copy() for k, v in sol.items()}
        date, sid = random.choice(list(new.keys()))
        st = next(s for s in self.shift_types if s.id == sid)
        change = random.choice(['add','remove','swap','move'])

        if change == 'add' and len(new[(date,sid)]) < st.max_staff:
            avail = [eid for eid in self.emp_by_id if eid not in new[(date,sid)] and
                     self.is_employee_available(eid, date, st, new)]
            if avail: new[(date,sid)].append(random.choice(avail))

        if change == 'remove' and len(new[(date,sid)]) > st.min_staff:
            new[(date,sid)].remove(random.choice(new[(date,sid)]))

        if change == 'swap':
            (d2, s2_id) = random.choice(list(new.keys()))
            st2 = next(s for s in self.shift_types if s.id == s2_id)
            if new[(date,sid)] and new[(d2,s2_id)]:
                e1 = random.choice(new[(date,sid)])
                e2 = random.choice(new[(d2,s2_id)])
                new[(date,sid)].remove(e1); new[(date,sid)].append(e2)
                new[(d2,s2_id)].remove(e2); new[(d2,s2_id)].append(e1)
                # Validierung zurückziehen bei Konflikt
                if not (self.is_employee_available(e2, date, st, new) and
                        self.is_employee_available(e1, d2, st2, new)):
                    new[(date,sid)].remove(e2); new[(date,sid)].append(e1)
                    new[(d2,s2_id)].remove(e1); new[(d2,s2_id)].append(e2)

        if change == 'move' and new[(date,sid)]:
            eid = random.choice(new[(date,sid)])
            new[(date,sid)].remove(eid)
            d2 = random.choice(self.days)['date']
            s2 = random.choice(self.shift_types)
            if len(new[(d2,s2.id)]) < s2.max_staff and self.is_employee_available(eid, d2, s2, new):
                new[(d2,s2.id)].append(eid)
            else:
                new[(date,sid)].append(eid)

        return new

    def simulated_annealing_logarithmic(self, initial_temp=10000.0, final_temp=1.0,
                                        max_iterations=10000):
        """Simulated Annealing mit logarithmischem Cooling: T = T0 / log(1+k)"""
        current = self.create_initial_solution()
        current_cost = self.evaluate_solution(current)
        best, best_cost = copy.deepcopy(current), current_cost
        T0 = initial_temp

        for k in range(1, max_iterations + 1):
            neighbor = self.get_neighbor(current)
            cost_n = self.evaluate_solution(neighbor)
            delta = cost_n - current_cost

            T = max(final_temp, T0 / math.log(1 + k))

            if delta < 0 or random.random() < math.exp(-delta / T):
                current, current_cost = neighbor, cost_n
                if cost_n < best_cost:
                    best, best_cost = copy.deepcopy(neighbor), cost_n

            if T <= final_temp:
                break

            if k % 1000 == 0:
                self.stdout.write(f"Iter {k}: BestCost={best_cost:.1f}, T={T:.1f}")

        self.stdout.write(f"SA Log fertig. BestCost={best_cost:.1f}")
        return best

    def simulated_annealing_linear(self, initial_temp=10000.0, final_temp=1.0,
                                   max_iterations=10000):
        """Simulated Annealing mit linearem Cooling: T = T0 - beta * k"""
        current = self.create_initial_solution()
        current_cost = self.evaluate_solution(current)
        best, best_cost = copy.deepcopy(current), current_cost

        # Beta so berechnen, dass T bei iters auf final_temp fällt
        beta = (initial_temp - final_temp) / max_iterations
        T = initial_temp

        for k in range(max_iterations):
            neighbor = self.get_neighbor(current)
            cost_n = self.evaluate_solution(neighbor)
            delta = cost_n - current_cost

            if delta < 0 or random.random() < math.exp(-delta / T):
                current, current_cost = neighbor, cost_n
                if cost_n < best_cost:
                    best, best_cost = copy.deepcopy(neighbor), cost_n

            # Lineares Abkühlen
            T = initial_temp - beta * (k + 1)
            if T < final_temp:
                break

            if k % 1000 == 0:
                self.stdout.write(f"Iter {k}: BestCost={best_cost:.1f}, T={T:.1f}")

        self.stdout.write(f"SA Lin fertig. BestCost={best_cost:.1f}")
        return best

    def simulated_annealing_exponential(self, initial_temp=10000.0, final_temp=1.0,
                                        cooling_rate=0.995, max_iterations=10000):
        """Simulated Annealing mit exponentiellem Cooling: T = T * alpha"""
        # Initialisierung
        current = self.create_initial_solution()
        current_cost = self.evaluate_solution(current)
        best, best_cost = copy.deepcopy(current), current_cost
        T = initial_temp

        for i in range(max_iterations):
            neighbor = self.get_neighbor(current)
            cost_n = self.evaluate_solution(neighbor)
            delta = cost_n - current_cost

            # Akzeptanzkriterium
            if delta < 0 or random.random() < math.exp(-delta / T):
                current, current_cost = neighbor, cost_n
                if cost_n < best_cost:
                    best, best_cost = copy.deepcopy(neighbor), cost_n

            # Exponentielles Abkühlen
            T *= cooling_rate
            if T < final_temp:
                break

            # Debug-Output alle 1000 Schritte
            if i % 1000 == 0:
                self.stdout.write(f"Iter {i}: BestCost={best_cost:.1f}, T={T:.1f}")

        self.stdout.write(f"SA Exp fertig. BestCost={best_cost:.1f}")
        return best

    def simulated_annealing(self):
        sol = self.create_initial_solution()
        cost = self.evaluate_solution(sol)
        best_sol, best_cost = copy.deepcopy(sol), cost

        T, T_min, alpha = 10000.0, 1.0, 0.995
        iters = 10000
        for i in range(iters):
            nbr = self.get_neighbor(sol)
            c2 = self.evaluate_solution(nbr)
            d = c2 - cost
            if d < 0 or random.random() < math.exp(-d/T):
                sol, cost = nbr, c2
                if cost < best_cost:
                    best_sol, best_cost = copy.deepcopy(sol), cost

            T *= alpha
            if T < T_min: break
            if i % 1000 == 0:
                self.stdout.write(f"Iter {i}: BestCost={best_cost:.1f}, T={T:.1f}")
        self.stdout.write(f"SA fertig. BestCost={best_cost:.1f}")
        return best_sol

    def save_solution(self, sol):
        schedule, kpis = [], {
            'total_assignments':0, 'employee_stats':{},
            'shift_coverage':defaultdict(int), 'fairness_metrics':{}
        }
        emp_hrs, emp_cnt = defaultdict(int), defaultdict(int)
        for (d, sid), eids in sol.items():
            st = next(s for s in self.shift_types if s.id == sid)
            for eid in eids:
                emp = self.emp_by_id[eid]
                ScheduleEntry.objects.create(employee=emp, date=d, shift_type=st, archived=False)
                schedule.append({
                    'employee_id':eid, 'employee_name':emp.name,
                    'date':d.isoformat(), 'shift_id':sid,
                    'shift_name':st.name, 'shift_duration':st.duration
                })
                emp_hrs[eid] += st.duration
                emp_cnt[eid] += 1
                kpis['total_assignments'] += 1
                kpis['shift_coverage'][st.name] += 1
        # # Stats
        # for emp in self.employees:
        #     h = emp_hrs[emp.id]
        #     kpis['employee_stats'][emp.id] = {
        #         'name':emp.name, 'total_hours':h,
        #         'total_shifts':emp_cnt[emp.id], 'max_hours_per_week':emp.max_hours_per_week,
        #         'utilization_rate':(h/(52*emp.max_hours_per_week)*100) if emp.max_hours_per_week>0 else 0
        #     }
        # hrs = list(emp_hrs.values())
        # if hrs:
        #     avg = sum(hrs)/len(hrs)
        #     kpis['fairness_metrics'] = {
        #         'average_hours':avg, 'min_hours':min(hrs), 'max_hours':max(hrs),
        #         'hours_std_dev':math.sqrt(sum((h-avg)**2 for h in hrs)/len(hrs))
        #     }
        # data = {
        #     'schedule':schedule, 'kpis':kpis,
        #     'generation_date':datetime.now().isoformat(),
        #     'algorithm':'Simulated Annealing',
        #     'period':{'start_date':self.start_date.isoformat(),'end_date':self.end_date.isoformat()}
        # }
        # path = 'yearly_schedule_sa.json'
        # with open(path, 'w', encoding='utf-8') as f:
        #     json.dump(data, f, indent=4, ensure_ascii=False)
        # self.stdout.write(self.style.SUCCESS(f"Ergebnis nach {path} exportiert"))
        # self.stdout.write(f"Gesamte Zuweisungen: {kpis['total_assignments']}")
        # if 'average_hours' in kpis['fairness_metrics']:
        #     self.stdout.write(f"Durchschnittliche Stunden: {kpis['fairness_metrics']['average_hours']:.1f}")
        #     self.stdout.write(f"Std. Abweichung: {kpis['fairness_metrics']['hours_std_dev']:.1f}")
