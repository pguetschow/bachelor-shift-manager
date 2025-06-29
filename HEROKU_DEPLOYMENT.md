# Heroku Docker Deployment

This project uses Docker containers for Heroku deployment via GitHub Actions.

## Setup

### 1. Create Heroku App

```bash
heroku create your-app-name
heroku addons:create heroku-postgresql:mini
```

### 2. Configure GitHub Secrets

Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

- `HEROKU_EMAIL`: Your Heroku email address
- `HEROKU_API_KEY`: Your Heroku API key (Account Settings → API Key)
- `HEROKU_APP_NAME`: Your Heroku app name

### 3. Set Environment Variables

```bash
heroku config:set SECRET_KEY=your-secret-key
heroku config:set DJANGO_SETTINGS_MODULE=rostering_project.settings
heroku config:set NODE_ENV=production
heroku config:set ALLOWED_HOSTS=your-app-name.herokuapp.com
```

### 4. Deploy

Push to `main` or `master` branch to trigger automatic deployment.

## Files

- `.github/workflows/deploy-heroku.yml`: GitHub Actions workflow
- `Dockerfile`: Multi-stage Docker build for Python + Node.js
- `.dockerignore`: Optimizes Docker build context

## Features

- ✅ Docker-based deployment
- ✅ Python 3.11 + Node.js 18
- ✅ Vue.js SSR build
- ✅ Django with Gunicorn
- ✅ PostgreSQL database
- ✅ Automatic migrations
- ✅ Static file collection 