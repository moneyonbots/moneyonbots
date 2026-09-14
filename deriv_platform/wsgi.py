import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

# Apply Vercel migrations and collect static files on startup for WSGI
if os.environ.get("VERCEL"):
    try:
        from deriv_platform.vercel_runtime import apply_vercel_migrations
        apply_vercel_migrations()
        
        # Collect static files on Vercel startup
        from django.core.management import call_command
        call_command("collectstatic", "--noinput", "--clear", verbosity=0)
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Vercel migrations and static files collection completed")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to apply Vercel setup: {e}")

application = get_wsgi_application()
app = application
