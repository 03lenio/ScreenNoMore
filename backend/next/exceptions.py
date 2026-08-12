"""Hold exceptions related to NextDNS API requests and responses."""

class NextDNSAPIError(RuntimeError):
    """Raised when NextDNS rejects a request or returns an invalid response."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status