"""Class for core service behaviour."""
import json
from collections.abc import Mapping
from datetime import datetime, timezone

from backend.core.util.normalization import normalize_domain, parse_datetime


class Service:

    def __init__(
        self,
        name: str,
        nextdns_id: str,
        domains: list[str] | tuple[str, ...],
        limit_minutes: int,
        block_duration_minutes: int,
        blocked: bool = False,
        block_time: datetime | None = None,
        current_usage_minutes: int = 0,
        usage_reset_at: datetime | None = None,
        last_sync_error: str | None = None,
    ) -> None:
        """Initialize a service with validation and normalization.

        Raises:
            ValueError: If any of the required fields are invalid.

        """
        normalized_domains = tuple(normalize_domain(domain) for domain in domains)
        if not name.strip():
            raise ValueError("Service name must not be empty")
        if not nextdns_id.strip():
            raise ValueError("NextDNS service ID must not be empty")
        if not normalized_domains or any(not domain for domain in normalized_domains):
            raise ValueError("A service must have at least one monitored domain")
        if limit_minutes <= 0:
            raise ValueError("Service usage limit must be greater than zero")
        if block_duration_minutes <= 0:
            raise ValueError("Service block duration must be greater than zero")

        self.name = name.strip()
        self.nextdns_id = nextdns_id.strip().lower()
        self.domains = normalized_domains
        self.limit_minutes = limit_minutes
        self.block_duration_minutes = block_duration_minutes
        self.blocked = blocked
        self.block_time = block_time
        self.current_usage_minutes = current_usage_minutes
        self.usage_reset_at = usage_reset_at
        self.last_sync_error = last_sync_error

    def to_record(self) -> dict[str, str | int | None]:
        """Serialize the service into SQLite-compatible values."""
        return {
            "name": self.name,
            "nextdns_id": self.nextdns_id,
            "domains": json.dumps(self.domains),
            "fallback_url": self.domains[0] if self.domains else "",
            "limit_minutes": self.limit_minutes,
            "block_duration_minutes": self.block_duration_minutes,
            "blocked": int(self.blocked),
            "block_time": self.block_time.isoformat() if self.block_time else None,
            "current_usage_minutes": self.current_usage_minutes,
            "usage_reset_at": (
                self.usage_reset_at.isoformat() if self.usage_reset_at else None
            ),
            "last_sync_error": self.last_sync_error,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> "Service":
        """Create a service from a database row."""
        keys = set(record.keys())
        domains_value = record["domains"] if "domains" in keys else None
        domains: list[str]
        if isinstance(domains_value, str) and domains_value:
            loaded_domains = json.loads(domains_value)
            domains = [str(domain) for domain in loaded_domains]
        else:
            fallback_url = record["fallback_url"] if "fallback_url" in keys else ""
            domains = [str(fallback_url)] if fallback_url else []

        return cls(
            name=str(record["name"]),
            nextdns_id=(
                str(record["nextdns_id"])
                if "nextdns_id" in keys and record["nextdns_id"]
                else str(record["name"]).lower()
            ),
            domains=domains,
            limit_minutes=int(record["limit_minutes"]),
            block_duration_minutes=int(record["block_duration_minutes"]),
            blocked=bool(record["blocked"]),
            block_time=parse_datetime(record["block_time"]),
            current_usage_minutes=int(record["current_usage_minutes"]),
            usage_reset_at=(
                parse_datetime(record["usage_reset_at"])
                if "usage_reset_at" in keys
                else None
            ),
            last_sync_error=(
                str(record["last_sync_error"])
                if "last_sync_error" in keys and record["last_sync_error"]
                else None
            ),
        )

    def should_block(self, usage_minutes: int) -> bool:
        """Determine if the service should be blocked based on usage.

        Args:
            usage_minutes (int): The usage minutes already recorded for the service.

        Returns:
            bool: True if the service should be blocked, False otherwise.
        """
        if self.blocked:
            return False
        return usage_minutes >= self.limit_minutes

    def should_unblock(self, now: datetime | None = None) -> bool:
        """Determine if the service should be unblocked based on block duration.

        Args:
            now (datetime | None): The current time to compare against. If None, uses the current UTC time.
        Returns:
            bool: True if the service should be unblocked, False otherwise.
        """
        if not self.blocked:
            return False
        if self.block_time is None:
            return False
        current_time = now or datetime.now(timezone.utc)
        elapsed_time = (current_time - self.block_time).total_seconds() / 60
        return elapsed_time >= self.block_duration_minutes
