"""Django settings for the Mwalimu Platform API."""

import os
from datetime import timedelta
from pathlib import Path

import environ  # type: ignore[import-untyped]

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "dev-secret-key-change-me-32bytes-min-for-jwt-signing",
)
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "corsheaders",
]

LOCAL_APPS = [
    "platform_api.apps.users",
    "platform_api.apps.institutions",
    "platform_api.apps.memberships",
    "platform_api.apps.libraries",
    "platform_api.apps.resources",
    "platform_api.apps.processing",
    "platform_api.apps.knowledge",
    "platform_api.apps.agents",
    "platform_api.apps.context",
    "platform_api.apps.connectors",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "platform_api.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "platform_api.wsgi.application"

_env = environ.Env()
if os.getenv("DATABASE_URL"):
    # Production (Render/Railway): DATABASE_URL is the single source of truth.
    DATABASES = {"default": _env.db_url("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DATABASE_NAME", "mwalimu"),
            "USER": os.getenv("DATABASE_USER", "mwalimu"),
            "PASSWORD": os.getenv("DATABASE_PASSWORD", "mwalimu"),
            "HOST": os.getenv("DATABASE_HOST", "localhost"),
            "PORT": os.getenv("DATABASE_PORT", "5432"),
        },
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Mwalimu Platform API",
    "DESCRIPTION": (
        "Identity, institution, membership, and library API for the Mwalimu platform."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SECURITY": [{"BearerAuth": []}],
}

SIMPLE_JWT = {
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
}

CORS_ALLOWED_ORIGINS = [
    origin
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin
]
# Cookies flow cross-origin (same-site, different port) but MUST never couple
# with a wildcard origin. Credentials are only enabled for the explicit origins
# listed above (django-cors-headers then reflects the specific allowed origin).
CORS_ALLOW_CREDENTIALS = os.getenv("CORS_ALLOW_CREDENTIALS", "True").lower() in (
    "true",
    "1",
    "yes",
)
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]
CORS_ALLOW_METHODS = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]

# Double-submit CSRF: the SPA reads the (non-HttpOnly) csrftoken cookie and
# sends it as X-CSRFToken for the cookie-authenticated endpoints (refresh/logout).
CSRF_TRUSTED_ORIGINS = os.getenv(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "True").lower() in (
    "true",
    "1",
    "yes",
)
CSRF_COOKIE_HTTPONLY = False  # JS must read it to send X-CSRFToken (double-submit).

# Refresh token cookie (HttpOnly + Secure + SameSite=Lax, scoped to auth routes).
# Secure is environment-configurable so non-localhost dev setups can relax it;
# production must default to True (it does).
REFRESH_COOKIE_NAME = os.getenv("REFRESH_COOKIE_NAME", "mwalimu_refresh")
REFRESH_COOKIE_PATH = os.getenv("REFRESH_COOKIE_PATH", "/api/v1/auth")
REFRESH_COOKIE_HTTPONLY = os.getenv("REFRESH_COOKIE_HTTPONLY", "True").lower() in (
    "true",
    "1",
    "yes",
)
REFRESH_COOKIE_SECURE = os.getenv("REFRESH_COOKIE_SECURE", "True").lower() in (
    "true",
    "1",
    "yes",
)
REFRESH_COOKIE_SAMESITE = os.getenv("REFRESH_COOKIE_SAMESITE", "Lax")
REFRESH_COOKIE_MAX_AGE = int(timedelta(days=7).total_seconds())

# Object storage configuration (S3-compatible: MinIO locally, AWS S3/R2 in production)
OBJECT_STORAGE_BACKEND = os.getenv(
    "OBJECT_STORAGE_BACKEND",
    "platform_api.apps.resources.storage.S3Storage",
)
OBJECT_STORAGE_ENDPOINT = os.getenv("OBJECT_STORAGE_ENDPOINT", "http://localhost:9000")
OBJECT_STORAGE_REGION = os.getenv("OBJECT_STORAGE_REGION", "")
OBJECT_STORAGE_ACCESS_KEY = os.getenv("OBJECT_STORAGE_ACCESS_KEY", "minioadmin")
OBJECT_STORAGE_SECRET_KEY = os.getenv("OBJECT_STORAGE_SECRET_KEY", "minioadmin")
OBJECT_STORAGE_BUCKET = os.getenv("OBJECT_STORAGE_BUCKET", "mwalimu")

# Resource upload limits
RESOURCE_MAX_UPLOAD_SIZE = int(
    os.getenv("RESOURCE_MAX_UPLOAD_SIZE", str(100 * 1024 * 1024))
)

# Celery and Redis configuration
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "False").lower() in (
    "true",
    "1",
    "yes",
)
CELERY_TASK_EAGER_PROPAGATES = True

# OAuth Provider Configuration (Google, Notion)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
NOTION_CLIENT_ID = os.getenv("NOTION_CLIENT_ID", "")
NOTION_CLIENT_SECRET = os.getenv("NOTION_CLIENT_SECRET", "")

CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True

CELERY_BEAT_SCHEDULE = {
    "reconcile-orphaned-agent-runs-every-60s": {
        "task": "platform_api.apps.agents.tasks.reconcile_orphaned_agent_runs",
        "schedule": 60.0,
    },
}

# Embedding Provider and Pipeline configuration
EMBEDDING_PROVIDER_BACKEND = os.getenv(
    "EMBEDDING_PROVIDER_BACKEND",
    "platform_api.apps.processing.embedding.openai_provider.OpenAICompatibleProvider",
)
EMBEDDING_API_BASE_URL = os.getenv(
    "EMBEDDING_API_BASE_URL", "https://api.openai.com/v1"
)
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_VERSION = os.getenv("EMBEDDING_VERSION", "1")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

PIPELINE_VERSION = os.getenv("PIPELINE_VERSION", "1")
CHUNKER_VERSION = os.getenv("CHUNKER_VERSION", "1")

# Knowledge Gateway configuration
KNOWLEDGE_GATEWAY_MAX_TOP_K = int(os.getenv("KNOWLEDGE_GATEWAY_MAX_TOP_K", "50"))
KNOWLEDGE_GATEWAY_MAX_QUERY_LENGTH = int(
    os.getenv("KNOWLEDGE_GATEWAY_MAX_QUERY_LENGTH", "10000")
)
DELEGATION_SIGNING_KEY = os.getenv("DELEGATION_SIGNING_KEY", SECRET_KEY)

# Agent Service configuration (independent FastAPI execution runtime)
AGENT_SERVICE_BASE_URL = os.getenv("AGENT_SERVICE_BASE_URL", "http://localhost:8001")
AGENT_SERVICE_JWT_SECRET_KEY = os.getenv(
    "AGENT_SERVICE_JWT_SECRET_KEY",
    "mwalimu-insecure-dev-secret-key-change-in-production",
)
AGENT_SERVICE_JWT_ALGORITHM = os.getenv("AGENT_SERVICE_JWT_ALGORITHM", "HS256")
AGENT_SERVICE_JWT_EXPIRATION_SECONDS = int(
    os.getenv("AGENT_SERVICE_JWT_EXPIRATION_SECONDS", "300")
)
AGENT_SERVICE_TIMEOUT_SECONDS = float(
    os.getenv("AGENT_SERVICE_TIMEOUT_SECONDS", "30.0")
)

# Internal Service completion callback authentication
# (Domain D: Agent Service -> Platform API)
INTERNAL_SERVICE_SECRET_KEY = os.getenv(
    "INTERNAL_SERVICE_SECRET_KEY",
    "mwalimu-insecure-dev-internal-secret-change-in-production",
)
INTERNAL_SERVICE_JWT_ALGORITHM = os.getenv("INTERNAL_SERVICE_JWT_ALGORITHM", "HS256")

# Agent Stream Capability configuration (Domain S: Client -> Agent Service SSE)
AGENT_SERVICE_PUBLIC_BASE_URL = os.getenv(
    "AGENT_SERVICE_PUBLIC_BASE_URL", "http://localhost:8001"
)
AGENT_STREAM_JWT_SECRET_KEY = os.getenv(
    "AGENT_STREAM_JWT_SECRET_KEY",
    AGENT_SERVICE_JWT_SECRET_KEY,
)
AGENT_STREAM_JWT_ALGORITHM = os.getenv("AGENT_STREAM_JWT_ALGORITHM", "HS256")
AGENT_STREAM_JWT_EXPIRATION_SECONDS = int(
    os.getenv("AGENT_STREAM_JWT_EXPIRATION_SECONDS", "300")
)
