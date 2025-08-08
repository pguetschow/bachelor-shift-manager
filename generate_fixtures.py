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

def generate_absences_32h(year=2025):
    """Generate absence patterns for 32h contracts (20 absences total)."""
    absences = []
    
    # Christmas holidays (5 days)
    christmas_start = date(year, 12, 24)
    for i in range(5):
        absences.append((christmas_start + timedelta(days=i)).strftime('%Y-%m-%d'))
    
    # Summer vacation (10 days)
    summer_month = random.choice([6, 7, 8])
    summer_start = date(year, summer_month, random.randint(1, 20))
    for i in range(10):
        vacation_date = summer_start + timedelta(days=i)
        if vacation_date.year == year:
            absences.append(vacation_date.strftime('%Y-%m-%d'))
    
    # Easter vacation (3 days)
    easter_start = date(year, 4, random.randint(1, 25))
    for i in range(3):
        absences.append((easter_start + timedelta(days=i)).strftime('%Y-%m-%d'))

    # Remove duplicates and sort
    absences = sorted(list(set(absences)))
    return absences

def generate_absences_40h(year=2025):
    """Generate absence patterns for 40h contracts (27 absences total)."""
    absences = []
    
    # Christmas holidays (7 days)
    christmas_start = date(year, 12, 22)
    for i in range(7):
        absences.append((christmas_start + timedelta(days=i)).strftime('%Y-%m-%d'))
    
    # Summer vacation (15 days)
    summer_month = random.choice([6, 7, 8])
    summer_start = date(year, summer_month, random.randint(1, 15))
    for i in range(15):
        vacation_date = summer_start + timedelta(days=i)
        if vacation_date.year == year:
            absences.append(vacation_date.strftime('%Y-%m-%d'))
    
    # Easter vacation (3 days)
    easter_start = date(year, 4, random.randint(1, 25))
    for i in range(3):
        absences.append((easter_start + timedelta(days=i)).strftime('%Y-%m-%d'))

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
        
        # Working hours: 80% full-time (40h), 20% part-time (32h)
        max_hours = 40 if random.random() < 0.8 else 32
        
        # Generate appropriate absences based on contract type
        if max_hours == 32:
            absences = generate_absences_32h()
        else:
            absences = generate_absences_40h()
        
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
                "absences": absences,
                "preferred_shifts": preferred_shifts
            }
        }
        employees.append(employee)
    
    return employees

def generate_optimized_employees(count, start_id=1):
    """Generate optimized employee data with expanded solution space."""
    employees = []
    used_names = set()
    
    # Create a more balanced workforce distribution
    shift_preferences = {
        "EarlyShift": [],
        "LateShift": [], 
        "NightShift": [],
        "flexible": []  # No preferences
    }
    
    for i in range(count):
        # Generate unique name
        while True:
            first_name = random.choice(FIRST_NAMES)
            last_name = random.choice(LAST_NAMES)
            full_name = f"{first_name} {last_name}"
            if full_name not in used_names:
                used_names.add(full_name)
                break
        
        # Working hours: 80% full-time (40h), 20% part-time (32h)
        if random.random() < 0.8:  # 80% full-time
            max_hours = 40
            absences = generate_absences_40h()
        else:
            max_hours = 32
            absences = generate_absences_32h()
        
        # More flexible shift preferences to expand solution space
        all_shifts = ["EarlyShift", "LateShift", "NightShift"]
        preference_choice = random.random()
        
        if preference_choice < 0.4:  # 40% have no preference (increased from 30%)
            preferred_shifts = []
            shift_preferences["flexible"].append(i)
        elif preference_choice < 0.7:  # 30% prefer one shift
            shift = random.choice(all_shifts)
            preferred_shifts = [shift]
            shift_preferences[shift].append(i)
        else:  # 30% prefer two shifts
            preferred_shifts = random.sample(all_shifts, 2)
            for shift in preferred_shifts:
                shift_preferences[shift].append(i)
        
        employee = {
            "model": "rostering_app.employee",
            "pk": start_id + i,
            "fields": {
                "name": full_name,
                "max_hours_per_week": max_hours,
                "absences": absences,
                "preferred_shifts": preferred_shifts,
                "company": 4  # bigger_company
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

# Generate optimized bigger_company employees (70 employees)
bigger_company_employees = generate_optimized_employees(70, start_id=4001)
with open('rostering_app/fixtures/bigger_company/employees.json', 'w', encoding='utf-8') as f:
    json.dump(bigger_company_employees, f, indent=2, ensure_ascii=False)

print("Fixtures generated successfully!")
print(f"Medium company: {len(medium_employees)} employees")
print(f"Large company: {len(large_employees)} employees")
print(f"Bigger company (optimized): {len(bigger_company_employees)} employees")
