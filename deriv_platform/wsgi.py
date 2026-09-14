import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

# get_wsgi_application() populates the app registry. Migrations MUST run after
# it, otherwise call_command("migrate") raises AppRegistryNotReady, the error
# is swallowed, and the /tmp SQLite tables are never created (500 on every
# DB-backed page).
application = get_wsgi_application()

if os.environ.get("VERCEL"):
    try:
        from deriv_platform.vercel_runtime import apply_vercel_migrations
        apply_vercel_migrations()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to apply Vercel migrations: {e}")

app = application
