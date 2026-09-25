"""Simulator HTTP calls with a total request budget and no retries."""

import asyncio
import math
from datetime import UTC, datetime
from typing import Any

import httpx

from . import settings as _settings

MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class ApiResponseError(RuntimeError):
    """The simulator response exceeded the supported body size."""


class ApiError(RuntimeError):
    """The simulator answered with a non-2xx status."""

    def __init__(self, status: int, body: Any, method: str = "", path: str = ""):
        self.status = status
        self.body = body
        self.method = method
        self.path = path
        super().__init__(f"{method} {path} -> HTTP {status}: {body}")


class ApiTimeout(TimeoutError):
    """The HTTP operation exceeded its budget; a write's outcome may be unknown."""


def _remaining(deadline_at: datetime, method: str, path: str) -> float:
    if deadline_at.utcoffset() is None:
        raise ValueError("HTTP deadline_at must have a timezone")
    remaining = (deadline_at - datetime.now(UTC)).total_seconds()
    if remaining <= 0:
        raise ApiTimeout(f"{method} {path}: deadline expired before dispatch; no request sent")
    return remaining


def _body(response: httpx.Response) -> Any:
    if "leash_body" in response.extensions:
        return response.extensions["leash_body"]
    if not response.content:
        return None
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return response.text


async def async_request(
    method: str, path: str, *, json: Any = None, params: dict | None = None,
    deadline_at: datetime | None = None,
) -> httpx.Response:
    """Bound connection, headers and the full response body by one absolute budget."""
    if deadline_at is not None:
        _remaining(deadline_at, method, path)
    settings = _settings.load()
    if not math.isfinite(settings.timeout_s) or settings.timeout_s <= 0:
        raise ValueError("HTTP timeout_s must be finite and positive")
    budget = settings.timeout_s
    if deadline_at is not None:
        budget = min(budget, _remaining(deadline_at, method, path))
    clock = asyncio.get_running_loop()
    stop_at = clock.time() + budget
    dispatched = False
    try:
        async with asyncio.timeout_at(stop_at):
            async with httpx.AsyncClient(
                base_url=settings.base_url,
                timeout=budget,
                headers={"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"},
            ) as client:
                if clock.time() >= stop_at:
                    raise TimeoutError("HTTP client setup exhausted the request budget")
                dispatched = True
                response = await client.request(method, path, json=json, params=params)
                if len(response.content) > MAX_RESPONSE_BYTES:
                    raise ApiResponseError(f"{method} {path}: response exceeds {MAX_RESPONSE_BYTES} bytes; remote outcome is unknown")
                response.extensions["leash_body"] = _body(response)
            if clock.time() >= stop_at:
                raise TimeoutError("HTTP response reading or decoding exceeded the request budget")
    except (TimeoutError, httpx.TimeoutException) as exc:
        outcome = "remote outcome is unknown" if dispatched else "no request sent"
        raise ApiTimeout(f"{method} {path}: total HTTP budget expired; {outcome}") from exc
    if not 200 <= response.status_code < 300:
        raise ApiError(response.status_code, _body(response), method, path)
    return response


def request(
    method: str, path: str, *, json: Any = None, params: dict | None = None,
    deadline_at: datetime | None = None,
) -> httpx.Response:
    """Synchronous boundary used by runner threads and synchronous app routes."""
    return asyncio.run(async_request(method, path, json=json, params=params, deadline_at=deadline_at))


def call(
    method: str, path: str, *, json: Any = None, params: dict | None = None,
    deadline_at: datetime | None = None,
) -> Any:
    """Make one bounded call and decode its body. An empty body returns None."""
    return _body(request(method, path, json=json, params=params, deadline_at=deadline_at))


def healthz() -> Any:
    return call("GET", "/healthz")


def bootstrap() -> Any:
    return call("GET", "/v1/bootstrap")
