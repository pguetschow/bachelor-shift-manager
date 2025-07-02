# Shift Manager - Employee Scheduling System

A modern employee scheduling system with a Django backend and Vue.js frontend, featuring advanced scheduling algorithms, analytics, and a responsive UI.

## 🚀 Features
- Multi-company support
- Advanced scheduling algorithms (Linear Programming, Genetic Algorithm, Simulated Annealing)
- Employee and shift management
- Real-time analytics and algorithm comparison
- Mobile-responsive design
- Dockerized for easy deployment

## 📝 Prerequisites
- Python 3.8+
- Node.js 16+
- npm or yarn
- Docker 20.10+ (for containerized setup)

## ⚡ Quick Start

### Docker (Recommended)
```bash
# Clone the repository
git clone <repository-url>
cd shift-manager

# Start in development mode
./scripts/start.sh          # Linux/macOS
scripts\start.bat           # Windows

# Or use Docker Compose directly
docker-compose up -d --build
```

### Local Development
#### Backend
```bash
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py loaddata rostering_app/fixtures/companies.json
python manage.py runserver
```
#### Frontend
```bash
npm install
npm run dev
```

## 🏗️ Project Structure
```
shift-manager/
├── src/                # Vue.js frontend
│   ├── components/     # UI components
│   ├── views/          # Pages
│   ├── stores/         # Pinia state
│   ├── services/       # API services
│   └── assets/         # Static assets
├── rostering_app/      # Django app
│   ├── models.py       # Data models
│   ├── views.py        # API views
│   └── fixtures/       # Sample data
├── scheduling_core/    # Scheduling algorithms
├── Dockerfile*         # Docker configs
├── docker-compose*.yml # Docker Compose
└── requirements.txt    # Python dependencies
```

## 🎯 Usage
- Access the app at http://localhost:3000 (frontend) and http://localhost:8000 (backend API)
- Django Admin: http://localhost:8000/admin
- Main workflow:
  1. Create/select a company
  2. Add employees and shifts
  3. Generate schedules using different algorithms
  4. Compare results and analyze statistics

## 🔑 Key API Endpoints
- `GET /api/companies/` - List companies
- `GET /api/companies/{id}/algorithms/` - Available algorithms
- `GET /api/companies/{id}/schedule/` - Schedule data
- `GET /api/companies/{id}/employees/` - Employees
- `GET /api/companies/{id}/shifts/` - Shifts
- `GET /api/companies/{id}/analytics/` - Algorithm KPIs

## 🛠️ Troubleshooting & Deployment
- If ports are in use, change them in `docker-compose.yml` or `vite.config.js`
- For production, use `docker-compose.prod.yml` and set environment variables as needed
- To rebuild: `docker-compose build --no-cache`
- For SSR, use `npm run build:ssr` and serve with Node or Django management command



## 🐳 Docker Deployment

### Development
```bash
docker-compose up -d
```

### Production
```bash
# With SSL certificates
./scripts/start.sh prod

# Manual setup
docker-compose -f docker-compose.prod.yml up -d
```

### Docker Commands
```bash
# View logs
docker-compose logs -f

# Access backend shell
docker-compose exec backend python manage.py shell

# Run Django commands
docker-compose exec backend python manage.py migrate
docker-compose exec backend python manage.py createsuperuser

# Scale services
docker-compose -f docker-compose.prod.yml up -d --scale backend=3
```