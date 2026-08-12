CREATE_SERVICES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS services (
    name TEXT PRIMARY KEY,
    nextdns_id TEXT NOT NULL,
    domains TEXT NOT NULL,
    fallback_url TEXT NOT NULL,
    limit_minutes INTEGER NOT NULL,
    block_duration_minutes INTEGER NOT NULL,
    blocked INTEGER NOT NULL DEFAULT 0,
    block_time TEXT,
    current_usage_minutes INTEGER NOT NULL DEFAULT 0,
    usage_reset_at TEXT,
    last_sync_error TEXT
)
"""


CREATE_APP_METADATA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""
