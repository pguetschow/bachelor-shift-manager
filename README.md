# Readme
## Install Dependencies:
Make sure you have installed Django, PuLP, pandas, matplotlib, and seaborn. 

`pip install django pulp pandas matplotlib seaborn`

## Setup

`python manage.py createsuperuser`

`python manage.py runserver`

## Migrations:
Run the following commands to create and apply migrations:

`python manage.py makemigrations`

`python manage.py makemigrations rostering_app`

`python manage.py migrate`

## Load Fixtures:
Load the employee data

`python manage.py loaddata employees.json`

`python manage.py loaddata shift_types.json`

## Generate Schedule:
Run the management command to archive any previous schedule and generate a new one

`python manage.py generate_schedule_linear`

`python manage.py generate_schedule_heuristic`

`python manage.py generate_schedule_genetic`

## View the Schedule:
Start the Django development server and navigate to http://127.0.0.1:8000/schedule/

`python manage.py runserver`


## Genetic Algorithm

### Candidate Representation:
Each candidate is a dictionary mapping a tuple (day, shift_id) to a list of employee IDs assigned to that shift.

### Population Initialization:
The create_candidate function generates a candidate by iterating over the fixture month days (28 days starting 2025‑02‑01) and, for each shift, randomly selecting a number of employees (while avoiding employees who are absent on that day or already assigned).

### Fitness Function:
The fitness function assigns penalties for:

- Fewer employees than the shift’s minimum requirement.
- More employees than the shift’s maximum allowed.
- An employee assigned to more than one shift on the same day.
- An employee assigned on a day when they are absent.

### Crossover and Mutation:

Crossover: For each day and shift, the child candidate takes the assignment from one parent with a 50% chance.

Mutation: A random day and shift are selected, and a new random assignment is generated for that shift.

### Evolution:
The genetic algorithm evolves the population over a set number of generations, selects the best candidate, and finally writes the schedule entries to the database.