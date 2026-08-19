import logging
import os
from pathlib import Path

from backend.config.config import Config
from backend.core.observer import Observer
from backend.core.orchestrator import CoreOrchestrator
from backend.core.service.service_manager import ServiceManager
from backend.db.sqlite import SQLiteClient
from backend.next.nextdns_client import NextDNSClient

config = Config()

LOG_LEVEL = config.get_setting("LOG_LEVEL", default="INFO")

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("screennomore")


def _required_string(config: Config, name: str) -> str:
    value = config.get_setting(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _positive_int(name: str, value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed


def main() -> int:
    health_file = os.getenv("HEALTH_FILE")
    if health_file:
        Path(health_file).unlink(missing_ok=True)

    _required_string(config, "NEXTDNS_API_KEY")
    profile_id = _required_string(config, "NEXTDNS_PROFILE_ID")
    services_path = _required_string(config, "SERVICES_CONFIG_PATH")
    observing_last_minutes = int(config.get_setting("OBSERVING_LAST_LOGS_FROM_MINUTES", default="40"))
    max_log_pages = _positive_int(
        "MAX_LOG_PAGES",
        config.get_setting("MAX_LOG_PAGES"),
    )
    database_path = config.get_setting("DATABASE_CONFIG_PATH")

    with SQLiteClient(database_path) as sqlite_client:
        sqlite_client.initialize()
        with NextDNSClient() as nextdns_client:
            service_manager = ServiceManager(
                sqlite_client,
                nextdns_client,
                profile_id,
                services_path,
            )
            service_manager.seed_services_once()
            observer = Observer(
                nextdns_client,
                service_manager,
                profile_id,
                observing_last_minutes,
                max_log_pages,
            )
            return CoreOrchestrator(observer).run()


if __name__ == "__main__":
    raise SystemExit(main())
