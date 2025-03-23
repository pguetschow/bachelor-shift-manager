from django.core.management.base import BaseCommand
from rostering_app.models import Employee, ShiftType, ScheduleEntry
from datetime import date, timedelta
import random
import copy

class Command(BaseCommand):
    help = "Generate employee schedule using a genetic algorithm heuristic approach"

    def handle(self, *args, **options):
        self.stdout.write("Generating schedule using genetic algorithm approach...")
        # Archive previous (non-archived) schedule entries.
        ScheduleEntry.objects.filter(archived=False).update(archived=True)

        # Retrieve employees, shift types and define the scheduling period.
        employees = list(Employee.objects.all())
        shift_types = list(ShiftType.objects.all())
        # Define the fixture scheduling period: 28 days starting on 2024-02-01.
        days = [date(2024, 2, 1) + timedelta(days=i) for i in range(28)]

        # Genetic algorithm parameters
        population_size = 40
        generations = 500
        mutation_rate = 0.1

        # Initialize population
        population = [self.create_candidate(days, shift_types, employees) for _ in range(population_size)]

        # Evolve over a number of generations
        for gen in range(generations):
            # Evaluate fitness for each candidate
            scored = [(self.fitness(candidate, days, shift_types, employees), candidate) for candidate in population]
            scored.sort(key=lambda x: x[0])
            best_fitness = scored[0][0]
            self.stdout.write(f"Generation {gen+1}: Best fitness = {best_fitness}")
            # Select the top half of the population as survivors
            survivors = [candidate for (score, candidate) in scored[:population_size//2]]
            # Generate new candidates through crossover and mutation until the population is replenished
            new_population = survivors.copy()
            while len(new_population) < population_size:
                parent1 = random.choice(survivors)
                parent2 = random.choice(survivors)
                child = self.crossover(parent1, parent2, days, shift_types)
                if random.random() < mutation_rate:
                    child = self.mutate(child, days, shift_types, employees)
                new_population.append(child)
            population = new_population

        # Choose the best candidate from the final population
        final_scored = [(self.fitness(candidate, days, shift_types, employees), candidate) for candidate in population]
        final_scored.sort(key=lambda x: x[0])
        best_candidate = final_scored[0][1]

        # Save the best candidate solution to the database
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
        self.stdout.write(self.style.SUCCESS("Genetic algorithm schedule generated successfully."))

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
        """
        penalty = 0
        daily_assignments = {}
        for day in days:
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
                    daily_assignments.setdefault(emp_id, 0)
                    daily_assignments[emp_id] += 1
            # Penalize duplicate assignments on the same day.
            for emp_id, count in day_assignments.items():
                if count > 1:
                    penalty += (count - 1) * 500
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
