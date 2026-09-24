"""HTTP client for the challenge simulator.

One call per method, a 30 s timeout, no retry. Any non-2xx raises ApiError.
"""

from typing import Any

import httpx

from . import settings as _settings


class ApiError(RuntimeError):
    """The simulator answered with a non-2xx status."""

    def __init__(self, status: int, body: Any, method: str = "", path: str = ""):
        self.status = status
        self.body = body
        self.method = method
        self.path = path
        super().__init__(f"{method} {path} -> HTTP {status}: {body}")


_client: httpx.Client | None = None


def client() -> httpx.Client:
    global _client
    if _client is None:
        s = _settings.load()
        _client = httpx.Client(
            base_url=s.base_url,
            timeout=s.timeout_s,
            headers={"Authorization": f"Bearer {s.api_key}", "Content-Type": "application/json"},
        )
    return _client


def _body(response: httpx.Response) -> Any:
    if not response.content:
        return None
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return response.text


def request(method: str, path: str, *, json: Any = None, params: dict | None = None) -> httpx.Response:
    """Make one call. Raises ApiError on any non-2xx; httpx errors propagate."""
    response = client().request(method, path, json=json, params=params)
    if not 200 <= response.status_code < 300:
        raise ApiError(response.status_code, _body(response), method, path)
    return response


def call(method: str, path: str, *, json: Any = None, params: dict | None = None) -> Any:
    """Make one call and return the decoded body (None for an empty body)."""
    return _body(request(method, path, json=json, params=params))


def healthz() -> Any:
    return call("GET", "/healthz")


def bootstrap() -> Any:
    return call("GET", "/v1/bootstrap")
