# Use Node.js 18 as base image
FROM node:18-slim

# Install Python and system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-dev \
        python3-pip \
        gcc \
        g++ \
        libpq-dev \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=rostering_project.settings
ENV NODE_ENV=production

# Set work directory
WORKDIR /app

# Install Node.js dependencies and build Vue.js app
COPY package*.json ./
RUN npm ci --only=production

# Copy Vue.js source and build
COPY src/ ./src/
COPY vite.config.js ./
COPY index.html ./
RUN npm run build:ssr

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy Django project
COPY rostering_app/ ./rostering_app/
COPY rostering_project/ ./rostering_project/
COPY manage.py ./

# Collect static files
RUN python3 manage.py collectstatic --noinput

# Create a non-root user
RUN adduser --disabled-password --gecos '' appuser
RUN chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Run the application with Gunicorn
CMD ["gunicorn", "rostering_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"] 