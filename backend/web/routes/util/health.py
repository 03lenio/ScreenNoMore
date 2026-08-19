"""Health route"""
import os
import time
from pathlib import Path

from flask import Blueprint

health_routes = Blueprint("health", __name__)

HEALTH_FILE = Path(os.getenv("HEALTH_FILE", "/health/healthy"))
HEALTH_MAX_AGE_SECONDS = max(
    float(os.getenv("HEALTH_MAX_AGE_SECONDS", "90")),
    float(os.getenv("OBSERVING_INTERVAL", "30")) * 3,
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
