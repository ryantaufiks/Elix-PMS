from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
# Docker Compose injects variables directly; this file is only read when
# running manage.py on the host.
if (BASE_DIR.parent / ".env").exists():
    environ.Env.read_env(BASE_DIR.parent / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

# Public URL of the API, used to build invitation share links.
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", default="http://localhost:8000")

# Fernet key(s) used to encrypt third-party credentials at rest. Comma-separate
# several keys to rotate: the first encrypts, all of them decrypt.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "phonenumber_field",
    "core",
]

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

ROOT_URLCONF = "myproject.urls"

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

WSGI_APPLICATION = "myproject.wsgi.application"
ASGI_APPLICATION = "myproject.asgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}
if env.bool("DB_POOL", default=False):
    # The ASGI server runs sync views on many threads, and each thread would open (and keep) its own
    # connection until Postgres runs out. A small shared pool per process caps and reuses them.
    DATABASES["default"]["CONN_MAX_AGE"] = 0
    DATABASES["default"].setdefault("OPTIONS", {})["pool"] = {
        "min_size": 2, "max_size": env.int("DB_POOL_SIZE", default=10), "timeout": 10,
    }
else:
    DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)

AUTH_USER_MODEL = "core.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Asia/Singapore"
USE_I18N = True
USE_TZ = True

PHONENUMBER_DEFAULT_REGION = "SG"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # The manifest backend needs collectstatic, which only runs in production.
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Media holds visitor face photos and LPR snapshots (personal data under PDPA).
# It is never served publicly; production access goes through authenticated views.
MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))
# Platform backups and site exports (System → Backups). Outside MEDIA_ROOT on purpose.
BACKUP_ROOT = env("BACKUP_ROOT", default=str(BASE_DIR / "backups"))
BACKUP_KEEP_DAYS = env.int("BACKUP_KEEP_DAYS", default=14)
SITE_EXPORT_KEEP_DAYS = env.int("SITE_EXPORT_KEEP_DAYS", default=7)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.Pagination",
    "EXCEPTION_HANDLER": "core.exceptions.exception_handler",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "kiosk_call": env("KIOSK_CALL_RATE", default="10/min"),
        "kiosk_checkin": env("KIOSK_CHECKIN_RATE", default="30/min"),
        "kiosk_assistant": env("KIOSK_ASSISTANT_RATE", default="30/min"),
        "visitor_pass": env("VISITOR_PASS_RATE", default="60/min"),
        "resident_open": env("RESIDENT_OPEN_RATE", default="10/min"),
        "payment_callback": env("PAYMENT_CALLBACK_RATE", default="120/min"),
        "login": env("LOGIN_RATE", default="20/min"),  # Per address (sign-in and token refresh).
        "login_user": env("LOGIN_USER_RATE", default="10/min"),  # Per username.
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=30)),
    "ROTATE_REFRESH_TOKENS": True,
    # A used refresh token is revoked, so a stolen copy stops working once the owner refreshes;
    # signing out, a password change or disabling the account revokes all of them.
    "BLACKLIST_AFTER_ROTATION": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Elix VMS API",
    "DESCRIPTION": "Visitor Management & Access Control System",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # The API map is for platform administrators (signed in to the Django admin), not the public.
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
    "SERVE_AUTHENTICATION": ["rest_framework.authentication.SessionAuthentication",
                             "rest_framework_simplejwt.authentication.JWTAuthentication"],
    "ENUM_NAME_OVERRIDES": {
        "InvitationStatusEnum": "core.models.visitors.Invitation.Status",
        "IntercomCallStatusEnum": "core.models.access.IntercomCall.Status",
        "InvitationPurposeEnum": "core.models.visitors.Invitation.Purpose",
        "VisitPurposeEnum": "core.models.visitors.VisitPurpose",
        "BookingStatusEnum": "core.models.amenities.Booking.Status",
        "BookingPaymentStatusEnum": "core.models.amenities.Booking.Payment",
        "FeedbackStatusEnum": "core.models.community.Feedback.Status",
    },
}

REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        # redis-py 6+ times out socket reads after 5 s by default, which kills every WebSocket consumer
        # waiting on a blocking pop; the layer's own blocking timeout already bounds each read.
        "CONFIG": {"hosts": [{"address": REDIS_URL, "socket_timeout": None}]},
    },
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TIME_LIMIT = 60
CELERY_BEAT_SCHEDULE = {
    "expire-invitations": {
        "task": "core.tasks.expire_invitations",
        "schedule": crontab(minute="*/10"),
    },
    "expire-unpaid-bookings": {
        "task": "core.tasks.expire_unpaid_bookings",
        "schedule": crontab(minute="*/5"),
    },
    "flush-expired-tokens": {
        "task": "core.tasks.flush_expired_tokens",
        "schedule": crontab(hour=4, minute=15),
    },
    "platform-backup": {
        "task": "core.tasks.daily_platform_backup",
        "schedule": crontab(hour=2, minute=45),
    },
    "prune-backups": {
        "task": "core.tasks.prune_backups",
        "schedule": crontab(hour=4, minute=30),
    },
    "subscription-lifecycle": {
        "task": "core.tasks.subscription_lifecycle",
        "schedule": crontab(hour=8, minute=5),
    },
    "prune-email-log": {
        "task": "core.tasks.prune_email_log",
        "schedule": crontab(hour=4, minute=45),
    },
    "purge-visitor-data": {
        "task": "core.tasks.purge_visitor_data",
        "schedule": crontab(hour=3, minute=30),
    },
}

# Gate relays and LPR
RELAY_HTTP_TIMEOUT = env.float("RELAY_HTTP_TIMEOUT", default=5.0)
LPR_DEBOUNCE_SECONDS = env.int("LPR_DEBOUNCE_SECONDS", default=20)

# LiveKit Cloud video intercom
LIVEKIT_URL = env("LIVEKIT_URL", default="")
LIVEKIT_API_KEY = env("LIVEKIT_API_KEY", default="")
LIVEKIT_API_SECRET = env("LIVEKIT_API_SECRET", default="")
LIVEKIT_TOKEN_TTL_SECONDS = env.int("LIVEKIT_TOKEN_TTL_SECONDS", default=600)
# How long after a call starts the resident may still swipe to unlock.
INTERCOM_UNLOCK_WINDOW_SECONDS = env.int("INTERCOM_UNLOCK_WINDOW_SECONDS", default=600)

# Firebase Cloud Messaging (push to resident app). Path to a service-account JSON file
# mounted into the containers; leave blank to disable push.
FCM_SERVICE_ACCOUNT_FILE = env("FCM_SERVICE_ACCOUNT_FILE", default="")

# Kiosk AI assistant: platform OpenAI key when System settings leaves it blank.
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")

# Outgoing email (SMTP). System settings > Email overrides these when filled in.
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_SECURITY = env("EMAIL_SECURITY", default="starttls")  # starttls, ssl or none
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_FROM_ADDRESS = env("EMAIL_FROM_ADDRESS", default="")
EMAIL_FROM_NAME = env("EMAIL_FROM_NAME", default="Elix")
EMAIL_REPLY_TO = env("EMAIL_REPLY_TO", default="")
EMAIL_TIMEOUT = 15
EMAIL_LOG_KEEP_DAYS = 30

# Weather from NEA's realtime readings on data.gov.sg. Works without a key; a key raises the rate limit.
DATA_GOV_SG_API_KEY = env("DATA_GOV_SG_API_KEY", default="")

CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
    SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
