"""Value normalization helpers."""
from datetime import datetime, timezone


def parse_datetime(value: object) -> datetime | None:
    """Parse an ISO 8601 timestamp string into a UTC datetime object."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_domain(value: str) -> str:
    domain = value.strip().lower().rstrip(".")
    if domain.startswith("www."):
        domain = domain.removeprefix("www.")
    return domain
