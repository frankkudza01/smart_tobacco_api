import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("DJANGO_SECRET_KEY")
DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost", cast=Csv())

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "storages",
    "django_celery_beat",
    "drf_spectacular",
]

LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.organizations",
    "apps.farms",
    "apps.seasons",
    "apps.lots",
    "apps.traceability",
    "apps.documents",
    "apps.grading",
    "apps.sales",
    "apps.settlements",
    "apps.disputes",
    "apps.provenance",
    "apps.sync",
    "apps.notifications",
    "apps.ai_assistant",
    "apps.ai_intelligence",
    "apps.blockchain",
    "apps.audit",
    "apps.whatsapp",
    "apps.worldready",
    "apps.ml_monitoring",
    "apps.privacy_controls",
    "apps.weather",
    "apps.tobacco_monitoring",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.middleware.RequestIDMiddleware",
    "apps.common.middleware.AuditMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL = config("DATABASE_URL", default="postgres://tobacco_user:tobacco_pass@localhost:5432/tobacco_db")


def _database_config_from_url(url: str) -> dict:
    """
    Parse postgres/postgresql URLs into Django DATABASES['default'].
    Accepts: postgres://user:pass@host:port/dbname (password may be empty or URL-encoded).
    """
    raw = (url or "").strip()
    if not raw:
        raise ImproperlyConfigured("DATABASE_URL is empty. Set it in your environment or .env file.")

    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]

    parsed = urlparse(raw)
    if parsed.scheme != "postgresql":
        raise ImproperlyConfigured(
            "DATABASE_URL must start with postgres:// or postgresql:// "
            f"(example: postgres://USER:PASSWORD@localhost:5432/DBNAME). Got scheme={parsed.scheme!r}."
        )

    if not parsed.hostname:
        raise ImproperlyConfigured(
            "DATABASE_URL must include a host after credentials, e.g. "
            "postgres://tobacco_user:tobacco_pass@localhost:5432/tobacco_db "
            "(the part user:pass@HOST is required — do not omit the @)."
        )

    db_name = (parsed.path or "").lstrip("/") or "postgres"
    user = unquote(parsed.username) if parsed.username else ""
    password = unquote(parsed.password) if parsed.password else ""
    port = str(parsed.port) if parsed.port else "5432"

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": db_name,
        "USER": user,
        "PASSWORD": password,
        "HOST": parsed.hostname,
        "PORT": port,
        "ATOMIC_REQUESTS": True,
    }


DATABASES = {"default": _database_config_from_url(DATABASE_URL)}

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Harare"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------------------
# Storage (Django 5.1+)
# ---------------------------------------------------------------------------
# DEFAULT_FILE_STORAGE / STATICFILES_STORAGE are ignored in Django 5.1.
# Media must use STORAGES["default"] or uploads silently fall back to local disk
# (MinIO will stay empty while rows still appear in Postgres).
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="minioadmin")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="minioadmin")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="tobacco-documents")
AWS_S3_ENDPOINT_URL = config("AWS_S3_ENDPOINT_URL", default="http://localhost:9000")
AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="us-east-1")
AWS_S3_FILE_OVERWRITE = False
AWS_DEFAULT_ACL = "private"
AWS_QUERYSTRING_AUTH = True
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_ADDRESSING_STYLE = "path"

# ---------------------------------------------------------------------------
# REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "apps.common.schema.LenientAutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/minute",
        "user": "120/minute",
        "assistant_chat": "30/minute",
    },
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# ---------------------------------------------------------------------------
# SimpleJWT
# ---------------------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=60, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = config("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Africa/Harare"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240
# Celery 6+ will stop using broker_connection_retry for startup retries; set explicitly.
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# ---------------------------------------------------------------------------
# Cache (Redis)
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://localhost:6379/0"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # If Redis is down, return cache misses instead of 500 (DRF throttles use cache).
            "IGNORE_EXCEPTIONS": True,
        },
    }
}

# ---------------------------------------------------------------------------
# Blockchain
# ---------------------------------------------------------------------------
BLOCKCHAIN_ENABLED = config("BLOCKCHAIN_ENABLED", default=False, cast=bool)
BLOCKCHAIN_PROVIDER_URL = config("BLOCKCHAIN_PROVIDER_URL", default="http://localhost:8545")
BLOCKCHAIN_CHAIN_ID = config("BLOCKCHAIN_CHAIN_ID", default=31337, cast=int)
BLOCKCHAIN_PRIVATE_KEY = config("BLOCKCHAIN_PRIVATE_KEY", default="")
BLOCKCHAIN_CONTRACT_ADDRESS = config("BLOCKCHAIN_CONTRACT_ADDRESS", default="")

# ---------------------------------------------------------------------------
# AI / LLM
# ---------------------------------------------------------------------------
AI_ENABLED = config("AI_ENABLED", default=False, cast=bool)
# openai | gemini
AI_PROVIDER = config("AI_PROVIDER", default="openai")
OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
GEMINI_API_KEY = config("GEMINI_API_KEY", default="")
AI_MODEL_NAME = config("AI_MODEL_NAME", default="gpt-4o-mini")
# Gemini generateContent: retries on 429/5xx (high demand). Default 6 with exponential backoff in openai_safe.
AI_GEMINI_MAX_HTTP_RETRIES = config("AI_GEMINI_MAX_HTTP_RETRIES", default=10, cast=int)
# When the primary model is overloaded (503), try this model after retries exhaust (deduped if same as primary).
AI_GEMINI_FALLBACK_MODEL = config("AI_GEMINI_FALLBACK_MODEL", default="gemini-2.0-flash")
# Vision grading uses this model when set; otherwise AI_MODEL_NAME (should be vision-capable, e.g. gpt-4o-mini).
AI_VISION_MODEL_NAME = config("AI_VISION_MODEL_NAME", default="")
AI_MAX_TOKENS = config("AI_MAX_TOKENS", default=2048, cast=int)
AI_OPENAI_TIMEOUT_SECONDS = config("AI_OPENAI_TIMEOUT_SECONDS", default=45, cast=int)
AI_OPENAI_MAX_RETRIES = config("AI_OPENAI_MAX_RETRIES", default=2, cast=int)
AI_CIRCUIT_BREAKER_THRESHOLD = config("AI_CIRCUIT_BREAKER_THRESHOLD", default=5, cast=int)
AI_CIRCUIT_BREAKER_COOLDOWN_SECONDS = config("AI_CIRCUIT_BREAKER_COOLDOWN_SECONDS", default=120, cast=int)
# When True, hardened assistant chat skips LangChain/tool-calling and returns the safe local fallback (200).
# Use for Python 3.14+ issues, dependency outages, or deliberate read-only assistant mode.
AI_FORCE_FALLBACK = config("AI_FORCE_FALLBACK", default=False, cast=bool)

# ---------------------------------------------------------------------------
# OpenWeatherMap (Zimbabwe farmer forecasts — key via env only, never in repo)
# ---------------------------------------------------------------------------
OPENWEATHERMAP_API_KEY = config("OPENWEATHERMAP_API_KEY", default="")
# Optional label matching the key name in your OpenWeatherMap dashboard (not secret).
OPENWEATHERMAP_KEY_NAME = config("OPENWEATHERMAP_KEY_NAME", default="")
OPENWEATHERMAP_TIMEOUT_SECONDS = config("OPENWEATHERMAP_TIMEOUT_SECONDS", default=15, cast=int)

# ---------------------------------------------------------------------------
# Sentry
# ---------------------------------------------------------------------------
SENTRY_DSN = config("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

# ---------------------------------------------------------------------------
# DRF Spectacular (OpenAPI)
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "AI-Enhanced Zimbabwe Tobacco Supply Chain API",
    "DESCRIPTION": (
        "Backend API for the tobacco supply chain traceability platform. "
        "Errors use a standard envelope: success=false, data=null, meta, errors[]. "
        "List endpoints commonly return {results: [...]}; pagination uses page/limit "
        "(StandardPagination) unless noted (e.g. sync/changes uses since_timestamp)."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1/",
    "COMPONENT_SPLIT_REQUEST": True,
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "()": "structlog.stdlib.ProcessorFormatter",
            "processor": "structlog.dev.ConsoleRenderer",
        },
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# File Upload Limits
# ---------------------------------------------------------------------------
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Document settings
# ---------------------------------------------------------------------------
ALLOWED_DOCUMENT_TYPES = [
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]
MAX_DOCUMENT_SIZE_MB = 10

# ---------------------------------------------------------------------------
# AgroMonitoring (satellite / NDVI for tobacco fields)
# ---------------------------------------------------------------------------
AGROMONITORING_API_KEY = config("AGROMONITORING_API_KEY", default="")
AGROMONITORING_BASE_URL = config(
    "AGROMONITORING_BASE_URL",
    default="https://api.agromonitoring.com/agro/1.0",
)
AGROMONITORING_TIMEOUT_SECONDS = config("AGROMONITORING_TIMEOUT_SECONDS", default=30, cast=int)
AGROMONITORING_MAX_RETRIES = config("AGROMONITORING_MAX_RETRIES", default=3, cast=int)
# AgroMonitoring NDVI/soil history often rejects long windows with HTTP 400; request in chunks.
AGROMONITORING_HISTORY_CHUNK_DAYS = config(
    "AGROMONITORING_HISTORY_CHUNK_DAYS",
    default=30,
    cast=int,
)

# ---------------------------------------------------------------------------
# Meta WhatsApp Cloud API (crop stress alerts; separate from Twilio OTP channel)
# ---------------------------------------------------------------------------
META_WHATSAPP_ACCESS_TOKEN = config("META_WHATSAPP_ACCESS_TOKEN", default="")
META_WHATSAPP_PHONE_NUMBER_ID = config("META_WHATSAPP_PHONE_NUMBER_ID", default="")
META_WHATSAPP_BASE_URL = config(
    "META_WHATSAPP_BASE_URL", default="https://graph.facebook.com/v21.0"
)
META_WHATSAPP_TIMEOUT_SECONDS = config("META_WHATSAPP_TIMEOUT_SECONDS", default=20, cast=int)
META_WHATSAPP_MAX_RETRIES = config("META_WHATSAPP_MAX_RETRIES", default=3, cast=int)

# ---------------------------------------------------------------------------
# Tobacco satellite monitoring (Zimbabwe)
# ---------------------------------------------------------------------------
SATELLITE_POLL_CRON = config(
    "SATELLITE_POLL_CRON", default="0 6 * * *"
)  # informational; django-celery-beat PeriodicTask in DB
NDVI_STRESS_DROP_THRESHOLD = config("NDVI_STRESS_DROP_THRESHOLD", default=10.0, cast=float)
SOIL_MOISTURE_STRESS_THRESHOLD = config(
    "SOIL_MOISTURE_STRESS_THRESHOLD", default=0.18, cast=float
)
SOIL_MOISTURE_DROP_THRESHOLD_PCT = config(
    "SOIL_MOISTURE_DROP_THRESHOLD_PCT", default=20.0, cast=float
)
DEFAULT_ALERT_LANGUAGE = config("DEFAULT_ALERT_LANGUAGE", default="en")
DEFAULT_COUNTRY_CODE = config("DEFAULT_COUNTRY_CODE", default="ZW")
TOBACCO_DEFAULT_CROP = config("TOBACCO_DEFAULT_CROP", default="tobacco")
TOBACCO_AUTO_CREATE_POLYGON_FROM_GEOFENCE = config(
    "TOBACCO_AUTO_CREATE_POLYGON_FROM_GEOFENCE", default=True, cast=bool
)
TOBACCO_SUPPORTED_PROVINCES = config(
    "TOBACCO_SUPPORTED_PROVINCES",
    default="Mashonaland Central,Mashonaland West,Mashonaland East,Manicaland",
    cast=Csv(),
)
TOBACCO_YIELD_PROXY_COEFFICIENT = config(
    "TOBACCO_YIELD_PROXY_COEFFICIENT", default=0.25, cast=float
)
TOBACCO_PLANTING_NDVI_THRESHOLD = config(
    "TOBACCO_PLANTING_NDVI_THRESHOLD", default=0.25, cast=float
)

# ---------------------------------------------------------------------------
# Twilio / WhatsApp
# ---------------------------------------------------------------------------
# Provider: auto | twilio | waapi | mock
# auto: WaAPI if WAAPI_TOKEN + WAAPI_INSTANCE_ID set, else Twilio if SID+token, else mock.
WHATSAPP_PROVIDER = config("WHATSAPP_PROVIDER", default="auto")
TWILIO_ACCOUNT_SID = config("TWILIO_ACCOUNT_SID", default="")
TWILIO_AUTH_TOKEN = config("TWILIO_AUTH_TOKEN", default="")
TWILIO_WHATSAPP_FROM = config("TWILIO_WHATSAPP_FROM", default="whatsapp:+14155238886")
TWILIO_WEBHOOK_PATH = config("TWILIO_WEBHOOK_PATH", default="/api/v1/whatsapp/webhook/")
# WaAPI (https://waapi.app) — Bearer token from dashboard (instance name e.g. TOBACCO is cosmetic).
WAAPI_BASE_URL = config("WAAPI_BASE_URL", default="https://waapi.app/api/v1")
WAAPI_INSTANCE_ID = config("WAAPI_INSTANCE_ID", default="")
WAAPI_TOKEN = config("WAAPI_TOKEN", default="")
# Optional: require matching header X-WAAPI-WEBHOOK-SECRET on inbound webhooks.
WAAPI_WEBHOOK_SECRET = config("WAAPI_WEBHOOK_SECRET", default="")

# ---------------------------------------------------------------------------
# OTP Configuration
# ---------------------------------------------------------------------------
OTP_TTL_SECONDS = config("OTP_TTL_SECONDS", default=300, cast=int)
OTP_RESEND_COOLDOWN_SECONDS = config("OTP_RESEND_COOLDOWN_SECONDS", default=60, cast=int)
OTP_MAX_ATTEMPTS = config("OTP_MAX_ATTEMPTS", default=5, cast=int)
OTP_CODE_LENGTH = config("OTP_CODE_LENGTH", default=6, cast=int)
ENABLE_DEV_OTP_LOGGING = config("ENABLE_DEV_OTP_LOGGING", default=DEBUG, cast=bool)

# ---------------------------------------------------------------------------
# WhatsApp conversation settings
# ---------------------------------------------------------------------------
WHATSAPP_CONVERSATION_TTL_MINUTES = config("WHATSAPP_CONVERSATION_TTL_MINUTES", default=30, cast=int)
WHATSAPP_WEBHOOK_RATE_LIMIT_PER_MINUTE = config(
    "WHATSAPP_WEBHOOK_RATE_LIMIT_PER_MINUTE", default=60, cast=int
)

# ---------------------------------------------------------------------------
# Mobile deep links (Flutter) — scheme only, no secrets
# ---------------------------------------------------------------------------
APP_DEEP_LINK_SCHEME = config("APP_DEEP_LINK_SCHEME", default="app")

# ---------------------------------------------------------------------------
# Push (optional — legacy FCM HTTP; set empty to disable sends)
# ---------------------------------------------------------------------------
FCM_LEGACY_SERVER_KEY = config("FCM_LEGACY_SERVER_KEY", default="")

# Absolute API base for links generated outside an HTTP request (e.g. WhatsApp export URLs).
PUBLIC_API_BASE_URL = config("PUBLIC_API_BASE_URL", default="http://127.0.0.1:8000")

# ---------------------------------------------------------------------------
# Privacy / field encryption (Fernet; base64 url-safe 32-byte key or any string hashed to key)
# ---------------------------------------------------------------------------
PII_ENCRYPTION_KEY = config("PII_ENCRYPTION_KEY", default="")
