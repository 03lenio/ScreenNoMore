"""Health route"""
import time

from flask import Blueprint

from backend.config.config import Config

health_routes = Blueprint("health", __name__)

config = Config()


HEALTH_FILE = config.get_path_setting("HEALTH_FILE", "/health/healthy")
HEALTH_MAX_AGE_SECONDS = max(
    config.get_float_setting("HEALTH_MAX_AGE_SECONDS", "90"),
    config.get_float_setting("OBSERVING_INTERVAL", "30") * 3,
)


@health_routes.get("/health")
def health():
    """Health endpoint, checks for existence of health file and its lifetime"""
    try:
        is_healthy = time.time() - HEALTH_FILE.stat().st_mtime < HEALTH_MAX_AGE_SECONDS
    except OSError:
        is_healthy = False

    status = "healthy" if is_healthy else "unhealthy"
    return {"status": status}, 200 if is_healthy else 503
