#!/bin/bash

# Set production environment variable for Django
export DJANGO_PRODUCTION=1

# Exit on any error
set -e

echo "Starting Shift Manager application..."

# Run database migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# Load fixtures if database is empty
echo "Checking if fixtures need to be loaded..."
if [ $(python manage.py shell -c "from rostering_app.models import Company; print(Company.objects.count())" 2>/dev/null) -eq 0 ]; then
    echo "Database is empty, loading fixtures..."
    python manage.py load_fixtures
else
    echo "Database already has data, skipping fixture loading."
fi

# Start the Django application with Gunicorn
echo "Starting Gunicorn server..."
exec gunicorn rostering_project.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120