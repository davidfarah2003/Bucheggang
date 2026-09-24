"""Accepted results on disk (plan 05 task 6).

Layout under data/ (the same root as the engine's data/state/):

- data/state/<mandate_id>.json: MandateState. The engine writes it through
  leash.engine.state.record; the runner only calls that function.
- data/decisions/<mandate_id>/<authorization_id>.json: the first accepted
  result for an authorization (the /decision submit).
- data/decisions/<mandate_id>/<authorization_id>.resolve.json: the /resolve
  result that closed a step_up.
- data/locks/<mandate_id>.lock: flock that serialises every write for one
  mandate across the run loop process and the API process.

Each decision file holds { decision, event, state_before, state_after,
accepted_at, accepted }. It is written only after the simulator accepted the
submit or resolve, and never overwritten (exclusive create). A missing or
malformed file raises.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from leash.contracts import Decision, Event, MandateState
from leash.engine import state as engine_state

DATA_DIR = engine_state.STATE_DIR.parent
DECISIONS_DIR = DATA_DIR / "decisions"
LOCKS_DIR = DATA_DIR / "locks"
RESOLVE_SUFFIX = ".resolve.json"


class RecordError(RuntimeError):
    """A decision record is missing, malformed or would be written twice."""


def _safe(name: str, what: str) -> str:
    if not name or "/" in name or name.startswith("."):
        raise ValueError(f"unusable {what} for a file name: {name!r}")
    return name


@contextmanager
def mandate_lock(mandate_id: str) -> Iterator[None]:
    """Exclusive lock for every state, decision and step-up write of one mandate."""
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(LOCKS_DIR / f"{_safe(mandate_id, 'mandate_id')}.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def write_exclusive(path: Path, value: dict[str, Any]) -> None:
    """Create `path` with `value`; raises FileExistsError if it is already there."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=1, default=str).encode("utf-8") + b"\n"
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(tmp, path)  # fails if path exists: never overwrite an accepted result
    os.unlink(tmp)


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    """Replace `path` with `value` in one rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=1, default=str).encode("utf-8") + b"\n"
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def record_accepted(
    event: Event, decision: Decision, accepted_at: datetime, accepted: Any, *, resolution: bool
) -> MandateState:
    """Record an accepted submit (resolution=False) or /resolve (resolution=True).

    The caller holds mandate_lock(event.mandate.mandate_id). Calls
    leash.engine.state.record, then writes the decision file. Returns the state after.
    """
    mandate_id = event.mandate.mandate_id
    auth_id = _safe(event.authorization.authorization_id, "authorization_id")
    state_before = engine_state.load(mandate_id)
    state_after = engine_state.record(mandate_id, event, decision)
    name = f"{auth_id}{RESOLVE_SUFFIX}" if resolution else f"{auth_id}.json"
    path = DECISIONS_DIR / _safe(mandate_id, "mandate_id") / name
    try:
        write_exclusive(path, {
            "decision": decision.model_dump(mode="json"),
            "event": event.model_dump(mode="json"),
            "state_before": state_before.model_dump(mode="json"),
            "state_after": state_after.model_dump(mode="json"),
            "accepted_at": accepted_at.isoformat(),
            "accepted": accepted,
        })
    except FileExistsError as exc:
        raise RecordError(f"{path} already exists; an accepted result is written once") from exc
    return state_after


def check_consistent(mandate_id: str) -> None:
    """Raise when decisions were recorded for a mandate but its state file is gone.

    leash.engine.state.load returns an empty state for a mandate with no file,
    which is right for a new mandate and wrong for one with recorded decisions.
    """
    folder = DECISIONS_DIR / _safe(mandate_id, "mandate_id")
    state_file = engine_state.STATE_DIR / f"{mandate_id}.json"
    if folder.is_dir() and any(folder.glob("*.json")) and not state_file.exists():
        raise RecordError(f"{folder} has recorded decisions but {state_file} is missing")


def _read(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text())
    for key in ("decision", "event", "state_before", "state_after", "accepted_at"):
        if key not in record:
            raise RecordError(f"{path} has no {key}")
    return record


def mandate_history(mandate_id: str) -> list[dict[str, Any]]:
    """[{decision, state_after}] oldest first. KeyError when the mandate has no decisions."""
    folder = DECISIONS_DIR / _safe(mandate_id, "mandate_id")
    if not folder.is_dir():
        raise KeyError(mandate_id)
    records = [_read(p) for p in folder.glob("*.json")]
    records.sort(key=lambda r: datetime.fromisoformat(r["accepted_at"]))
    return [
        {
            "decision": Decision.model_validate(r["decision"]),
            "state_after": MandateState.model_validate(r["state_after"]),
        }
        for r in records
    ]


def decision_detail(authorization_id: str) -> dict[str, Any]:
    """{decision, event, state_before, state_after} for the latest accepted result of one authorization.

    For a resolved step_up that is the /resolve result. KeyError when unknown.
    """
    auth_id = _safe(authorization_id, "authorization_id")
    resolved = list(DECISIONS_DIR.glob(f"*/{auth_id}{RESOLVE_SUFFIX}"))
    first = list(DECISIONS_DIR.glob(f"*/{auth_id}.json"))
    found = resolved or first
    if not found:
        raise KeyError(authorization_id)
    if len(found) > 1:
        raise RecordError(f"{authorization_id} is recorded under more than one mandate: {found}")
    r = _read(found[0])
    return {
        "decision": Decision.model_validate(r["decision"]),
        "event": Event.model_validate(r["event"]),
        "state_before": MandateState.model_validate(r["state_before"]),
        "state_after": MandateState.model_validate(r["state_after"]),
    }
