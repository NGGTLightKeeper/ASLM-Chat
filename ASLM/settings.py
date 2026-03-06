import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Ensure BASE_DIR is on sys.path so Settings package is importable
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from Settings.settings import load_settings as _load_settings

_cfg = _load_settings()

SECRET_KEY = _cfg.get('secret_key') or 'django-insecure-fallback-key-change-me'
DEBUG = _cfg.get('debug', False)

ALLOWED_HOSTS = _cfg.get('allowed_hosts', ['127.0.0.1', 'localhost'])

OLLAMA_URL = f"http://127.0.0.1:{_cfg.get('ollama-service_port', 30002)}"
OLLAMA_ENABLED = _cfg.get('ollama-service', False)

CORS_ALLOWED_ORIGINS = [
    "https://localhost",
    "https://127.0.0.1",
    "http://localhost",
    "http://127.0.0.1",
]
CSRF_TRUSTED_ORIGINS = [
    "https://localhost",
    "https://127.0.0.1",
    "http://localhost",
    "http://127.0.0.1",
]
CORS_ALLOW_METHODS = (
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'martor',

    'Apps.Data',
    'Apps.UI',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

ROOT_URLCONF = 'ASLM.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'ASLM.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

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

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
DEFAULT_CHARSET = 'utf-8'

# STATIC
STATIC_ROOT = "staticfiles/"
STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / "static/",
]

# WhiteNoise — serve files directly from STATICFILES_DIRS without collectstatic
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
