"""Django settings for the ASLM-Chat project."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from Settings.settings import get_engine_url, get_llm_engine, get_openai_api_key, is_engine_enabled, load_settings

_cfg = load_settings()

SECRET_KEY = _cfg.get("secret_key") or "django-insecure-fallback-key-change-me"
DEBUG = bool(_cfg.get("debug", False))

ALLOWED_HOSTS = _cfg.get("allowed_hosts", ["127.0.0.1", "localhost"])

LLM_ENGINE = get_llm_engine()
OLLAMA_URL = get_engine_url("ollama-service")
OLLAMA_ENABLED = is_engine_enabled("ollama-service")
LMSTUDIO_URL = get_engine_url("lms")
OPENAI_COMPAT_URL = get_engine_url("openai")
OPENAI_COMPAT_API_KEY = get_openai_api_key() or os.environ.get("OPENAI_API_KEY", "not-needed")

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
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "martor",
    "Apps.Data",
    "Apps.UI",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

ROOT_URLCONF = "ASLM.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "ASLM.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_CHARSET = "utf-8"

STATIC_ROOT = "staticfiles/"
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static/"]

# WhiteNoise serves assets directly from STATICFILES_DIRS in development.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Allow large JSON bodies for base64-encoded image uploads (256 MB).
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024 * 256
