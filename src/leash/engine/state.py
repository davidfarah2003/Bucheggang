"""Mandate state per mandate_id, persisted to data/state/<mandate_id>.json.

The engine is the only writer. `record` is called by the runner after the API
accepted a submit or /resolve, and does no simulator I/O.
"""

from __future__ import annotations

import os
from pathlib import Path

from leash.contracts import Approval, Decision, Event, MandateState

STATE_DIR = Path(__file__).resolve().parents[3] / "data" / "state"


class StateConflict(RuntimeError):
    """A recorded authorization is being recorded again with a different outcome."""


def _path(mandate_id: str) -> Path:
    if not mandate_id or "/" in mandate_id or mandate_id.startswith("."):
        raise ValueError(f"unusable mandate_id for a state file: {mandate_id!r}")
    return STATE_DIR / f"{mandate_id}.json"


def load(mandate_id: str) -> MandateState:
    """The saved state, or a new empty state when this mandate has none yet."""
    path = _path(mandate_id)
    if not path.exists():
        return MandateState(mandate_id=mandate_id)
    state = MandateState.model_validate_json(path.read_text())
    if state.mandate_id != mandate_id:
        raise StateConflict(f"{path} holds state for {state.mandate_id!r}, not {mandate_id!r}")
    return state


def _save(state: MandateState) -> None:
    path = _path(state.mandate_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(state.model_dump_json(indent=1))
    os.replace(tmp, path)


def apply(state: MandateState, event: Event, accepted: Decision) -> MandateState:
    """Pure: the state after recording `accepted`. Returns `state` itself when nothing changes."""
    auth = event.authorization
    auth_id = auth.authorization_id
    if accepted.authorization_id != auth_id:
        raise ValueError(f"decision is for {accepted.authorization_id}, event is {auth_id}")
    previous = state.handled.get(auth_id)
    if previous is not None:
        if previous.decision == accepted.decision:
            return state
        if previous.decision != "step_up" or accepted.decision == "step_up":
            raise StateConflict(
                f"{auth_id} was recorded as {previous.decision}; it cannot become {accepted.decision}"
            )
    new = state.model_copy(deep=True)
    if auth_id in new.pending_step_ups:
        new.pending_step_ups.remove(auth_id)
    if accepted.decision == "approve":
        new.approvals.append(
            Approval(
                authorization_id=auth_id,
                merchant_id=auth.merchant.merchant_id,
                amount_chf=auth.billing_amount_chf,  # delivery is already inside this amount
                timestamp=auth.timestamp,
            )
        )
    elif accepted.decision == "decline":
        new.declined.append(auth_id)
    else:
        new.pending_step_ups.append(auth_id)
    new.handled[auth_id] = accepted
    return new


def record(mandate_id: str, event: Event, accepted: Decision) -> MandateState:
    """Record a decision the API accepted. Idempotent; returns the saved state."""
    state = load(mandate_id)
    new = apply(state, event, accepted)
    if new is not state:
        _save(new)
    return new
