"""Small synchronous client for the NextDNS API endpoints used by the worker."""

from collections.abc import Mapping
from typing import Any, Literal, Self
from urllib.parse import quote

from requests import Session
from requests.exceptions import RequestException, Timeout

from backend.config.config import Config
from backend.next.exceptions import NextDNSAPIError
from backend.next.nextdns_schemas import NextDNSLogPage


class NextDNSClient:
    def __init__(self) -> None:
        """Initialize the NextDNSClient with a session and configuration."""
        self._session: Session | None = None
        self._config = Config()
        self.nextdns_url = "https://api.nextdns.io"
        self.init()

    def init(self) -> Self:
        """Create a client with authentication and bounded request timeouts."""
        if self._session is not None:
            return self
        api_key = self._config.get_setting("NEXTDNS_API_KEY")
        if not isinstance(api_key, str):
            raise TypeError("NEXTDNS_API_KEY must be a string")
        session = Session()
        session.headers.update(
            {
                "X-Api-Key": api_key,
                "Accept": "application/json",
            }
        )
        self._session = session
        return self

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        json: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        """Make a request to the NextDNS API and handle errors."""
        if self._session is None:
            raise RuntimeError("NextDNS client is closed")
        try:
            response = self._session.request(
                method,
                f"{self.nextdns_url}{path}",
                params=params,
                json=json,
                timeout=(5, 10),
            )
        except Timeout as exc:
            raise NextDNSAPIError("NextDNS request timed out") from exc
        except RequestException as exc:
            raise NextDNSAPIError(f"NextDNS request failed: {exc}") from exc

        if response.status_code == 204:
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise NextDNSAPIError(
                "NextDNS returned a non-JSON response", status=response.status_code
            ) from exc

        if not isinstance(payload, dict):
            raise NextDNSAPIError(
                "NextDNS returned an invalid response", status=response.status_code
            )

        errors = payload.get("errors")
        # Explain the error if the HTTP status code indicates an error or if the payload contains an "errors" field.
        if response.status_code >= 400 or errors:
            detail = self._error_detail(errors) or f"HTTP {response.status_code}"
            raise NextDNSAPIError(
                f"NextDNS API error: {detail}", status=response.status_code
            )

        return payload

    def get(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
    ) -> dict[str, Any]:
        """Make a GET request to the NextDNS API."""
        return self._request("GET", path, params=params)

    def patch(
        self,
        path: str,
        *,
        json: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        """Make a PATCH request to the NextDNS API."""
        return self._request("PATCH", path, json=json)

    def post(
        self,
        path: str,
        *,
        json: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        """Make a POST request to the NextDNS API."""
        return self._request("POST", path, json=json)

    @staticmethod
    def _error_detail(errors: object) -> str | None:
        """Extract a human-readable error message from the NextDNS API response."""
        if not isinstance(errors, list) or not errors:
            return None
        first_error = errors[0]
        if not isinstance(first_error, dict):
            return str(first_error)
        detail = first_error.get("detail")
        code = first_error.get("code")
        if detail and code:
            return f"{code}: {detail}"
        return str(detail or code) if detail or code else None

    def get_logs_page(
        self,
        profile_id: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
        from_: str | None = None,
        to: str | None = None,
        sort: Literal["asc", "desc"] = "desc",
        device: str | None = None,
        status: Literal["default", "error", "blocked", "allowed"] | None = None,
        search: str | None = None,
        raw: bool = False,
    ) -> NextDNSLogPage:
        """
        Fetch one page from the query-log endpoint.

        Args:
            profile_id: The NextDNS profile ID.
            cursor: The pagination cursor for the next page.
            limit: The number of logs to fetch (between 10 and 1000).
            from_: The start time for the logs (ISO 8601 or relative format).
            to: The end time for the logs (ISO 8601 or relative format).
            sort: The sort order of the logs ('asc' or 'desc').
            device: Filter logs by device ID.
            status: Filter logs by status ('default', 'error', 'blocked', 'allowed').
            search: Filter logs by search term.
            raw: Whether to include raw log data in the response.

        Returns:
            A NextDNSLogPage object containing the logs, pagination cursor, and stream ID.
        Raises:
            ValueError: If limit is not between 10 and 1000, or if sort is not 'asc' or 'desc'.
            NextDNSAPIError: If the NextDNS API returns an error or an invalid response.

        """
        if not 10 <= limit <= 1000:
            raise ValueError("limit must be between 10 and 1000")
        if sort not in ("asc", "desc"):
            raise ValueError("sort must be 'asc' or 'desc'")

        params: dict[str, str | int] = {
            "limit": limit,
            "sort": sort,
        }
        optional_params: dict[str, str | None] = {
            "cursor": cursor,
            "from": from_,
            "to": to,
            "device": device,
            "status": status,
            "search": search,
        }
        params.update(
            {
                name: value
                for name, value in optional_params.items()
                if value is not None
            }
        )
        if raw:
            params["raw"] = 1

        encoded_profile_id = quote(profile_id, safe="")
        payload = self.get(
            f"/profiles/{encoded_profile_id}/logs", params=params
        )

        logs = payload.get("data")
        if not isinstance(logs, list) or not all(
            isinstance(log, dict) for log in logs
        ):
            raise NextDNSAPIError("NextDNS returned an invalid logs response")

        meta = payload.get("meta")
        if meta is None:
            meta = {}
        if not isinstance(meta, dict):
            raise NextDNSAPIError("NextDNS returned invalid logs metadata")

        pagination = meta.get("pagination", {})
        stream = meta.get("stream", {})
        if not isinstance(pagination, dict) or not isinstance(stream, dict):
            raise NextDNSAPIError("NextDNS returned invalid logs metadata")

        next_cursor = pagination.get("cursor")
        stream_id = stream.get("id")
        if next_cursor is not None and not isinstance(next_cursor, str):
            raise NextDNSAPIError("NextDNS returned an invalid pagination cursor")
        if stream_id is not None and not isinstance(stream_id, str):
            raise NextDNSAPIError("NextDNS returned an invalid stream ID")

        return NextDNSLogPage(logs=logs, cursor=next_cursor, stream_id=stream_id)

    def set_service_blocking(
        self,
        profile_id: str,
        service_id: str,
        active: bool,
        *,
        fallback_domains: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """Enable or disable blocking for a service in a NextDNS profile."""
        encoded_profile_id = quote(profile_id, safe="")
        encoded_service_id = quote(service_id, safe="")
        try:
            return self.patch(
                f"/profiles/{encoded_profile_id}/parentalControl/services/{encoded_service_id}",
                json={"active": active},
            )
        except NextDNSAPIError as exc:
            if exc.status != 404 or not fallback_domains:
                raise
            result: dict[str, Any] = {}
            for domain in fallback_domains:
                result = self.set_denylist_state(profile_id, domain, active)
            return result

    def is_domain_on_denylist(self, profile_id: str, domain: str) -> bool:
        """Return whether a domain exists in a profile's denylist."""
        encoded_profile_id = quote(profile_id, safe="")
        payload = self.get(f"/profiles/{encoded_profile_id}/denylist")
        entries = payload.get("data")
        if not isinstance(entries, list):
            raise NextDNSAPIError("NextDNS returned an invalid denylist")
        return any(
            isinstance(entry, dict) and entry.get("id") == domain
            for entry in entries
        )

    def set_denylist_state(
        self,
        profile_id: str,
        domain: str,
        active: bool,
    ) -> dict[str, Any]:
        """Add or update a domain in a profile's denylist."""
        encoded_profile_id = quote(profile_id, safe="")
        encoded_domain = quote(domain, safe="")

        if not self.is_domain_on_denylist(profile_id, domain):
            return self.post(
                f"/profiles/{encoded_profile_id}/denylist",
                json={"id": domain, "active": active},
            )

        return self.patch(
            f"/profiles/{encoded_profile_id}/denylist/{encoded_domain}",
            json={"active": active},
        )


    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        self.close()
