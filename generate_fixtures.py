"""Generate employee fixtures for medium and large companies."""
import json
import random
from datetime import date, timedelta

# German first names
FIRST_NAMES = [
    "Alexander", "Andrea", "Andreas", "Angelika", "Anna", "Bernd", "Birgit", 
    "Christian", "Christina", "Claudia", "Daniel", "Daniela", "Dennis", "Diana",
    "Dirk", "Doris", "Eva", "Felix", "Frank", "Franziska", "Georg", "Gisela",
    "Hans", "Heike", "Helmut", "Ingrid", "Jan", "Jana", "Jens", "Jessica",
    "Joachim", "Julia", "Jürgen", "Karin", "Karl", "Katharina", "Klaus", "Laura",
    "Lisa", "Manfred", "Maria", "Mario", "Markus", "Martin", "Martina", "Matthias",
    "Michael", "Michaela", "Monika", "Nadine", "Nicole", "Nina", "Oliver", "Patrick",
    "Peter", "Petra", "Ralf", "Regina", "Rene", "Robert", "Sabine", "Sandra",
    "Sebastian", "Silke", "Simon", "Stefan", "Stefanie", "Susanne", "Sven", "Thomas",
    "Thorsten", "Tim", "Tobias", "Torsten", "Ulrich", "Ulrike", "Ursula", "Ute",
    "Uwe", "Vanessa", "Verena", "Walter", "Werner", "Wolfgang"
]

# German last names
LAST_NAMES = [
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner",
    "Becker", "Schulz", "Hoffmann", "Schäfer", "Koch", "Bauer", "Richter",
    "Klein", "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann", "Braun",
    "Krüger", "Hofmann", "Hartmann", "Lange", "Schmitt", "Werner", "Schmitz",
    "Krause", "Meier", "Lehmann", "Schmid", "Schulze", "Maier", "Köhler",
    "Herrmann", "König", "Walter", "Mayer", "Huber", "Kaiser", "Fuchs",
    "Peters", "Lang", "Scholz", "Möller", "Weiß", "Jung", "Hahn", "Schubert",
    "Vogel", "Friedrich", "Keller", "Günther", "Frank", "Berger", "Winkler",
    "Roth", "Beck", "Lorenz", "Baumann", "Franke", "Albrecht", "Schuster",
    "Simon", "Ludwig", "Böhm", "Winter", "Kraus", "Martin", "Schumacher",
    "Krämer", "Vogt", "Stein", "Jäger", "Otto", "Sommer", "Groß", "Seidel",
    "Heinrich", "Brandt", "Haas", "Schreiber", "Graf", "Dietrich", "Ziegler"
]

def generate_absences(year=2025):
    """Generate realistic absence patterns."""
    absences = []
    
    # Christmas holidays
    christmas_start = date(year, 12, 22)
    for i in range(random.randint(5, 10)):
        absences.append((christmas_start + timedelta(days=i)).strftime('%Y-%m-%d'))
    
    # Summer vacation (2-3 weeks)
    summer_month = random.choice([6, 7, 8])
    summer_start = date(year, summer_month, random.randint(1, 15))
    vacation_length = random.randint(10, 21)
    for i in range(vacation_length):
        vacation_date = summer_start + timedelta(days=i)
        if vacation_date.year == year:
            absences.append(vacation_date.strftime('%Y-%m-%d'))
    
    # Easter vacation (1 week)
    easter_start = date(year, 4, random.randint(1, 20))
    for i in range(random.randint(5, 7)):
        absences.append((easter_start + timedelta(days=i)).strftime('%Y-%m-%d'))
    
    # Random sick days (5-10 per year)
    for _ in range(random.randint(5, 10)):
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        absences.append(date(year, month, day).strftime('%Y-%m-%d'))
    
    # Remove duplicates and sort
    absences = sorted(list(set(absences)))
    return absences

def generate_employees(count, start_id=1):
    """Generate employee data."""
    employees = []
    used_names = set()
    
    for i in range(count):
        # Generate unique name
        while True:
            first_name = random.choice(FIRST_NAMES)
            last_name = random.choice(LAST_NAMES)
            full_name = f"{first_name} {last_name}"
            if full_name not in used_names:
                used_names.add(full_name)
                break
        
        # Working hours: 70% full-time (40h), 30% part-time (32h)
        max_hours = 40 if random.random() < 0.7 else 32
        
        # Shift preferences
        all_shifts = ["EarlyShift", "LateShift", "NightShift"]
        if random.random() < 0.3:
            # 30% have no preference
            preferred_shifts = []
        elif random.random() < 0.5:
            # 35% prefer one shift
            preferred_shifts = [random.choice(all_shifts)]
        else:
            # 35% prefer two shifts
            preferred_shifts = random.sample(all_shifts, 2)
        
        employee = {
            "model": "rostering_app.employee",
            "pk": start_id + i,
            "fields": {
                "name": full_name,
                "max_hours_per_week": max_hours,
                "absences": generate_absences(),
                "preferred_shifts": preferred_shifts
            }
        }
        employees.append(employee)
    
    return employees

# Generate medium company employees (30 employees)
medium_employees = generate_employees(30, start_id=1)
with open('rostering_app/fixtures/medium_company/employees.json', 'w', encoding='utf-8') as f:
    json.dump(medium_employees, f, indent=2, ensure_ascii=False)

# Generate large company employees (100 employees)
large_employees = generate_employees(100, start_id=1)
with open('rostering_app/fixtures/large_company/employees.json', 'w', encoding='utf-8') as f:
    json.dump(large_employees, f, indent=2, ensure_ascii=False)

print("Fixtures generated successfully!")
print(f"Medium company: {len(medium_employees)} employees")
print(f"Large company: {len(large_employees)} employees")
