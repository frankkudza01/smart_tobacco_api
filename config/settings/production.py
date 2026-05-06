from .base import *  # noqa: F401,F403

DEBUG = False

# When deploying behind HTTPS (recommended), leave default True. For a first deploy on a bare IP
# over HTTP only, set DJANGO_USE_TLS=False in the environment (see .env.production.example).
USE_TLS = config("DJANGO_USE_TLS", default=True, cast=bool)  # noqa: F405

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = USE_TLS
CSRF_COOKIE_SECURE = USE_TLS
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=USE_TLS, cast=bool)  # noqa: F405

if USE_TLS:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
else:
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

CSRF_TRUSTED_ORIGINS = config(  # noqa: F405
    "CSRF_TRUSTED_ORIGINS",
    default="https://localhost",
    cast=Csv(),  # noqa: F405
)
