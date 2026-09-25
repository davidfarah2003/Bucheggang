"""Simulator mandate client, as specified in docs/contracts.md "Runner mandate client".

Each function makes exactly one simulator call and raises
leash.runner.api.ApiError on any non-2xx. No retry, no fallback.
"""

from typing import Any, Mapping

from leash.policy.store import simulator_payload

from . import api


def _draft_dict(draft: Any) -> dict[str, Any]:
    if isinstance(draft, Mapping):
        return dict(draft)
    if hasattr(draft, "model_dump"):
        return draft.model_dump(mode="json")
    raise TypeError(f"draft must be a PolicyDraft or a mapping, got {type(draft).__name__}")


class UnexpectedResponse(RuntimeError):
    """A 2xx simulator response did not carry the field the contract needs."""


def _require(body: Any, key: str, where: str) -> str:
    if not isinstance(body, dict) or not isinstance(body.get(key), str) or not body[key]:
        raise UnexpectedResponse(f"POST {where} returned 2xx without {key}: {body}")
    return body[key]


def create(draft: Any, global_rules: list[dict[str, Any]] | None = None) -> str:
    """POST /v1/mandates with the simulator payload; returns the simulator draft_id."""
    body = api.call("POST", "/v1/mandates", json=simulator_payload(_draft_dict(draft), global_rules))
    return _require(body, "draft_id", "/v1/mandates")


def confirm(simulator_draft_id: str) -> str:
    """POST /v1/mandates/{draft_id}/confirm; returns mandate_id."""
    path = f"/v1/mandates/{simulator_draft_id}/confirm"
    body = api.call("POST", path, json={"confirmed": True})
    return _require(body, "mandate_id", path)


def get(mandate_id: str) -> dict:
    """GET /v1/mandates/{mandate_id}; the raw stored mandate."""
    return api.call("GET", f"/v1/mandates/{mandate_id}")


def tighten(mandate_id: str, patch: dict) -> dict:
    """PATCH /v1/mandates/{mandate_id}; returns the simulator response."""
    return api.call("PATCH", f"/v1/mandates/{mandate_id}", json=patch)


def revoke(mandate_id: str) -> None:
    """DELETE /v1/mandates/{mandate_id}."""
    api.call("DELETE", f"/v1/mandates/{mandate_id}")
