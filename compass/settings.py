"""
Django settings for the Compass project.

Compass is a mobile-first PWA that gives debate adjudicators one-tap access to
their Tabbycat private URLs. Configuration is environment-driven (see .env.example);
sensible defaults keep local development zero-config.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load a local .env file if present (no-op in production where real env vars are set).
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# --- Core security -----------------------------------------------------------

# A dev fallback key keeps `runserver` working out of the box; production MUST set
# DJANGO_SECRET_KEY (the deployment checklist warns if this default is used).
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-me-in-production-0123456789abcdef",
)

DEBUG = env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Public host used to build links in emails sent outside a request (e.g. the
# bulk-invite management command).
SITE_DOMAIN = os.getenv("SITE_DOMAIN", "localhost:8000")

# Fernet key used to encrypt secrets at rest (Tabbycat API tokens, private url keys).
# Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "")


# --- Applications ------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "accounts",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "compass.middleware.LanguageMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "compass.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "compass.wsgi.application"


# --- Database ----------------------------------------------------------------

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}


# --- Cache -------------------------------------------------------------------

# The database cache keeps login-throttle counters shared across processes and
# dynos (LocMem would silo them per worker). The table is created by
# `manage.py createcachetable` (run in the Procfile release phase).
if DEBUG:
    CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "cache_table",
        }
    }


# --- Authentication ----------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

# "Remember me" is applied per-login in the login view via set_expiry(). This is
# the default lifetime when the box is ticked (~60 days).
SESSION_COOKIE_AGE = 60 * 60 * 24 * 60

# Slide the session window on every request so an adjudicator who opens the app
# regularly is never logged out mid-tournament. Browser-close sessions
# (remember-me unticked, set_expiry(0)) are unaffected.
SESSION_SAVE_EVERY_REQUEST = True

# A stale CSRF token (long-idle PWA, page restored from cache) redirects back to
# a fresh page with a message instead of Django's bare 403.
CSRF_FAILURE_VIEW = "accounts.views.csrf_failure"

# Lock the login form after this many failed attempts per IP/email, for
# LOGIN_THROTTLE_TIMEOUT seconds (also the counting window).
LOGIN_THROTTLE_LIMIT = int(os.getenv("LOGIN_THROTTLE_LIMIT", "5"))
LOGIN_THROTTLE_TIMEOUT = int(os.getenv("LOGIN_THROTTLE_TIMEOUT", "900"))

# When True, sync auto-provisions an account for any Tabbycat adjudicator email
# that doesn't have one yet. Such accounts are created with an *unusable* password,
# so they cannot be logged into until the person sets one via the reset flow — and
# no invite email is ever sent. An account can only be created for an email that is
# actually a Tabbycat adjudicator (with a private URL).
AUTO_CREATE_ADJUDICATOR_ACCOUNTS = env_bool("AUTO_CREATE_ADJUDICATOR_ACCOUNTS", False)

# An active Tabbycat instance whose last sync is older than this is flagged red
# in the admin list — the usual cause is a dead cron job.
SYNC_STALE_AFTER_MINUTES = int(os.getenv("SYNC_STALE_AFTER_MINUTES", "60"))


# --- Internationalization ----------------------------------------------------

LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# English is the default UI language; Slovak is opt-in via Settings.
LANGUAGES = [("en", "English"), ("sk", "Slovenčina")]
LOCALE_PATHS = [BASE_DIR / "locale"]
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365  # remember the choice for a year


# --- Static files ------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# In production, hash + compress static assets via WhiteNoise. In development the
# staticfiles app serves directly from STATICFILES_DIRS (no manifest required).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Email -------------------------------------------------------------------

# Console backend by default (prints emails to the terminal). Configure SMTP via
# env to send real set-password / reset messages.
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Compass <noreply@localhost>")


# --- Production hardening -----------------------------------------------------

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", str(60 * 60 * 24 * 30)))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
