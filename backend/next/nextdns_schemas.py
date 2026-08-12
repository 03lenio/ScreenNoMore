"""Schemas for modeling parsed NextDNS API responses."""
from dataclasses import dataclass
from typing import Any


# Logging

@dataclass(frozen=True, slots=True)
class NextDNSLogPage:
    """One page of query logs and its continuation cursor."""

    logs: list[dict[str, Any]]
    cursor: str | None
    stream_id: str | None = None