import unittest
from datetime import datetime, timedelta, timezone

from backend.core.observer import Observer
from backend.core.service.models.service import Service
from backend.next.exceptions import NextDNSAPIError
from backend.next.nextdns_schemas import NextDNSLogPage


class PagingNextDNSClient:
    def __init__(self, pages: list[NextDNSLogPage]) -> None:
        self.pages = pages
        self.calls: list[str | None] = []

    def get_logs_page(self, _profile_id: str, **kwargs) -> NextDNSLogPage:
        self.calls.append(kwargs.get("cursor"))
        return self.pages[len(self.calls) - 1]


def make_service(**overrides) -> Service:
    values = {
        "name": "Youtube",
        "nextdns_id": "youtube",
        "domains": ["youtube.com", "googlevideo.com"],
        "limit_minutes": 2,
        "block_duration_minutes": 30,
    }
    values.update(overrides)
    return Service(**values)


class ObserverTests(unittest.TestCase):
    def test_scan_logs_follows_every_cursor(self) -> None:
        client = PagingNextDNSClient(
            [
                NextDNSLogPage([{"root": "youtube.com"}], "second"),
                NextDNSLogPage([{"root": "reddit.com"}], None),
            ]
        )
        observer = Observer(client, object(), "profile", 40)

        logs = observer.scan_logs()

        self.assertEqual(2, len(logs))
        self.assertEqual([None, "second"], client.calls)

    def test_scan_logs_fails_instead_of_silently_undercounting_at_cap(self) -> None:
        client = PagingNextDNSClient(
            [
                NextDNSLogPage([], "second"),
                NextDNSLogPage([], "third"),
            ]
        )
        observer = Observer(client, object(), "profile", 40, max_log_pages=2)

        with self.assertRaises(NextDNSAPIError):
            observer.scan_logs()

    def test_analysis_counts_unique_allowed_minutes_and_matching_domains(self) -> None:
        now = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
        service = make_service()
        observer = Observer(object(), object(), "profile", 40)
        logs = [
            {
                "root": "youtube.com",
                "timestamp": (now - timedelta(minutes=2)).isoformat(),
                "status": "default",
            },
            {
                "root": "r1---sn.googlevideo.com",
                "timestamp": (now - timedelta(minutes=1, seconds=40)).isoformat(),
                "status": "allowed",
            },
            {
                "root": "youtube.com",
                "timestamp": (now - timedelta(minutes=1)).isoformat(),
                "status": "default",
            },
            {
                "root": "youtube.com",
                "timestamp": now.isoformat(),
                "status": "blocked",
            },
            {
                "root": "notyoutube.com",
                "timestamp": now.isoformat(),
                "status": "default",
            },
            {
                "root": "youtube.com",
                "timestamp": (now - timedelta(minutes=41)).isoformat(),
                "status": "default",
            },
        ]

        usage = observer.analyse_logs(logs, [service], now)

        self.assertEqual(2, usage[service])
        self.assertTrue(service.should_block(usage[service]))

    def test_analysis_ignores_activity_before_cooldown_reset(self) -> None:
        now = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
        service = make_service(usage_reset_at=now - timedelta(minutes=2))
        observer = Observer(object(), object(), "profile", 40)
        logs = [
            {
                "root": "youtube.com",
                "timestamp": (now - timedelta(minutes=3)).isoformat(),
                "status": "default",
            },
            {
                "root": "youtube.com",
                "timestamp": (now - timedelta(minutes=1)).isoformat(),
                "status": "default",
            },
        ]

        usage = observer.analyse_logs(logs, [service], now)

        self.assertEqual(1, usage[service])


if __name__ == "__main__":
    unittest.main()
