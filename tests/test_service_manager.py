import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from backend.core.service.models.service import Service
from backend.core.service.service_manager import ServiceManager
from backend.db.sqlite import SQLiteClient
from backend.next.exceptions import NextDNSAPIError


SEED_PATH = (
    Path(__file__).resolve().parents[1]
    / "backend"
    / "core"
    / "service"
    / "services"
    / "services.json"
)


class FakeNextDNSClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bool, tuple[str, ...]]] = []
        self.error: Exception | None = None

    def set_service_blocking(
        self,
        profile_id: str,
        service_id: str,
        active: bool,
        *,
        fallback_domains: tuple[str, ...],
    ) -> dict:
        self.calls.append((profile_id, service_id, active, fallback_domains))
        if self.error is not None:
            raise self.error
        return {}


class ServiceManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_directory.name) / "test.db"
        self.database = SQLiteClient(database_path)
        self.database.initialize()
        self.nextdns = FakeNextDNSClient()
        self.manager = ServiceManager(
            self.database,
            self.nextdns,
            "profile",
            SEED_PATH,
        )
        self.manager.seed_services_once()

    def tearDown(self) -> None:
        self.database.close()
        self.temp_directory.cleanup()

    def test_seed_file_is_only_applied_once(self) -> None:
        self.database.execute("DELETE FROM services WHERE name = ?", ("Reddit",))

        seeded = self.manager.seed_services_once()

        self.assertFalse(seeded)
        self.assertIsNone(
            self.database.fetch_one(
                "SELECT name FROM services WHERE name = ?",
                ("Reddit",),
            )
        )

    def test_failed_remote_block_does_not_mark_service_blocked(self) -> None:
        service = self.manager.get_monitored_services_db()[0]
        self.nextdns.error = NextDNSAPIError("remote unavailable")

        with self.assertRaises(NextDNSAPIError):
            self.manager.block(service)

        row = self.database.fetch_one(
            "SELECT blocked, block_time, last_sync_error FROM services WHERE name = ?",
            (service.name,),
        )
        self.assertEqual(0, row["blocked"])
        self.assertIsNone(row["block_time"])
        self.assertEqual("remote unavailable", row["last_sync_error"])

    def test_block_state_survives_reload_and_unblock_resets_usage(self) -> None:
        service = self.manager.get_monitored_services_db()[0]
        self.manager.update_usage(service, service.limit_minutes)
        self.manager.block(service)

        reloaded = Service.from_record(
            self.database.fetch_one(
                "SELECT * FROM services WHERE name = ?",
                (service.name,),
            )
        )
        self.assertTrue(reloaded.blocked)
        self.assertTrue(
            reloaded.should_unblock(
                reloaded.block_time
                + timedelta(minutes=reloaded.block_duration_minutes)
            )
        )

        self.manager.unblock(reloaded)
        row = self.database.fetch_one(
            "SELECT * FROM services WHERE name = ?",
            (service.name,),
        )
        self.assertEqual(0, row["blocked"])
        self.assertIsNone(row["block_time"])
        self.assertEqual(0, row["current_usage_minutes"])
        self.assertIsNotNone(row["usage_reset_at"])


class DatabaseMigrationTests(unittest.TestCase):
    def test_prototype_service_rows_are_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            database_path = Path(temp_directory) / "legacy.db"
            connection = sqlite3.connect(database_path)
            connection.execute(
                """
                CREATE TABLE services (
                    name TEXT PRIMARY KEY,
                    limit_minutes INTEGER NOT NULL,
                    block_duration_minutes INTEGER NOT NULL,
                    fallback_url TEXT NOT NULL,
                    blocked INTEGER NOT NULL DEFAULT 0,
                    block_time TEXT,
                    current_usage_minutes INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                """
                INSERT INTO services VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("Reddit", 10, 30, "www.reddit.com", 0, "None", 2),
            )
            connection.commit()
            connection.close()

            database = SQLiteClient(database_path)
            database.initialize()
            service = Service.from_record(
                database.fetch_one("SELECT * FROM services WHERE name = 'Reddit'")
            )
            database.close()

            self.assertEqual("reddit", service.nextdns_id)
            self.assertEqual(("reddit.com",), service.domains)
            self.assertIsNone(service.block_time)


if __name__ == "__main__":
    unittest.main()
