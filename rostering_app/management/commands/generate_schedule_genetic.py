from django.core.management.base import BaseCommand
from rostering_app.models import Employee, ShiftType, ScheduleEntry
from datetime import date, timedelta
import random
import copy

class Command(BaseCommand):
    help = "Generate schedule using a genetic algorithm heuristic approach for a full year with weekly constraints"

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
            help="Number of generations (default: 50)"
        )
        parser.add_argument(
            '--mutation_rate',
            type=float,
            default=0.1,
            help="Mutation rate (default: 0.1)"
        )

    def handle(self, *args, **options):
        population_size = options.get('population_size')
        generations = options.get('generations')
        mutation_rate = options.get('mutation_rate')
        self.stdout.write(
            f"Running GA with population_size={population_size}, generations={generations}, mutation_rate={mutation_rate}")

        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())
        # Define scheduling period: full year from 2024-01-01 to 2024-12-31.
        start_date = date(2024, 1, 1)
        end_date = date(2024, 12, 31)
        num_days = (end_date - start_date).days + 1
        days = [start_date + timedelta(days=i) for i in range(num_days)]

        population = [self.create_candidate(days, shift_types, employees) for _ in range(population_size)]
        for gen in range(generations):
            scored = [(self.fitness(candidate, days, shift_types, employees), candidate) for candidate in population]
            scored.sort(key=lambda x: x[0])
            survivors = [candidate for (score, candidate) in scored[:population_size // 2]]
            new_population = survivors.copy()
            while len(new_population) < population_size:
                parent1 = random.choice(survivors)
                parent2 = random.choice(survivors)
                child = self.crossover(parent1, parent2, days, shift_types)
                if random.random() < mutation_rate:
                    child = self.mutate(child, days, shift_types, employees)
                new_population.append(child)
            population = new_population

        final_scored = [(self.fitness(candidate, days, shift_types, employees), candidate) for candidate in population]
        final_scored.sort(key=lambda x: x[0])
        best_candidate = final_scored[0][1]
        for day in days:
            for shift in shift_types:
                key = (day, shift.id)
                assigned_emp_ids = best_candidate.get(key, [])
                for emp_id in assigned_emp_ids:
                    emp = next((e for e in employees if e.id == emp_id), None)
                    if emp:
                        ScheduleEntry.objects.create(
                            employee=emp,
                            date=day,
                            shift_type=shift,
                            archived=False
                        )
        self.stdout.write(self.style.SUCCESS("Genetic algorithm yearly schedule generated successfully."))

    def create_candidate(self, days, shift_types, employees):
        """
        Create a candidate solution.
        The candidate is a dict with keys (day, shift_id) and values: a list of employee IDs.
        For each day, it assigns employees for each shift (if available) while trying to respect the staffing constraints.
        """
        candidate = {}
        for day in days:
            assigned_today = set()
            for shift in shift_types:
                key = (day, shift.id)
                # Get employees available on this day and not yet assigned today.
                available = [emp.id for emp in employees if day.isoformat() not in emp.absences and emp.id not in assigned_today]
                if available:
                    num_to_assign = random.randint(shift.min_staff, min(shift.max_staff, len(available)))
                    assigned = random.sample(available, num_to_assign)
                else:
                    assigned = []
                candidate[key] = assigned
                assigned_today.update(assigned)
        return candidate

    def fitness(self, candidate, days, shift_types, employees):
        """
        Compute a fitness score for the candidate.
        Lower score is better.
        Penalties:
          - For each shift, if the number of assigned employees is less than min_staff, penalty = 1000 per missing employee.
          - For each shift, if the number exceeds max_staff, penalty = 1000 per extra employee.
          - For each employee assigned to more than one shift per day, penalty = 500 per duplicate.
          - For each employee assigned on a day when they are absent, penalty = 1000 per violation.
          - For each employee exceeding weekly hours (based on shift.get_duration()), penalty = 1000 per extra hour.
        """
        penalty = 0
        daily_assignments = {}
        # Accumulate weekly hours per employee: key = (employee.id, (iso_year, iso_week))
        weekly_hours = {}

        for day in days:
            week_key = day.isocalendar()[:2]  # (iso_year, iso_week)
            day_assignments = {}
            for shift in shift_types:
                key = (day, shift.id)
                assigned = candidate.get(key, [])
                count = len(assigned)
                if count < shift.min_staff:
                    penalty += (shift.min_staff - count) * 1000
                if count > shift.max_staff:
                    penalty += (count - shift.max_staff) * 1000
                for emp_id in assigned:
                    emp = next((e for e in employees if e.id == emp_id), None)
                    if emp and day.isoformat() in emp.absences:
                        penalty += 1000
                    day_assignments.setdefault(emp_id, 0)
                    day_assignments[emp_id] += 1
                    # Accumulate weekly hours.
                    weekly_hours[(emp_id, week_key)] = weekly_hours.get((emp_id, week_key), 0) + shift.get_duration()
                    daily_assignments.setdefault(emp_id, 0)
                    daily_assignments[emp_id] += 1
            # Penalize duplicate assignments on the same day.
            for emp_id, count in day_assignments.items():
                if count > 1:
                    penalty += (count - 1) * 500

        # Penalize employees who exceed their weekly hours.
        for (emp_id, week_key), hours in weekly_hours.items():
            emp = next((e for e in employees if e.id == emp_id), None)
            if emp and hours > emp.max_hours_per_week:
                penalty += (hours - emp.max_hours_per_week) * 1000

        # Extra term: penalize large differences in total shifts assigned per employee.
        if daily_assignments:
            avg_shifts = sum(daily_assignments.values()) / len(daily_assignments)
            for emp_id, count in daily_assignments.items():
                penalty += abs(count - avg_shifts) * 100
        return penalty

    def crossover(self, parent1, parent2, days, shift_types):
        """
        Perform crossover between two candidate solutions.
        For each day and shift, randomly choose the assignment from one of the parents.
        """
        child = {}
        for day in days:
            for shift in shift_types:
                key = (day, shift.id)
                if random.random() < 0.5:
                    child[key] = parent1.get(key, []).copy()
                else:
                    child[key] = parent2.get(key, []).copy()
        return child

    def mutate(self, candidate, days, shift_types, employees):
        """
        Mutate a candidate solution by reassigning a random shift.
        """
        mutant = copy.deepcopy(candidate)
        day = random.choice(days)
        shift = random.choice(shift_types)
        key = (day, shift.id)
        available = [emp.id for emp in employees if day.isoformat() not in emp.absences]
        if available:
            num_to_assign = random.randint(shift.min_staff, min(shift.max_staff, len(available)))
            mutant[key] = random.sample(available, num_to_assign)
        return mutant
