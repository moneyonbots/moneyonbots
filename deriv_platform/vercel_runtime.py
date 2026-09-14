import logging
import os

logger = logging.getLogger(__name__)


def apply_vercel_migrations():
    """Create tables on cold start so sessions/allauth don't 500 without a DB."""
    if not os.environ.get("VERCEL"):
        return
    if os.environ.get("VERCEL_MIGRATIONS_DONE"):
        return
    os.environ["VERCEL_MIGRATIONS_DONE"] = "1"
    try:
        from django.core.management import call_command

        call_command("migrate", "--run-syncdb", "--noinput", verbosity=0)
        logger.info("Vercel migrations applied")
    except Exception as e:
        logger.exception("Vercel migrations failed: %s", str(e))
        # Don't fail startup even if migrations fail
        pass
