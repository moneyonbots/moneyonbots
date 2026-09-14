import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

# Apply Vercel migrations on startup for WSGI
if os.environ.get("VERCEL"):
    try:
        from deriv_platform.vercel_runtime import apply_vercel_migrations
        apply_vercel_migrations()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to apply Vercel migrations: {e}")

application = get_wsgi_application()
app = application
