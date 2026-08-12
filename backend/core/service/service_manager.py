"""Manage persisted service state and NextDNS blocking transitions."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from backend.core.service.exceptions import ServicesNotFoundError
from backend.core.service.models.service import Service
from backend.db.sqlite import SQLiteClient
from backend.next.nextdns_client import NextDNSClient


logger = logging.getLogger(__name__)
SEED_METADATA_KEY = "services_seeded"


class ServiceManager:
    """Manage service state using SQLite as the source of truth."""

    def __init__(
        self,
        db_client: SQLiteClient,
        nextdns_client: NextDNSClient,
        profile_id: str,
        services_path: str | Path,
    ) -> None:
        self.db_client = db_client
        self.nextdns_client = nextdns_client
        self.profile_id = profile_id
        self.services_path = Path(services_path)

    def get_seed_services(self) -> list[Service]:
        """Load services used only to seed a fresh database."""
        if not self.services_path.exists():
            raise ServicesNotFoundError(
                f"Services configuration file not found at {self.services_path}"
            )

        with self.services_path.open("r", encoding="utf-8") as services_file:
            services = json.load(services_file)

        return [
            Service(
                name=service["name"],
                nextdns_id=service.get("nextdns_id", service["name"].lower()),
                domains=service.get(
                    "domains",
                    [service["fallback_url"]] if service.get("fallback_url") else [],
                ),
                limit_minutes=int(service["limit_minutes"]),
                block_duration_minutes=int(service["block_duration_minutes"]),
            )
            for service in services
        ]

    def seed_services_once(self) -> bool:
        """Seed defaults once; later database edits remain authoritative."""
        seeded = self.db_client.fetch_one(
            "SELECT value FROM app_metadata WHERE key = ?",
            (SEED_METADATA_KEY,),
        )
        if seeded is not None:
            return False

        for service in self.get_seed_services():
            record = service.to_record()
            self.db_client.execute(
                """
                INSERT OR IGNORE INTO services (
                    name, nextdns_id, domains, fallback_url, limit_minutes,
                    block_duration_minutes, blocked, block_time,
                    current_usage_minutes, usage_reset_at, last_sync_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["name"],
                    record["nextdns_id"],
                    record["domains"],
                    record["fallback_url"],
                    record["limit_minutes"],
                    record["block_duration_minutes"],
                    record["blocked"],
                    record["block_time"],
                    record["current_usage_minutes"],
                    record["usage_reset_at"],
                    record["last_sync_error"],
                ),
            )

        self.db_client.execute(
            "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
            (SEED_METADATA_KEY, "1"),
        )
        logger.info("Seeded initial monitored services")
        return True

    def get_monitored_services_db(self) -> list[Service]:
        """Get monitored services from the authoritative database."""
        rows = self.db_client.fetch_all("SELECT * FROM services ORDER BY name")
        return [Service.from_record(row) for row in rows]

    def _record_sync_error(self, service: Service, error: Exception) -> None:
        """Record an error if blocking/unblocking fails, but don't raise it."""
        message = str(error)
        service.last_sync_error = message
        self.db_client.execute(
            "UPDATE services SET last_sync_error = ? WHERE name = ?",
            (message, service.name),
        )

    def _set_remote_state(self, service: Service, active: bool) -> None:
        """Try to set the remote blocking state, recording any errors for consideration on later retries."""
        try:
            self.nextdns_client.set_service_blocking(
                self.profile_id,
                service.nextdns_id,
                active,
                fallback_domains=service.domains,
            )
        except Exception as exc:
            self._record_sync_error(service, exc)
            raise

    def block(self, service: Service) -> None:
        """Block remotely before recording a successful local transition."""
        block_time = datetime.now(timezone.utc)
        self._set_remote_state(service, True)
        try:
            self.db_client.execute(
                """
                UPDATE services
                SET blocked = ?, block_time = ?, last_sync_error = NULL
                WHERE name = ?
                """,
                (True, block_time.isoformat(), service.name),
            )
        except Exception:
            logger.exception(
                "Local block update failed; attempting to restore NextDNS state"
            )
            try:
                self.nextdns_client.set_service_blocking(
                    self.profile_id,
                    service.nextdns_id,
                    False,
                    fallback_domains=service.domains,
                )
            except Exception:
                logger.exception("Could not restore NextDNS after local block failure")
            raise

        service.block_time = block_time
        service.blocked = True
        service.last_sync_error = None
        logger.info("Service %s has been blocked", service.name)

    def unblock(self, service: Service) -> None:
        """Unblock remotely, reset usage, then record the local transition."""
        usage_reset_at = datetime.now(timezone.utc)
        self._set_remote_state(service, False)
        try:
            self.db_client.execute(
                """
                UPDATE services
                SET blocked = ?, block_time = NULL, current_usage_minutes = ?,
                    usage_reset_at = ?, last_sync_error = NULL
                WHERE name = ?
                """,
                (False, 0, usage_reset_at.isoformat(), service.name),
            )
        except Exception:
            logger.exception(
                "Local unblock update failed; attempting to restore NextDNS state"
            )
            try:
                self.nextdns_client.set_service_blocking(
                    self.profile_id,
                    service.nextdns_id,
                    True,
                    fallback_domains=service.domains,
                )
            except Exception:
                logger.exception("Could not restore NextDNS after local unblock failure")
            raise

        service.block_time = None
        service.blocked = False
        service.current_usage_minutes = 0
        service.usage_reset_at = usage_reset_at
        service.last_sync_error = None
        logger.info("Service %s has been unblocked", service.name)

    def update_usage(self, service: Service, usage_minutes: int) -> None:
        """Update the current usage minutes for a service."""
        service.current_usage_minutes = usage_minutes
        self.db_client.execute(
            "UPDATE services SET current_usage_minutes = ? WHERE name = ?",
            (usage_minutes, service.name),
        )
        logger.info(
            "Service %s usage updated to %d minutes",
            service.name,
            usage_minutes,
        )
