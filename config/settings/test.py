from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "test-secret-key-not-for-production"

# If Postgres is not running, the default client can block for a very long time.
# connect_timeout (seconds, libpq) fails fast so pytest does not appear "hung".
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "test_tobacco_db",
        "USER": "tobacco_user",
        "PASSWORD": "tobacco_pass",
        "HOST": "localhost",
        "PORT": "5432",
        "ATOMIC_REQUESTS": True,
        "OPTIONS": {
            "connect_timeout": 5,
        },
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

STORAGES = {
    **STORAGES,
    "default": {
        "BACKEND": "django.core.files.storage.InMemoryStorage",
    },
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
    "anon": "10000/minute",
    "user": "10000/minute",
    "assistant_chat": "10000/minute",
}

BLOCKCHAIN_ENABLED = False
AI_ENABLED = False
