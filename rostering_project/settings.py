import os
from pathlib import Path
import mimetypes
import dj_database_url
from urllib.parse import urlparse
import environ
env = environ.Env()
environ.Env.read_env()

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')

DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = [
    'localhost', 
    '127.0.0.1', 
    '0.0.0.0', 
    'backend',
    'bachelor-shift-manager-2c19b47af666.herokuapp.com',
    '.herokuapp.com',  # Allow all herokuapp.com subdomains
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rostering_app',
    'scheduling_core',
    'corsheaders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'rostering_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [ BASE_DIR / 'rostering_app' / 'templates' ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'rostering_project.wsgi.application'

# Database (default is SQLite)
# if os.environ.get('DJANGO_PRODUCTION') or os.environ.get('HEROKU'):
DATABASES = {
  'default': {
    'ENGINE': 'django.db.backends.mysql',
    'HOST': env('STACKHERO_MYSQL_HOST'),
    'PORT': '7398',
    'OPTIONS': {
      'ssl_mode': 'REQUIRED',
       'charset': 'utf8mb4',
       'init_command': "SET NAMES 'utf8mb4'",
    },
    'NAME': 'scheduler',
    'USER': 'root',
    'PASSWORD': env('STACKHERO_MYSQL_ROOT_PASSWORD')
  }
}
# else:
#     DATABASES = {
#         'default': {
#             'ENGINE': 'django.db.backends.mysql',
#             'NAME': os.environ.get('MYSQL_DATABASE', 'shift_manager'),
#             'USER': os.environ.get('MYSQL_USER', 'shift_manager'),
#             'PASSWORD': os.environ.get('MYSQL_PASSWORD', 'shift_manager_password'),
#             'HOST': os.environ.get('MYSQL_HOST', 'db'),
#             'PORT': os.environ.get('MYSQL_PORT', '3306'),
#             'OPTIONS': {
#                 'charset': 'utf8mb4',
#                 'init_command': "SET NAMES 'utf8mb4'",
#             },
#         }
#     }

# Password validation (use default validators)
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'de-de'
TIME_ZONE = 'Europe/Berlin'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static'

# Add the dist directory for Vue.js built files
STATICFILES_DIRS = [
    BASE_DIR / 'dist',
]

# Ensure static files are served in production
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

# MIME type configuration for proper asset serving
mimetypes.add_type("text/css", ".css", True)
mimetypes.add_type("application/javascript", ".js", True)

# CORS settings
# For development, allow all localhost origins
CORS_ALLOW_ALL_ORIGINS = True

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# Security settings for production
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
