from .base import *  # noqa: F401,F403

DEBUG = True

# ---------------------------------------------------------------------------
# Cache — optional Redis for local development
# ---------------------------------------------------------------------------
# Running `manage.py runserver` on the host without Docker often leaves nothing
# listening on 127.0.0.1:6379. DRF rate throttles use the default cache; a Redis
# connection error becomes a 500 on POST /api/v1/auth/login/. Use in-process
# LocMem unless USE_REDIS_CACHE=true (e.g. full Docker stack with Redis up).
if not config("USE_REDIS_CACHE", default=False, cast=bool):  # noqa: F405
    CACHES = {  # noqa: F405
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "smart-tobacco-local-cache",
        }
    }

INSTALLED_APPS += [  # noqa: F405
    "debug_toolbar",
    "django_extensions",
]

MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405

INTERNAL_IPS = ["127.0.0.1"]

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
    "anon": "1000/minute",
    "user": "5000/minute",
    "assistant_chat": "60/minute",
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
