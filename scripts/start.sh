#!/bin/bash

# Start script for Shift Manager
set -e

echo "🚀 Starting Shift Manager..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create necessary directories
mkdir -p data
mkdir -p static
mkdir -p ssl

# Check if we're in production mode
if [ "$1" = "prod" ]; then
    echo "🏭 Starting in PRODUCTION mode..."
    
    # Check for SSL certificates
    if [ ! -f "ssl/cert.pem" ] || [ ! -f "ssl/key.pem" ]; then
        echo "⚠️  SSL certificates not found. Generating self-signed certificates..."
        mkdir -p ssl
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout ssl/key.pem -out ssl/cert.pem \
            -subj "/C=DE/ST=State/L=City/O=Organization/CN=localhost"
    fi
    
    # Set production environment variables
    export SECRET_KEY=${SECRET_KEY:-$(openssl rand -hex 32)}
    export ALLOWED_HOSTS=${ALLOWED_HOSTS:-localhost,127.0.0.1,0.0.0.0}
    
    # Start production services
    docker-compose -f docker-compose.prod.yml up -d --build
    
    echo "✅ Production services started!"
    echo "🌐 Frontend: http://localhost"
    echo "🔒 HTTPS: https://localhost"
    echo "🔧 Backend API: http://localhost:8000"
    
else
    echo "🔧 Starting in DEVELOPMENT mode..."
    
    # Start development services
    docker-compose up -d --build
    
    echo "✅ Development services started!"
    echo "🌐 Frontend: http://localhost:3000"
    echo "🔧 Backend API: http://localhost:8000"
fi

echo ""
echo "📊 To view logs: docker-compose logs -f"
echo "🛑 To stop: docker-compose down"
echo "🧹 To clean up: docker-compose down -v --remove-orphans" 