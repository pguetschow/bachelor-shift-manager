# Use Node.js 18 as base image
FROM node:18-slim

# Install Python and system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-venv \
        python3-pip \
        gcc \
        g++ \
        libpq-dev \
        libfreetype6 \
        libpng-dev \
        pkg-config \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables (NODE_ENV später setzen!)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=rostering_project.settings

# Set work directory
WORKDIR /app

# Install Node.js dependencies and build Vue.js app
COPY package*.json ./
RUN npm install

COPY src/ ./src/
COPY vite.config.js ./
COPY index.html ./

ENV NODE_ENV=production

# Build SSR version of the frontend
RUN npm run build:ssr

# Also build the regular version for static serving
RUN npm run build

# Install Python dependencies in a virtual environment
COPY requirements.txt ./
RUN python3.11 -m venv /opt/venv \
    && . /opt/venv/bin/activate \
    && pip install --no-cache-dir -r requirements.txt

# Set virtualenv as default Python
ENV PATH="/opt/venv/bin:$PATH"

# Copy Django project
COPY rostering_app/ ./rostering_app/
COPY rostering_project/ ./rostering_project/
COPY scheduling_core/ ./scheduling_core/
COPY manage.py ./

# Ensure dist directory is available (in case it was built locally)
COPY dist/ ./dist/ 2>/dev/null || true

# Copy start.sh script and make it executable
COPY start.sh ./
RUN chmod +x start.sh

# Collect static files
RUN python manage.py collectstatic --noinput

# Create a non-root user
RUN adduser --disabled-password --gecos '' appuser
RUN chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Use start.sh script instead of directly running Gunicorn
CMD ["./start.sh"]
