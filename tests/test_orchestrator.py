import unittest
from unittest.mock import patch

from backend.core.orchestrator import CoreOrchestrator


class FailingObserver:
    def __init__(self) -> None:
        self.calls = 0
        self.orchestrator: CoreOrchestrator | None = None

    def run(self) -> None:
        self.calls += 1
        if self.calls > 3:
            self.orchestrator.stopped.set()
            return
        raise RuntimeError("cycle failed")


class OrchestratorTests(unittest.TestCase):
    def test_repeated_failures_reach_exit_threshold(self) -> None:
        observer = FailingObserver()
        orchestrator = CoreOrchestrator(
            observer,
            observer_interval=1,
            max_consecutive_failures=3,
        )
        observer.orchestrator = orchestrator
        orchestrator._wait_or_stop = lambda _seconds: None

        with patch("backend.core.orchestrator.signal.signal"):
            exit_code = orchestrator.run()

        self.assertEqual(1, exit_code)
        self.assertEqual(3, observer.calls)


if __name__ == "__main__":
    unittest.main()
