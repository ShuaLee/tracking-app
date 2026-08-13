import json
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .exceptions import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
    ResourceNotFoundError,
)


class JsonHttpClient:
    def __init__(self, *, base_url, timeout=10, default_headers=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.default_headers = dict(default_headers or {})

    def get(self, path, params=None):
        query = urlencode(
            {key: value for key, value in (params or {}).items() if value is not None},
            doseq=True,
        )
        url = f"{self.base_url}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{query}"
        request = Request(url, headers=self.default_headers, method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            if exc.code in {401, 403}:
                raise ProviderAuthenticationError("Provider credentials were rejected.") from exc
            if exc.code == 404:
                raise ResourceNotFoundError("Provider resource was not found.") from exc
            if exc.code == 429:
                raise ProviderRateLimitError(
                    "Provider rate limit was reached.", retry_after=retry_after
                ) from exc
            if exc.code >= 500:
                raise ProviderUnavailableError("Provider is temporarily unavailable.") from exc
            raise ProviderResponseError(f"Provider returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
            raise ProviderUnavailableError("Provider could not be reached.") from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderResponseError("Provider returned invalid JSON.") from exc
        if isinstance(payload, dict) and any(
            key in payload for key in ("Error Message", "error", "Error")
        ):
            raise ProviderResponseError("Provider returned an error response.")
        return payload

