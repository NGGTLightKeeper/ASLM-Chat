---
title: "settings"
draft: false
---

## Module `settings`

`ASLM/settings.py` — see source for implementation details.

---

## Module constants

#### `BASE_DIR`

**Purpose:** Module constant `BASE_DIR` (Path(__file__).resolve().parent.parent…).

#### `_cfg`

**Purpose:** Module constant `_cfg` (load_settings()…).

#### `SECRET_KEY`

**Purpose:** Module constant `SECRET_KEY` (_cfg.get('secret_key') or 'django-insecure-fallback-key-change-me'…).

#### `DEBUG`

**Purpose:** Module constant `DEBUG` (bool(_cfg.get('debug', False))…).

#### `ALLOWED_HOSTS`

**Purpose:** Module constant `ALLOWED_HOSTS` (_cfg.get('allowed_hosts', ['127.0.0.1', 'localhost'])…).

#### `LLM_ENGINE`

**Purpose:** Module constant `LLM_ENGINE` (get_llm_engine()…).

#### `OLLAMA_URL`

**Purpose:** Module constant `OLLAMA_URL` (get_engine_url('ollama-service')…).

#### `OLLAMA_ENABLED`

**Purpose:** Module constant `OLLAMA_ENABLED` (is_engine_enabled('ollama-service')…).

#### `LMSTUDIO_URL`

**Purpose:** Module constant `LMSTUDIO_URL` (get_engine_url('lms')…).

#### `OPENAI_COMPAT_URL`

**Purpose:** Module constant `OPENAI_COMPAT_URL` (get_engine_url('openai')…).

#### `OPENAI_COMPAT_API_KEY`

**Purpose:** Module constant `OPENAI_COMPAT_API_KEY` (get_openai_api_key() or os.environ.get('OPENAI_API_KEY', 'not-needed')…).

#### `CORS_ALLOWED_ORIGINS`

**Purpose:** Module constant `CORS_ALLOWED_ORIGINS` (['https://localhost', 'https://127.0.0.1', 'http://localhost', 'http://127.0.0.1…).

#### `CSRF_TRUSTED_ORIGINS`

**Purpose:** Module constant `CSRF_TRUSTED_ORIGINS` (['https://localhost', 'https://127.0.0.1', 'http://localhost', 'http://127.0.0.1…).

#### `CORS_ALLOW_METHODS`

**Purpose:** Module constant `CORS_ALLOW_METHODS` (('DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT')…).

#### `INSTALLED_APPS`

**Purpose:** Module constant `INSTALLED_APPS` (['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes', '…).

#### `MIDDLEWARE`

**Purpose:** Module constant `MIDDLEWARE` (['django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNo…).

#### `PASSWORD_HASHERS`

**Purpose:** Module constant `PASSWORD_HASHERS` (['django.contrib.auth.hashers.Argon2PasswordHasher', 'django.contrib.auth.hasher…).

#### `AUTH_PASSWORD_VALIDATORS`

**Purpose:** Module constant `AUTH_PASSWORD_VALIDATORS` ([{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValida…).

#### `ROOT_URLCONF`

**Purpose:** ASLM.urls

#### `WSGI_APPLICATION`

**Purpose:** ASLM.wsgi.application

#### `TEMPLATES`

**Purpose:** Module constant `TEMPLATES` ([{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP…).

#### `DATABASES`

**Purpose:** Module constant `DATABASES` ({'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqli…).

#### `LANGUAGE_CODE`

**Purpose:** en-us

#### `TIME_ZONE`

**Purpose:** UTC

#### `USE_I18N`

**Purpose:** Module constant `USE_I18N` (True…).

#### `USE_TZ`

**Purpose:** Module constant `USE_TZ` (True…).

#### `DEFAULT_CHARSET`

**Purpose:** utf-8

#### `DEFAULT_AUTO_FIELD`

**Purpose:** django.db.models.BigAutoField

#### `STATIC_ROOT`

**Purpose:** staticfiles/

#### `STATIC_URL`

**Purpose:** static/

#### `STATICFILES_DIRS`

**Purpose:** Module constant `STATICFILES_DIRS` ([BASE_DIR / 'static/']…).

#### `WHITENOISE_USE_FINDERS`

**Purpose:** Module constant `WHITENOISE_USE_FINDERS` (True…).

#### `WHITENOISE_AUTOREFRESH`

**Purpose:** Module constant `WHITENOISE_AUTOREFRESH` (DEBUG…).

#### `DATA_UPLOAD_MAX_MEMORY_SIZE`

**Purpose:** Module constant `DATA_UPLOAD_MAX_MEMORY_SIZE` (1024 * 1024 * 256…).

---

## Related

- [ASLM/_index](_index/)
