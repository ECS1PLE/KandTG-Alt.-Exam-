import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'local-discretka-development-key')
DEBUG = False
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]', 'testserver']
ROOT_URLCONF = 'webapp.urls'
INSTALLED_APPS = []
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware',
              'django.middleware.common.CommonMiddleware',
              'django.middleware.csrf.CsrfViewMiddleware']
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates',
              'DIRS': [BASE_DIR / 'webapp' / 'templates'], 'APP_DIRS': False}]
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
USE_TZ = True

LANGUAGE_CODE = 'ru'
CSRF_FAILURE_VIEW = 'webapp.views.csrf_failure'
