# Vue.js SSR Frontend for Django Shift Manager

This project has been optimized with a modern Vue.js 3 frontend featuring Server-Side Rendering (SSR) for improved performance and SEO.

## Features

- **Vue.js 3** with Composition API
- **Server-Side Rendering (SSR)** for better SEO and initial load performance
- **Pinia** for state management
- **Vue Router** for client-side routing
- **Vite** for fast development and building
- **Bootstrap 5** for responsive UI
- **Chart.js** for data visualization
- **Axios** for API communication

## Project Structure

```
shift-manager/
├── src/                          # Vue.js source code
│   ├── assets/                   # Static assets
│   ├── components/               # Reusable Vue components
│   ├── router/                   # Vue Router configuration
│   ├── stores/                   # Pinia stores
│   ├── services/                 # API services
│   ├── views/                    # Page components
│   ├── App.vue                   # Root component
│   ├── main.js                   # Client entry point
│   └── entry-server.js           # Server entry point
├── rostering_app/                # Django app
│   ├── management/commands/      # Django management commands
│   └── views.py                  # Django views with API endpoints
├── package.json                  # Node.js dependencies
├── vite.config.js               # Vite configuration
├── server.js                    # SSR server
└── index.html                   # HTML template
```

## Setup Instructions

### Prerequisites

- Node.js 16+ and npm
- Python 3.8+ and pip
- Django 4.0+

### 1. Install Dependencies

```bash
# Install Node.js dependencies
npm install

# Install Python dependencies (if not already done)
pip install -r requirements.txt
```

### 2. Build the Vue.js Application

```bash
# Development build
npm run build

# Production build with SSR
npm run build:ssr
```

### 3. Run the Application

#### Option A: Development Mode (Recommended for development)

```bash
# Terminal 1: Start Django development server
python manage.py runserver

# Terminal 2: Start Vue.js development server
npm run dev
```

#### Option B: Production Mode with SSR

```bash
# Build the application first
npm run build:ssr

# Start Django server
python manage.py runserver

# Start SSR server
npm run serve:ssr
```

#### Option C: Using Django Management Command

```bash
# Build and serve Vue.js SSR with Django
python manage.py serve_vue_ssr --build
```

### 4. Access the Application

- **Django Admin**: http://localhost:8000/admin/
- **Vue.js Frontend**: http://localhost:3000/
- **Django API**: http://localhost:8000/api/

## Development Workflow

### Adding New Components

1. Create components in `src/components/`
2. Import and use in views
3. Components are auto-imported thanks to `unplugin-vue-components`

### Adding New API Endpoints

1. Add new views in `rostering_app/views.py`
2. Add URL patterns in `rostering_app/urls.py`
3. Create corresponding API methods in `src/services/api.js`

### State Management

Use Pinia stores in `src/stores/`:
- `company.js` - Company-related state
- `schedule.js` - Schedule and algorithm state

### Styling

- Global styles in `src/assets/main.css`
- Component-specific styles using `<style scoped>`
- Bootstrap 5 classes for layout and components

## API Endpoints

The Django backend provides these API endpoints:

- `GET /api/companies/` - List all companies
- `GET /api/companies/{id}/` - Get company details
- `GET /api/companies/{id}/algorithms/` - Get available algorithms
- `GET /api/companies/{id}/schedule/` - Get schedule data
- `GET /api/companies/{id}/employees/` - Get employees
- `GET /api/companies/{id}/shifts/` - Get shifts

## Performance Optimizations

### SSR Benefits

- **Faster Initial Load**: HTML is rendered on the server
- **Better SEO**: Search engines can crawl the content
- **Improved Core Web Vitals**: Better LCP and FID scores

### Code Splitting

- Routes are lazy-loaded for better performance
- Components are automatically code-split by Vite

### Caching

- API responses can be cached at the Django level
- Static assets are cached with proper headers

## Troubleshooting

### Common Issues

1. **Port conflicts**: Change ports in `vite.config.js` or use `--port` flag
2. **Build errors**: Clear `node_modules` and reinstall dependencies
3. **API errors**: Check Django server is running and CORS settings

### Debug Mode

```bash
# Enable Vue devtools
npm run dev

# Check browser console for errors
# Check Django logs for API errors
```

## Deployment

### Production Build

```bash
# Build for production
npm run build:ssr

# Collect static files
python manage.py collectstatic

# Run with production server (Gunicorn, etc.)
```

### Environment Variables

Set these environment variables for production:

```bash
NODE_ENV=production
DJANGO_SETTINGS_MODULE=rostering_project.settings
```

## Contributing

1. Follow Vue.js 3 Composition API patterns
2. Use TypeScript for better type safety (optional)
3. Write tests for components and stores
4. Follow the existing code style and structure

## License

This project is part of the Shift Manager application. 