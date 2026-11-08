"""Django settings, driven by environment variables.

Secure by default: with ``DEBUG`` off (the default) a real ``SECRET_KEY`` is
required and HTTPS-related protections are switched on. See docs/deployment.md.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
# Load a local .env if present. Real environment variables always win.
# Set DJANGO_READ_DOT_ENV_FILE=false to skip it (the test suite does).
if env.bool("DJANGO_READ_DOT_ENV_FILE", default=True):
    environ.Env.read_env(BASE_DIR / ".env")

# --- Core -----------------------------------------------------------------

DEBUG = env.bool("DEBUG", default=False)

if DEBUG:
    SECRET_KEY = env("SECRET_KEY", default="insecure-dev-only-key-do-not-use-in-production")
else:
    # Raises ImproperlyConfigured when missing: there is no production default.
    SECRET_KEY = env("SECRET_KEY")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sitemaps",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    # Installed always; a provider only shows up once its keys are set (docs/auth.md).
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.github",
    "apps.core",
    "apps.accounts",
    "apps.billing",
    "apps.example",
    "apps.ai",
    "apps.blog",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
            ],
        },
    },
]

# --- Database -------------------------------------------------------------

# With Litestream (LITESTREAM_REPLICA_URL set) the database is the SQLite file at DB_PATH, so every
# process in the container (gunicorn, `docker exec ... manage.py`) opens the replicated file.
_DEFAULT_SQLITE = (
    env("DB_PATH", default="/data/db.sqlite3")
    if env("LITESTREAM_REPLICA_URL", default="")
    else str(BASE_DIR / "db.sqlite3")
)
DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{_DEFAULT_SQLITE}")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
if "sqlite" in DATABASES["default"]["ENGINE"]:
    # Production-ready SQLite: WAL (needed by Litestream, lets reads run during a write), NORMAL sync
    # (safe with WAL), wait for the single writer instead of failing, and BEGIN IMMEDIATE so a write
    # transaction never fails halfway with "database is locked".
    DATABASES["default"]["OPTIONS"] = {
        **DATABASES["default"].get("OPTIONS", {}),
        "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;",
        "transaction_mode": "IMMEDIATE",
        "timeout": 20,
    }
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Auth -----------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "account-settings"
LOGOUT_REDIRECT_URL = "home"

# django-allauth: email is the only login identifier, there is no username.
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
# "none" | "optional" | "mandatory"
ACCOUNT_EMAIL_VERIFICATION = env("ACCOUNT_EMAIL_VERIFICATION", default="optional")
ACCOUNT_UNIQUE_EMAIL = True

# Social login (OFF until keys are set). Each provider appears on the login and signup pages
# only when both <PROVIDER>_CLIENT_ID and <PROVIDER>_CLIENT_SECRET are set (docs/auth.md).
SOCIAL_PROVIDER_DEFAULTS: dict[str, dict] = {
    "google": {"SCOPE": ["openid", "email", "profile"], "AUTH_PARAMS": {"access_type": "online"}},
    "github": {"SCOPE": ["read:user", "user:email"]},
}
SOCIALACCOUNT_PROVIDERS: dict[str, dict] = {}
for _provider, _defaults in SOCIAL_PROVIDER_DEFAULTS.items():
    _client_id = env(f"{_provider.upper()}_CLIENT_ID", default="")
    _secret = env(f"{_provider.upper()}_CLIENT_SECRET", default="")
    if _client_id and _secret:
        SOCIALACCOUNT_PROVIDERS[_provider] = {
            **_defaults,
            "APPS": [{"client_id": _client_id, "secret": _secret, "key": ""}],
        }
SOCIALACCOUNT_ADAPTER = "apps.accounts.adapters.SocialAccountAdapter"
SOCIALACCOUNT_EMAIL_REQUIRED = True  # every user needs an email; asked for if the provider has none
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_STORE_TOKENS = False  # sign-in only: no provider tokens kept in the database
# Sign-in starts with a POST (CSRF-protected), never a GET link. Leave this off.
SOCIALACCOUNT_LOGIN_ON_GET = False
# A provider login is NOT auto-linked to an existing password account with the same email
# (that would let anyone who controls the email at the provider take over the account).
# Users link providers from /accounts/3rdparty/ after signing in.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False

# --- Static files ---------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# --- Private attachments (OFF by default) ---------------------------------

UPLOADS_ENABLED = env.bool("UPLOADS_ENABLED", default=False)
UPLOAD_MAX_FILE_BYTES = env.int("UPLOAD_MAX_FILE_BYTES", default=5 * 1024 * 1024)
MEDIA_ROOT = BASE_DIR / "media"
# Deliberately no MEDIA_URL route: every download must pass the owner check.
GS_BUCKET_NAME = env("GS_BUCKET_NAME", default="")
if GS_BUCKET_NAME:
    _private_storage: dict = {
        "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
        "OPTIONS": {
            "bucket_name": GS_BUCKET_NAME,
            "default_acl": None,
            "querystring_auth": True,
            "file_overwrite": False,
        },
    }
    STORAGES["default"] = _private_storage

# --- MFA and verified email changes (enrolment OFF by default) -------------

# Always install the MFA stages: disabling enrolment must never bypass existing MFA.
INSTALLED_APPS.insert(INSTALLED_APPS.index("apps.accounts"), "allauth.mfa")
MFA_ENROLLMENT_ENABLED = env.bool("MFA_ENROLLMENT_ENABLED", default=False)
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TRUST_ENABLED = False
MFA_ADAPTER = "apps.accounts.mfa.MFAAdapter"
MFA_FORMS = {
    "authenticate": "apps.accounts.mfa.AuthenticateForm",
    "reauthenticate": "apps.accounts.mfa.ReauthenticateForm",
    "activate_totp": "apps.accounts.mfa.ActivateTOTPForm",
}
ACCOUNT_REAUTHENTICATION_REQUIRED = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = False
ACCOUNT_FORMS = {"add_email": "apps.accounts.mfa.AddEmailForm"}

# --- Internationalisation -------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- REST framework -------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", default="60/min"),
        "user": env("THROTTLE_USER", default="300/min"),
        "auth": env("THROTTLE_AUTH", default="10/min"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Django SaaS Starter API",
    "DESCRIPTION": "Session-authenticated JSON API. Unsafe methods need the CSRF token.",
    "VERSION": "0.2.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
}

# --- Billing (OFF by default) --------------------------------------------

BILLING_ENABLED = env.bool("BILLING_ENABLED", default=False)
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")
BILLING_SUCCESS_URL = env("BILLING_SUCCESS_URL", default="http://localhost:8000/account/?billing=success")
BILLING_CANCEL_URL = env("BILLING_CANCEL_URL", default="http://localhost:8000/account/?billing=cancelled")
BILLING_PORTAL_RETURN_URL = env("BILLING_PORTAL_RETURN_URL", default="http://localhost:8000/account/")

# --- Scheduled jobs trigger (OFF by default) -----------------------------

# POST /internal/jobs/run/ runs the registered jobs (apps/core/job_trigger.py, docs/deployment.md).
# Google Cloud Scheduler: set both of these (the deploy script does).
JOBS_OIDC_AUDIENCE = env("JOBS_OIDC_AUDIENCE", default="")
JOBS_INVOKER_EMAIL = env("JOBS_INVOKER_EMAIL", default="")
# Any other scheduler: a long random bearer token. Keep it in a secret manager.
JOBS_TRIGGER_TOKEN = env("JOBS_TRIGGER_TOKEN", default="")
if JOBS_TRIGGER_TOKEN and len(JOBS_TRIGGER_TOKEN) < 32:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("JOBS_TRIGGER_TOKEN must be at least 32 characters (use a random value).")

# --- AI assistant demo (OFF until ANTHROPIC_API_KEY is set) --------------

# /ai/ for signed-in users (apps/ai, docs/ai.md). The key belongs in a secret manager.
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
AI_MODEL = env("AI_MODEL", default="claude-opus-5-5")
AI_EFFORT = env("AI_EFFORT", default="low")  # low | medium | high | xhigh | max
AI_MAX_INPUT_CHARS = env.int("AI_MAX_INPUT_CHARS", default=20000)

# --- Email ----------------------------------------------------------------

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Django SaaS Starter <noreply@example.com>")
SITE_NAME = env("SITE_NAME", default="Django SaaS Starter")

# --- Security -------------------------------------------------------------

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
CONTENT_SECURITY_POLICY = env(
    "CONTENT_SECURITY_POLICY",
    default="default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'",
)
# Paths that skip the CSP header (Swagger UI and admin use inline scripts/styles).
CSP_EXEMPT_PREFIXES = ("/api/docs/", "/admin/")

# Behind a TLS-terminating proxy (Cloud Run, Fly, most PaaS) set this to true so
# Django trusts X-Forwarded-Proto. Only enable it if your proxy sets/strips the header.
if env.bool("TRUST_PROXY_SSL_HEADER", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not DEBUG)
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=not DEBUG)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0 if DEBUG else 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
# HSTS preload is hard to undo, so it is opt-in. Intentional exception to `check --deploy`.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# --- Logging --------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

# --- Plausible analytics (OFF by default) --------------------------------

# When set (e.g. "example.com"), public pages load the hosted Plausible script
# with that data-domain, and CSP allows plausible.io. Empty = nothing injected.
PLAUSIBLE_DOMAIN = env("PLAUSIBLE_DOMAIN", default="")
if PLAUSIBLE_DOMAIN:
    CONTENT_SECURITY_POLICY = (
        f"{CONTENT_SECURITY_POLICY}; "
        "script-src 'self' https://plausible.io; "
        "connect-src 'self' https://plausible.io"
    )

# --- Staff analytics dashboard -------------------------------------------

# Always on for staff at /admin/dashboard/ (linked from the admin index).
# No env flag: the page is harmless and gated by is_staff.

# --- Blog ----------------------------------------------------------------

# Public Markdown blog at /blog/ (empty until you publish posts in admin).
# Markdown + nh3 sanitisation live in apps.blog.markdown.
