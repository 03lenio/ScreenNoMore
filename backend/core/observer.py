"""Observe NextDNS logs and apply service usage policies."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.core.service.models.service import Service
from backend.core.service.service_manager import ServiceManager
from backend.core.util.normalization import parse_datetime
from backend.next.exceptions import NextDNSAPIError
from backend.next.nextdns_client import NextDNSClient


logger = logging.getLogger(__name__)


class Observer:
    def __init__(
        self,
        nextdns_client: NextDNSClient,
        service_manager: ServiceManager,
        profile_id: str,
        observing_last_minutes: int,
        max_log_pages: int = 20,
    ) -> None:
        """Get ready to observe NextDNS logs and enforce service usage policies.

        Args:
            nextdns_client: An instance of NextDNSClient to fetch logs.
            service_manager: An instance of ServiceManager to manage service state.
            profile_id: The NextDNS profile ID to fetch logs for.
            observing_last_minutes: The time window in minutes to observe logs.
                                    e.g. if observing_last_minutes=40, logs from the last 40 minutes will be fetched.
            max_log_pages: The maximum number of log pages to fetch from NextDNS.

        Raises:
            ValueError: If observing_last_minutes or max_log_pages are not positive integers.
        """
        if observing_last_minutes <= 0:
            raise ValueError("OBSERVING_LAST_LOGS_FROM_MINUTES must be positive")
        if max_log_pages <= 0:
            raise ValueError("MAX_LOG_PAGES must be positive")
        self.nextdns_client = nextdns_client
        self.service_manager = service_manager
        self.profile_id = profile_id
        self.observing_last_minutes = observing_last_minutes
        self.max_log_pages = max_log_pages

    def scan_logs(self) -> list[dict[str, Any]]:
        """Fetch every log page in the configured observation window.

        Returns:
            A list of log entries, each represented as a dictionary.
        Raises:
            NextDNSAPIError: If the NextDNS API returns a repeated pagination cursor or if the maximum number
                             of log pages is exceeded.
        """
        logs: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()

        for _page_number in range(self.max_log_pages):
            page = self.nextdns_client.get_logs_page(
                self.profile_id,
                cursor=cursor,
                limit=1000,
                from_=f"-{self.observing_last_minutes}m",
            )
            logs.extend(page.logs)
            cursor = page.cursor
            if cursor is None:
                break
            if cursor in seen_cursors:
                raise NextDNSAPIError("NextDNS returned a repeated pagination cursor")
            seen_cursors.add(cursor)
        else:
            raise NextDNSAPIError(
                f"NextDNS log pagination exceeded MAX_LOG_PAGES={self.max_log_pages}"
            )

        logger.info("Fetched %s NextDNS log entries", len(logs))
        return logs

    @staticmethod
    def _matches_service(root: str, service: Service) -> bool:
        """Check if a log entry's root domain matches any of the service's domains."""
        normalized_root = root.lower().rstrip(".")
        return any(
            normalized_root == domain or normalized_root.endswith(f".{domain}")
            for domain in service.domains
        )

    def analyse_logs(
        self,
        logs: list[dict[str, Any]],
        services: list[Service],
        now: datetime | None = None,
    ) -> dict[Service, int]:
        """Count unique allowed-use minute buckets for each service."""
        current_time = now or datetime.now(timezone.utc)
        window_start = current_time - timedelta(minutes=self.observing_last_minutes)
        minutes_by_service: dict[Service, set[datetime]] = {
            service: set() for service in services
        }

        for log in logs:
            if log.get("status") in ("blocked", "error"):
                continue
            # Only consider logs that have a root domain and timestamp
            root = log.get("root")
            timestamp = parse_datetime(log.get("timestamp"))
            if not isinstance(root, str) or timestamp is None:
                continue
            if timestamp < window_start or timestamp > current_time:
                continue

            minute = timestamp.replace(second=0, microsecond=0)
            for service in services:
                usage_start = service.usage_reset_at or window_start
                if timestamp >= usage_start and self._matches_service(root, service):
                    minutes_by_service[service].add(minute)
        # Return the count of unique minutes for each service
        return {
            service: len(minutes)
            for service, minutes in minutes_by_service.items()
        }

    def run(self) -> None:
        """Run one finite observation and enforcement cycle."""
        services = self.service_manager.get_monitored_services_db()
        for service in services:
            if service.should_unblock():
                logger.info(
                    "Service '%s' block duration elapsed; unblocking",
                    service.name,
                )
                self.service_manager.unblock(service)

        if not services:
            logger.info("No services are currently monitored")
            return

        logs = self.scan_logs()
        monitoring_analysis = self.analyse_logs(logs, services)

        for service, usage_minutes in monitoring_analysis.items():
            logger.info(
                "Service '%s' used for %d minutes (limit: %d minutes)",
                service.name,
                usage_minutes,
                service.limit_minutes,
            )
            self.service_manager.update_usage(service, usage_minutes)
            if service.should_block(usage_minutes):
                logger.info(
                    "Service '%s' exceeded limit; blocking for %d minutes",
                    service.name,
                    service.block_duration_minutes,
                )
                self.service_manager.block(service)
