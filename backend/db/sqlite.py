"""Small SQLite client used by the application database layer."""
import json
import os
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Self

from backend.db.tables.services import (
    CREATE_APP_METADATA_TABLE_SQL,
    CREATE_SERVICES_TABLE_SQL,
)


Parameters = Mapping[str, object] | Sequence[object]


class SQLiteClient:

    def __init__(self, database_path: str | Path | None = None) -> None:
        path = database_path or os.getenv("DATABASE_PATH", "screennomore.db")
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row

    def initialize(self) -> None:
        """Create application tables and migrate the prototype schema."""
        self.execute(CREATE_SERVICES_TABLE_SQL)
        self.execute(CREATE_APP_METADATA_TABLE_SQL)
        columns = {
            row["name"]
            for row in self.fetch_all("PRAGMA table_info(services)")
        }
        migrations = {
            "nextdns_id": "ALTER TABLE services ADD COLUMN nextdns_id TEXT",
            "domains": "ALTER TABLE services ADD COLUMN domains TEXT",
            "usage_reset_at": "ALTER TABLE services ADD COLUMN usage_reset_at TEXT",
            "last_sync_error": "ALTER TABLE services ADD COLUMN last_sync_error TEXT",
        }
        for column, sql in migrations.items():
            if column not in columns:
                self.execute(sql)

        rows = self.fetch_all("SELECT * FROM services")
        for row in rows:
            if not row["nextdns_id"]:
                self.execute(
                    "UPDATE services SET nextdns_id = ? WHERE name = ?",
                    (str(row["name"]).lower(), row["name"]),
                )
            if not row["domains"]:
                fallback_url = (
                    row["fallback_url"]
                    if "fallback_url" in row.keys()
                    else ""
                )
                domain = str(fallback_url).lower().removeprefix("www.")
                self.execute(
                    "UPDATE services SET domains = ? WHERE name = ?",
                    (json.dumps([domain]), row["name"]),
                )

    def execute(
        self,
        sql: str,
        parameters: Parameters = (),
    ) -> sqlite3.Cursor:
        """Execute and commit one data-changing statement."""
        try:
            cursor = self.connection.execute(sql, parameters)
            self.connection.commit()
            return cursor
        except sqlite3.Error:
            self.connection.rollback()
            raise

    def fetch_one(
        self,
        sql: str,
        parameters: Parameters = (),
    ) -> sqlite3.Row | None:
        """Fetch one row for a parameterized query."""
        return self.connection.execute(sql, parameters).fetchone()

    def fetch_all(
        self,
        sql: str,
        parameters: Parameters = (),
    ) -> list[sqlite3.Row]:
        """Fetch all rows for a parameterized query."""
        return self.connection.execute(sql, parameters).fetchall()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        self.close()
