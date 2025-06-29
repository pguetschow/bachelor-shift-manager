# Shift Manager - Employee Scheduling System

A comprehensive employee scheduling system built with Django backend and Vue.js frontend, featuring advanced scheduling algorithms and modern web technologies.

## 🚀 Features

### Core Functionality
- **Multi-Company Support**: Manage multiple companies with separate data
- **Advanced Scheduling Algorithms**: Linear Programming, Genetic Algorithm, and Heuristic approaches
- **Employee Management**: Track employee availability, preferences, and constraints
- **Shift Management**: Define shifts with time slots and staffing requirements
- **Real-time Analytics**: Dashboard with coverage statistics and employee insights
- **Mobile-Responsive Design**: Optimized for all device sizes

### Technical Features
- **Vue.js 3** with Composition API and Server-Side Rendering (SSR)
- **Django 4** backend with RESTful API
- **Pinia** for state management
- **Bootstrap 5** for responsive UI
- **Chart.js** for data visualization
- **Docker** containerization for easy deployment
- **PostgreSQL** support (optional)

## 📋 Prerequisites

### For Development
- Python 3.8+
- Node.js 16+
- npm or yarn
- Git

### For Production
- Docker 20.10+
- Docker Compose 2.0+

## 🛠️ Installation & Setup

### Option 1: Docker (Recommended)

#### Quick Start
```bash
# Clone the repository
git clone <repository-url>
cd shift-manager

# Start in development mode
./scripts/start.sh          # Linux/macOS
scripts\start.bat           # Windows

# Start in production mode
./scripts/start.sh prod     # Linux/macOS
scripts\start.bat prod      # Windows
```

#### Manual Docker Setup
```bash
# Development
docker-compose up -d --build

# Production
docker-compose -f docker-compose.prod.yml up -d --build
```

### Option 2: Local Development

#### Backend Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Run migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Load sample data
python manage.py loaddata rostering_app/fixtures/companies.json
python manage.py loaddata rostering_app/fixtures/small_company/employees.json
python manage.py loaddata rostering_app/fixtures/small_company/shifts.json

# Start Django server
python manage.py runserver
```

#### Frontend Setup
```bash
# Install Node.js dependencies
npm install

# Development mode
npm run dev

# Production build
npm run build
npm run build:ssr
```

## 🏗️ Project Structure

```
shift-manager/
├── src/                          # Vue.js frontend
│   ├── components/               # Reusable UI components
│   ├── views/                    # Page components
│   ├── stores/                   # Pinia state management
│   ├── services/                 # API services
│   ├── composables/              # Utility functions
│   └── assets/                   # Static assets
├── rostering_app/                # Django application
│   ├── models.py                 # Data models
│   ├── views.py                  # API views
│   ├── management/commands/      # Django commands
│   └── fixtures/                 # Sample data
├── scheduling_core/              # Scheduling algorithms
│   ├── genetic_algorithm.py      # Genetic algorithm implementation
│   ├── linear_programming.py     # Linear programming solver
│   └── simulated_annealing.py    # Simulated annealing
├── Dockerfile*                   # Docker configurations
├── docker-compose*.yml           # Docker Compose files
└── requirements.txt              # Python dependencies
```

## 🎯 Usage

### Access Points

#### Development
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **Django Admin**: http://localhost:8000/admin

#### Production
- **Frontend**: http://localhost (HTTP) / https://localhost (HTTPS)
- **Backend API**: http://localhost:8000

### Basic Workflow

1. **Company Setup**: Create or select a company
2. **Employee Management**: Add employees with availability and preferences
3. **Shift Configuration**: Define shifts with time slots and staffing requirements
4. **Algorithm Selection**: Choose from available scheduling algorithms
5. **Schedule Generation**: Generate optimal schedules
6. **Review & Analytics**: View schedules and analyze coverage

### Scheduling Algorithms

#### Linear Programming
```bash
python manage.py generate_schedule_linear
```
- Uses PuLP library for mathematical optimization
- Finds globally optimal solution
- Best for smaller datasets

#### Genetic Algorithm
```bash
python manage.py generate_schedule_genetic
```
- Evolutionary approach for complex constraints
- Handles large datasets efficiently
- Configurable parameters for optimization

#### Heuristic Algorithm
```bash
python manage.py generate_schedule_heuristic
```
- Fast greedy approach
- Good for quick solutions
- Suitable for real-time adjustments

## 🔧 Configuration

### Environment Variables

Create a `.env` file for custom configuration:

```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com

# Database (if using PostgreSQL)
POSTGRES_DB=shift_manager
POSTGRES_USER=shift_manager
POSTGRES_PASSWORD=your-password
```

### Database Options

#### SQLite (Default)
- Stored in `./data/db.sqlite3`
- Suitable for development and small deployments

#### PostgreSQL (Production)
- Uncomment database service in `docker-compose.yml`
- Update settings in `rostering_project/settings.py`

## 🎨 UI Components

### Reusable Components
- **PageHeader**: Standardized page headers with breadcrumbs
- **MonthNavigation**: Month navigation controls
- **DateNavigation**: Day navigation controls
- **LoadingState**: Consistent loading indicators
- **ErrorState**: Error message display
- **StatCard**: Statistics cards
- **ShiftBadge**: Shift name display with color coding
- **StatusBadge**: Status indicators
- **ProgressBar**: Progress bars with auto-coloring
- **TimeDisplay**: Time formatting

### Color Scheme
Consistent shift colors across the application:
- **Early Shift**: Blue (#1976d2)
- **Morning Shift**: Purple (#7b1fa2)
- **Late Shift**: Orange (#f57c00)
- **Night Shift**: Pink (#c2185b)

## 📊 API Endpoints

### Companies
- `GET /api/companies/` - List all companies
- `GET /api/companies/{id}/` - Get company details

### Scheduling
- `GET /api/companies/{id}/algorithms/` - Get available algorithms
- `GET /api/companies/{id}/schedule/` - Get schedule data
- `POST /api/companies/{id}/schedule/generate/` - Generate new schedule

### Employees
- `GET /api/companies/{id}/employees/` - Get employees
- `GET /api/employees/{id}/` - Get employee details

### Shifts
- `GET /api/companies/{id}/shifts/` - Get shifts
- `GET /api/companies/{id}/shifts/{date}/` - Get day schedule

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

## 🔒 Security

### Production Security
- HTTPS with SSL/TLS encryption
- Security headers (HSTS, X-Frame-Options, etc.)
- Rate limiting on API endpoints
- CORS configuration
- Environment variable management

### Authentication
- Django admin authentication
- API token authentication (configurable)
- Session-based authentication

## 📈 Performance

### Optimizations
- **SSR**: Server-side rendering for better SEO and initial load
- **Code Splitting**: Lazy-loaded routes and components
- **Caching**: Static asset caching and API response caching
- **Gzip Compression**: Reduced bandwidth usage
- **CDN Ready**: Static files optimized for CDN deployment

### Monitoring
```bash
# Check service status
docker-compose ps

# Monitor resource usage
docker stats

# View application logs
docker-compose logs -f
```

## 🐛 Troubleshooting

### Common Issues

#### Port Conflicts
```bash
# Check port usage
lsof -i :8000
lsof -i :3000

# Change ports in docker-compose.yml
ports:
  - "8001:8000"
```

#### Database Issues
```bash
# Reset database
docker-compose down -v
docker-compose up -d

# Manual migration
docker-compose exec backend python manage.py migrate
```

#### Build Failures
```bash
# Clear Docker cache
docker system prune -a
docker-compose build --no-cache
```

### Debug Mode
```bash
# Enable debug
export DEBUG=True
docker-compose up -d
```

## 🔄 Maintenance

### Updates
```bash
# Pull latest changes
git pull

# Rebuild containers
docker-compose down
docker-compose up -d --build
```

### Backups
```bash
# Backup database
docker-compose exec backend python manage.py dumpdata > backup.json

# Restore database
docker-compose exec backend python manage.py loaddata backup.json
```

### Cleanup
```bash
# Remove containers and volumes
docker-compose down -v --remove-orphans

# Clean up images
docker system prune -a
```

## 📚 Documentation

- [Docker Deployment Guide](README_DOCKER.md)
- [Vue.js SSR Documentation](README_VUE_SSR.md)
- [Refactoring Summary](REFACTORING_SUMMARY.md)
- [Monthly Hours Calculation](MONTHLY_HOURS_CALCULATION.md)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Check the troubleshooting section
- Review the documentation files
- Open an issue on GitHub

## 🚀 Roadmap

- [ ] Real-time notifications
- [ ] Advanced reporting
- [ ] Mobile app
- [ ] Integration with HR systems
- [ ] Machine learning optimization
- [ ] Multi-language support 