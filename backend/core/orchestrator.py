"""Orchestrate the core loop by observing behavior over time."""
import logging
import os
import signal
from pathlib import Path
from threading import Event

from backend.config.config import Config
from backend.core.observer import Observer

logger = logging.getLogger(__name__)


class CoreOrchestrator:

    def __init__(
        self,
        observer: Observer,
        observer_interval: float | None = None,
        max_consecutive_failures: int | None = None,
        health_file: str | Path | None = None,
    ) -> None:
        """Set up the orchestrator with an observer and configuration parameters.

        Args:
            observer: An instance of Observer that defines the behavior to observe.
            observer_interval: Time in seconds between fetching and observing behavior.
            """
        self.observer = observer
        self.config = Config()
        self.observer_interval = (
            observer_interval
            if observer_interval is not None
            else float(
                self.config.get_setting("OBSERVING_INTERVAL", default="5")
            )
        )
        self.max_consecutive_failures = (
            max_consecutive_failures
            if max_consecutive_failures is not None
            else int(self.config.get_setting("MAX_CONSECUTIVE_FAILURES", default="10"))
        )
        if self.observer_interval <= 0:
            raise ValueError("OBSERVING_INTERVAL must be greater than zero")
        if self.max_consecutive_failures <= 0:
            raise ValueError("MAX_CONSECUTIVE_FAILURES must be greater than zero")
        configured_health_file = health_file or os.getenv("HEALTH_FILE")
        self.health_file = (
            Path(configured_health_file) if configured_health_file else None
        )
        self.stopped = Event()

    def request_stop(self, signum: int, _frame: object) -> None:
        """Request shutdown signal to stop observing behavior"""
        logger.info("Received signal %s; shutting down", signum)
        self.stopped.set()

    def _wait_or_stop(self, seconds: float) -> None:
        self.stopped.wait(timeout=seconds)

    def _mark_healthy(self) -> None:
        if self.health_file is None:
            return
        self.health_file.parent.mkdir(parents=True, exist_ok=True)
        self.health_file.touch()

    def run(self) -> int:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)

        failures = 0
        logger.info("Worker started; interval=%ss", self.observer_interval)
        while not self.stopped.is_set():
            try:
                self.observer.run()
                failures = 0
                self._mark_healthy()
                self._wait_or_stop(self.observer_interval)
            except Exception:
                failures += 1
                logger.exception(
                    "Job failed (%s/%s)",
                    failures,
                    self.max_consecutive_failures,
                )
                if failures >= self.max_consecutive_failures:
                    logger.error("Too many consecutive failures; exiting for restart")
                    return 1
                self._wait_or_stop(min(60.0, 2.0**failures))
        logger.info("Worker stopped cleanly")
        return 0
