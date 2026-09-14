"""
Django settings for deriv_platform.

Analysis-only trading dashboard: live Deriv charts + a market-wide
analysis window powered by an ML signal engine ported from bot.py.
No live order execution — paper positions only.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Try to load .env file if it exists, but don't fail if it doesn't (Vercel environment)
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)

# Production must be safe by default; local development can opt in to DEBUG.
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
IS_VERCEL = bool(os.environ.get("VERCEL"))
IS_PRODUCTION = IS_VERCEL or not DEBUG

# Use `or` (not getenv's default arg): an env var that exists but is EMPTY
# would otherwise yield "" and Django 5.2 raises ImproperlyConfigured, 500ing
# every request the moment the cookie signer touches SECRET_KEY.
SECRET_KEY = os.getenv("SECRET_KEY") or "django-insecure-default-key-for-deployment"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "ALLOWED_HOSTS",
        ".vercel.app,localhost,127.0.0.1,testserver,moneybots.vercel.app,moneyonbots.vercel.app",
    ).split(",")
    if host.strip()
]

# Vercel preview URLs (moneybots-xxxxx-team.vercel.app) 400 if ALLOWED_HOSTS
# is set in the dashboard to only the production hostname.
if IS_VERCEL:
    for host in (
        ".vercel.app",
        "moneybots.vercel.app",
        "moneyonbots.vercel.app",
        os.getenv("VERCEL_URL", ""),
        os.getenv("VERCEL_BRANCH_URL", ""),
        os.getenv("VERCEL_PROJECT_PRODUCTION_URL", ""),
    ):
        host = host.strip()
        if host and host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)

    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    CSRF_TRUSTED_ORIGINS = ["https://*.vercel.app"]
    for origin_host in (
        os.getenv("VERCEL_URL", ""),
        os.getenv("VERCEL_BRANCH_URL", ""),
        os.getenv("VERCEL_PROJECT_PRODUCTION_URL", ""),
        "moneybots.vercel.app",
        "moneyonbots.vercel.app",
    ):
        origin_host = origin_host.strip()
        if origin_host:
            origin = f"https://{origin_host}"
            if origin not in CSRF_TRUSTED_ORIGINS:
                CSRF_TRUSTED_ORIGINS.append(origin)

# Log production configuration without exposing secret values.
if IS_PRODUCTION:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    logger.warning(f"Running on Vercel - DEBUG={DEBUG}, ALLOWED_HOSTS={ALLOWED_HOSTS}")
    logger.info(f"DATABASE_URL configured: {bool(os.getenv('DATABASE_URL'))}")
    if SECRET_KEY == "django-insecure-default-key-for-deployment":
        logger.warning("SECRET_KEY is not configured; set it in Vercel environment variables")

INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "dashboard",
    "markets",
    "analysis",
    "positions",
    "news",
    "assistant",
    "stocks",
]

# Only install channels/daphne if not on Vercel (no WebSocket support)
if not IS_VERCEL:
    INSTALLED_APPS.insert(0, "daphne")
    INSTALLED_APPS.insert(6, "channels")

MIDDLEWARE = [
    "deriv_platform.middleware.VercelExceptionMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "deriv_platform.urls"

WSGI_APPLICATION = "deriv_platform.wsgi.application"
# Only set ASGI_APPLICATION if not on Vercel (no WebSocket support)
ASGI_APPLICATION = "deriv_platform.asgi.application" if not IS_VERCEL else None

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

# Analysis loop now runs integrated with the main Django server process
# using Django's startup signal. InMemoryChannelLayer works fine for
# single-process operation. Only configure if channels is installed.
if "channels" in INSTALLED_APPS:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

# Use SQLite locally. On Vercel the deploy filesystem is read-only, so
# SQLite must live in /tmp unless DATABASE_URL (Postgres) is set.
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    import dj_database_url
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=0,
            ssl_require="sslmode" not in DATABASE_URL.lower(),
        )
    }
elif IS_VERCEL:
    import tempfile
    from pathlib import Path

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(Path(tempfile.gettempdir()) / "deriv.sqlite3"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

if IS_VERCEL:
    SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Deriv API
# ---------------------------------------------------------------------------
DERIV_APP_ID = os.getenv("DERIV_APP_ID") or "1089"
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN") or ""  # Leave empty for public access
DERIV_WS_URL = os.getenv("DERIV_WS_URL") or f"wss://ws.derivws.com/websockets/v3?app_id={DERIV_APP_ID}"

# ---------------------------------------------------------------------------
# Paper trading (no live execution anywhere in this project)
# ---------------------------------------------------------------------------
PAPER_STARTING_BALANCE = float(os.getenv("PAPER_STARTING_BALANCE") or "10")

# ---------------------------------------------------------------------------
# Analysis engine
# ---------------------------------------------------------------------------
ANALYSIS_INTERVAL_SECONDS = int(os.getenv("ANALYSIS_INTERVAL_SECONDS") or "30")
MODEL_RETRAIN_HOURS = int(os.getenv("MODEL_RETRAIN_HOURS") or "6")
ML_MODELS_DIR = BASE_DIR / "ml_models"

# ---------------------------------------------------------------------------
# Email alerts — pulled from env, never hardcoded (see alerts/email_alerts.py)
# ---------------------------------------------------------------------------
EMAIL_CONFIG = {
    "HOST": os.getenv("EMAIL_HOST") or "smtp.gmail.com",
    "PORT": int(os.getenv("EMAIL_PORT") or "587"),
    "USE_TLS": (os.getenv("EMAIL_USE_TLS") or "True") == "True",
    "HOST_USER": os.getenv("EMAIL_HOST_USER") or "",
    "HOST_PASSWORD": os.getenv("EMAIL_HOST_PASSWORD") or "",
    "CONTACT_EMAIL": os.getenv("ALERT_CONTACT_EMAIL") or "",
}
ALERT_COOLDOWN_MINUTES = int(os.getenv("ALERT_COOLDOWN_MINUTES") or "240")

# ---------------------------------------------------------------------------
# AI chart assistant — floating "brain" chat panel + AI Chart page.
# Backend-only key; never sent to the browser. Panel degrades to a clear
# "not configured" message if this is left blank.
# ---------------------------------------------------------------------------
def _env_secret(name, default=""):
    value = os.getenv(name, default) or default
    return str(value).strip().strip('"').strip("'")


ANTHROPIC_API_KEY = _env_secret("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = _env_secret("ANTHROPIC_MODEL", "claude-sonnet-4-5")

GROQ_API_KEY = _env_secret("GROQ_API_KEY")
GROQ_MODEL = _env_secret("GROQ_MODEL", "llama-3.3-70b-versatile")

GEMINI_API_KEY = _env_secret("GEMINI_API_KEY")

# ---------------------------------------------------------------------------
# MT5 Live Trading Configuration - Removed for Vercel deployment (Windows-only)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# News Sentiment Analysis Configuration
# ---------------------------------------------------------------------------
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY") or ""
NEWS_CACHE_FILE = BASE_DIR / "news_cache.pkl"
NEWS_CACHE_DURATION = int(os.getenv("NEWS_CACHE_DURATION") or "3600")  # 1 hour

# ---------------------------------------------------------------------------
# Google OAuth Configuration (django-allauth)
# ---------------------------------------------------------------------------
SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# allauth settings
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "none"  # Disabled for development
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = False
ACCOUNT_UNIQUE_EMAIL = True

# Social account settings
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            "secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "key": "",
        },
        "SETTINGS": {
            "domain": os.getenv("SITE_DOMAIN", "localhost:8000"),
            "scope": ["profile", "email"],
            "auth_params": {
                "access_type": "online",
            },
        },
    }
}

# Login/Logout URLs
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"
