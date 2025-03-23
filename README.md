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

## Create Shift Types:
Either use the Django admin or create a data migration / fixture to add the three shift types (EarlyShift, LateShift, NightShift) with their start/end times and staff constraints.

## Generate Schedule:
Run the management command to archive any previous schedule and generate a new one

`python manage.py generate_schedule`

## View the Schedule:
Start the Django development server and navigate to http://127.0.0.1:8000/schedule/

`python manage.py runserver`