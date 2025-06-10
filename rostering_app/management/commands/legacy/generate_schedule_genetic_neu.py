from datetime import datetime, timedelta
from collections import defaultdict
import random

from django.core.management.base import BaseCommand
from rostering_app.models import Employee, ShiftType, ScheduleEntry


class GeneticScheduler:
    """
    Ein heuristischer Planer, der einen genetischen Algorithmus verwendet, um für einen gegebenen
    Monatszeitraum (mit Tagen und zugehörigen Schichtmöglichkeiten) einen Dienstplan zu erzeugen.

    Die Lösung (Chromosom) wird als Dictionary modelliert:
      Schlüssel: (employee.id, day_date)
      Wert: shift.id oder None (keine Schicht)
    """

    def __init__(self, employees, shift_types, month_days, last_day_assignment, carryover):
        self.employees = employees
        self.shift_types = shift_types
        self.month_days = month_days  # Liste von Dictionaries: {'date': date, 'shifts': [shift, ...]}
        self.last_day_assignment = last_day_assignment  # {employee.id: Shift} aus dem Vormonat
        self.carryover = carryover  # {employee.id: Stunden}

        # GA-Parameter (diese Werte sollten ggf. feinabgestimmt werden)
        self.population_size = 20
        self.generations = 10
        self.mutation_rate = 0.1
        self.crossover_rate = 0.7

    def initialize_population(self):
        """
        Erzeugt die initiale Population als Liste von Individuen (Lösungen).
        """
        population = []
        for _ in range(self.population_size):
            individual = {}
            for day in self.month_days:
                date = day['date']
                for employee in self.employees:
                    # Mitarbeiter-Absenz berücksichtigen
                    if date.isoformat() in employee.absences:
                        individual[(employee.id, date)] = None
                    else:
                        # Zufällige Zuweisung: Auswahl aus den verfügbaren Schichten plus Option "kein Einsatz"
                        assignment = random.choice(day['shifts'] + [None])
                        if assignment is None:
                            individual[(employee.id, date)] = None
                        else:
                            individual[(employee.id, date)] = assignment.id
            population.append(individual)
        return population

    def fitness(self, individual):
        """
        Bewertet ein Individuum anhand von Strafkosten (Penalties) und Boni.
        Eine hohe Fitness entspricht einer guten Lösung.
        """
        penalty = 0
        bonus = 0

        # (a) Staffing-Constraints: Für jeden Tag und Schicht wird geprüft, ob die
        # Anzahl der eingesetzten Mitarbeiter im zulässigen Bereich liegt.
        schedule_by_day = defaultdict(lambda: defaultdict(int))
        for day in self.month_days:
            date = day['date']
            for employee in self.employees:
                shift_id = individual.get((employee.id, date))
                if shift_id is not None:
                    schedule_by_day[date][shift_id] += 1

        for day in self.month_days:
            date = day['date']
            for shift in day['shifts']:
                count = schedule_by_day[date].get(shift.id, 0)
                if count < shift.min_staff:
                    penalty += 1000 * (shift.min_staff - count)  # starke Strafe bei Unterbesetzung
                if count > shift.max_staff:
                    penalty += 1000 * (count - shift.max_staff)  # starke Strafe bei Überbesetzung

        # (b) Ruhezeiten (11-Stunden-Pause) zwischen aufeinanderfolgenden Tagen
        for employee in self.employees:
            for i in range(len(self.month_days) - 1):
                day = self.month_days[i]
                next_day = self.month_days[i + 1]
                shift_id_today = individual.get((employee.id, day['date']))
                shift_id_next = individual.get((employee.id, next_day['date']))
                shift_today = next((s for s in day['shifts'] if s.id == shift_id_today), None)
                shift_next = next((s for s in next_day['shifts'] if s.id == shift_id_next), None)
                if shift_today is not None and shift_next is not None:
                    if shift_today.name == "LateShift" and shift_next.name == "EarlyShift":
                        penalty += 1000
                    if shift_today.name == "NightShift" and shift_next.name in ["EarlyShift", "LateShift"]:
                        penalty += 1000

        # (c) Übergangs-Constraints vom Vormonat
        first_day = self.month_days[0]
        for employee in self.employees:
            last_shift = self.last_day_assignment.get(employee.id)
            shift_id_first = individual.get((employee.id, first_day['date']))
            first_shift = next((s for s in first_day['shifts'] if s.id == shift_id_first), None)
            if last_shift is not None and first_shift is not None:
                if last_shift.name == "LateShift" and first_shift.name == "EarlyShift":
                    penalty += 1000
                if last_shift.name == "NightShift" and first_shift.name in ["EarlyShift", "LateShift"]:
                    penalty += 1000

        # (d) Wöchentliche maximale Arbeitszeit (nur komplette Wochen im aktuellen Monat)
        weeks = defaultdict(list)
        for day in self.month_days:
            iso_year, iso_week, _ = day['date'].isocalendar()
            weeks[(iso_year, iso_week)].append(day)
        for employee in self.employees:
            for week, days in weeks.items():
                # Prüfen, ob alle Tage dieser Woche im aktuellen Monat liegen
                if all(d['date'].month == self.month_days[0]['date'].month for d in days):
                    total_hours = 0
                    for day in days:
                        shift_id = individual.get((employee.id, day['date']))
                        if shift_id is not None:
                            shift = next((s for s in day['shifts'] if s.id == shift_id), None)
                            if shift is not None:
                                total_hours += shift.get_duration()
                    if total_hours > employee.max_hours_per_week:
                        penalty += 1000 * (total_hours - employee.max_hours_per_week)

        # (e) Fairness: Abweichung von der angestrebten monatlichen Arbeitszeit inkl. Carry‑Over.
        for employee in self.employees:
            monthly_target = employee.max_hours_per_week * (len(self.month_days) / 7) + self.carryover.get(employee.id,
                                                                                                           0)
            total_hours = 0
            for day in self.month_days:
                shift_id = individual.get((employee.id, day['date']))
                if shift_id is not None:
                    shift = next((s for s in day['shifts'] if s.id == shift_id), None)
                    if shift is not None:
                        total_hours += shift.get_duration()
            deviation = abs(total_hours - monthly_target)
            penalty += 10 * deviation  # geringere Gewichtung für Fairness

        # (f) Bonus für bevorzugte Schichten
        for day in self.month_days:
            date = day['date']
            for employee in self.employees:
                shift_id = individual.get((employee.id, date))
                if shift_id is not None:
                    shift = next((s for s in day['shifts'] if s.id == shift_id), None)
                    if shift is not None and shift.name in employee.preferred_shifts:
                        bonus += 5

        # Hier kombinieren wir die Boni und Strafkosten.
        # Da wir eine Maximierungsproblematik betrachten, geben wir den Netto-Bonus zurück.
        return bonus - penalty

    def selection(self, population, fitnesses):
        """
        Turnierselektion: Aus zufällig gewählten Gruppen (Turnieren) wird das beste Individuum ausgewählt.
        """
        selected = []
        tournament_size = 3
        for _ in range(len(population)):
            participants = random.sample(list(zip(population, fitnesses)), tournament_size)
            winner = max(participants, key=lambda x: x[1])[0]
            selected.append(winner)
        return selected

    def crossover(self, parent1, parent2):
        """
        Einpunkt-Crossover: Es wird entlang der zeitlichen Reihenfolge (Tage) ein Schnittpunkt gewählt
        und die Gene (Zuweisungen) zwischen den Eltern ausgetauscht.
        """
        child1 = {}
        child2 = {}
        days_sorted = sorted(self.month_days, key=lambda d: d['date'])
        point = random.randint(1, len(days_sorted) - 1)
        for i, day in enumerate(days_sorted):
            date = day['date']
            for employee in self.employees:
                if i < point:
                    child1[(employee.id, date)] = parent1[(employee.id, date)]
                    child2[(employee.id, date)] = parent2[(employee.id, date)]
                else:
                    child1[(employee.id, date)] = parent2[(employee.id, date)]
                    child2[(employee.id, date)] = parent1[(employee.id, date)]
        return child1, child2

    def mutate(self, individual):
        """
        Mutation: Für jedes Gen (Mitarbeiter/Tag) wird mit einer bestimmten Wahrscheinlichkeit
        eine zufällige Änderung vorgenommen.
        """
        for day in self.month_days:
            date = day['date']
            for employee in self.employees:
                if random.random() < self.mutation_rate:
                    # Falls der Mitarbeiter an diesem Tag abwesend ist, überspringen.
                    if date.isoformat() in employee.absences:
                        continue
                    assignment = random.choice(day['shifts'] + [None])
                    if assignment is None:
                        individual[(employee.id, date)] = None
                    else:
                        individual[(employee.id, date)] = assignment.id
        return individual

    def run(self):
        """
        Führt den genetischen Algorithmus aus und gibt das beste gefundene Individuum (Lösung)
        sowie dessen Fitness zurück.
        """
        population = self.initialize_population()
        best_individual = None
        best_fitness = float("-inf")
        for gen in range(self.generations):
            fitnesses = [self.fitness(individual) for individual in population]
            # Aktualisiere die bisher beste Lösung
            gen_best_fitness = max(fitnesses)
            if gen_best_fitness > best_fitness:
                best_fitness = gen_best_fitness
                best_individual = population[fitnesses.index(gen_best_fitness)]
            # Selektion
            selected = self.selection(population, fitnesses)
            new_population = []
            # Erzeuge neue Population durch Crossover und Mutation
            while len(new_population) < self.population_size:
                if random.random() < self.crossover_rate and len(selected) >= 2:
                    parent1 = random.choice(selected)
                    parent2 = random.choice(selected)
                    child1, child2 = self.crossover(parent1, parent2)
                    new_population.append(self.mutate(child1))
                    if len(new_population) < self.population_size:
                        new_population.append(self.mutate(child2))
                else:
                    individual = random.choice(selected)
                    new_population.append(self.mutate(individual.copy()))
            population = new_population
            print(f"Generation {gen}: Beste Fitness = {best_fitness}")
        return best_individual, best_fitness


class Command(BaseCommand):
    help = (
        "Erstellt einen Jahresdienstplan (monatlich aufgeteilt) mittels genetischem Algorithmus. "
        "Dabei werden harte (u.a. Mindest-/Maximumbesetzung, Ruhezeiten, Abwesenheiten, "
        "wöchentliche Arbeitszeit) und weiche Ziele (Fairness, Schichtpräferenzen) berücksichtigt."
    )

    def handle(self, *args, **kwargs):
        # Archivierung alter Dienstplaneinträge
        ScheduleEntry.objects.filter(archived=False).update(archived=True)

        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())

        # Jahreszeitraum: 2025-01-01 bis 2025-12-31
        start_date = datetime.strptime('2025-01-01', '%Y-%m-%d').date()
        end_date = datetime.strptime('2025-12-31', '%Y-%m-%d').date()
        num_days = (end_date - start_date).days + 1

        # Erzeuge Liste aller Tage: Jeder Tag enthält alle verfügbaren ShiftTypes.
        days = []
        for i in range(num_days):
            day_date = start_date + timedelta(days=i)
            days.append({'date': day_date, 'shifts': shift_types})

        # Initialisiere Übergangsdaten
        last_day_assignment = {}  # Speichert für jeden Mitarbeiter die letzte Schicht des Vormonats
        carryover = {employee.id: 0 for employee in employees}

        # Durchlaufe alle 12 Monate
        for month in range(1, 13):
            month_days = [day for day in days if day['date'].month == month]
            if not month_days:
                self.stdout.write(self.style.WARNING(
                    f"Kein Planungstag für Monat {month} gefunden, überspringe diesen Monat."
                ))
                continue

            self.stdout.write(f"Starte genetische Planung für Monat {month}...")
            # Instanziiere den genetischen Scheduler
            ga = GeneticScheduler(employees, shift_types, month_days, last_day_assignment, carryover)
            best_schedule, best_fitness = ga.run()
            self.stdout.write(self.style.SUCCESS(f"Monat {month} GA beendet. Beste Fitness: {best_fitness}"))

            # Aktualisiere das Carry‑Over für jeden Mitarbeiter basierend auf den tatsächlich geleisteten Stunden.
            for employee in employees:
                total_hours = 0
                for day in month_days:
                    shift_id = best_schedule.get((employee.id, day['date']))
                    if shift_id is not None:
                        shift = next((s for s in day['shifts'] if s.id == shift_id), None)
                        if shift:
                            total_hours += shift.get_duration()
                monthly_target = employee.max_hours_per_week * (len(month_days) / 7)
                carryover[employee.id] = carryover.get(employee.id, 0) + (total_hours - monthly_target)

            # Schreibe die Zuweisungen des Monats in die Datenbank
            for day in month_days:
                date = day['date']
                for employee in employees:
                    shift_id = best_schedule.get((employee.id, date))
                    if shift_id is not None:
                        shift = next((s for s in day['shifts'] if s.id == shift_id), None)
                        if shift:
                            ScheduleEntry.objects.create(
                                employee=employee,
                                date=date,
                                shift_type=shift,
                                archived=False
                            )

            # Aktualisiere für jeden Mitarbeiter die letzte zugewiesene Schicht am Ende des Monats (für Übergangsregeln)
            last_day = max(month_days, key=lambda d: d['date'])
            for employee in employees:
                shift_id = best_schedule.get((employee.id, last_day['date']))
                if shift_id is not None:
                    shift = next((s for s in last_day['shifts'] if s.id == shift_id), None)
                    if shift:
                        last_day_assignment[employee.id] = shift

            self.stdout.write(self.style.SUCCESS(f"Monat {month} erfolgreich geplant."))

        self.stdout.write(self.style.SUCCESS("Jahresdienstplan mittels genetischem Algorithmus erfolgreich generiert."))
