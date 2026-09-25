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
import hashlib
import json
import math
import os
import re
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
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
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError(f"unusable {what} for a file name: {name!r}")
    return name


@contextmanager
def _file_lock(path: Path, *, stop_at: float | None = None) -> Iterator[None]:
    if stop_at is not None and not math.isfinite(stop_at):
        raise ValueError("lock deadline must be finite")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if stop_at is None:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        else:
            while True:
                remaining = stop_at - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"{path.name}: coordination deadline expired before acquiring the lock")
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(min(0.01, remaining))
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


@contextmanager
def customer_lock(customer: str, *, stop_at: float | None = None) -> Iterator[None]:
    """Guard owned-set enumeration, including a customer's first confirmation.

    Acquire this before any mandate lock. The digest keeps Unicode customer
    names within filesystem limits without placing raw names in lock paths.
    """
    if not isinstance(customer, str) or not customer:
        raise ValueError("customer lock requires an authenticated customer identity")
    name = hashlib.sha256(customer.encode("utf-8")).hexdigest()
    with _file_lock(LOCKS_DIR / "customer" / f"{name}.lock", stop_at=stop_at):
        yield


@contextmanager
def mandate_lock(mandate_id: str, *, stop_at: float | None = None) -> Iterator[None]:
    """Exclusive mandate lock. Mutation callers already hold their customer guard."""
    with _file_lock(LOCKS_DIR / f"{_safe(mandate_id, 'mandate_id')}.lock", stop_at=stop_at):
        yield


@contextmanager
def mandate_locks(mandate_ids: list[str], *, deadline_at: datetime, stop_at: float | None = None) -> Iterator[None]:
    """Nest the sorted owned set inside customer_lock. The first set may be empty."""
    if deadline_at.utcoffset() is None:
        raise ValueError("coordination deadline must have a timezone")
    wall_stop = time.monotonic() + (deadline_at - datetime.now(UTC)).total_seconds()
    stop_at = wall_stop if stop_at is None else min(stop_at, wall_stop)
    with ExitStack() as stack:
        for mandate_id in sorted(set(mandate_ids)):
            stack.enter_context(mandate_lock(mandate_id, stop_at=stop_at))
        if time.monotonic() >= stop_at:
            raise TimeoutError("coordination deadline expired after acquiring mandate locks")
        yield


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
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
    sync_directory(path.parent)
    sync_directory(path.parent.parent)


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
    sync_directory(path.parent)
    sync_directory(path.parent.parent)


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


def recover_accepted(
    event: Event, decision: Decision, accepted_at: datetime, accepted: Any,
    *, resolution: bool, state_before: MandateState,
) -> MandateState:
    """Finish a journaled accepted write once, including a crash after state.record.

    The caller holds all affected mandate locks and has verified the remote
    outcome. state_before is the persistent snapshot saved before dispatch.
    No new mutation may run until the journal has been completed.
    """
    mandate_id = event.mandate.mandate_id
    auth_id = _safe(event.authorization.authorization_id, "authorization_id")
    if state_before.mandate_id != mandate_id or event.authorization.mandate_id != mandate_id:
        raise RecordError(f"{auth_id}: journal event and state mandate differ")
    state_after = engine_state.apply(state_before, event, decision)
    expected = {
        "decision": decision.model_dump(mode="json"),
        "event": event.model_dump(mode="json"),
        "state_before": state_before.model_dump(mode="json"),
        "state_after": state_after.model_dump(mode="json"),
        "accepted_at": accepted_at.isoformat(),
        "accepted": accepted,
    }
    name = f"{auth_id}{RESOLVE_SUFFIX}" if resolution else f"{auth_id}.json"
    path = DECISIONS_DIR / _safe(mandate_id, "mandate_id") / name
    if path.exists() and _read(path) != expected:
        raise RecordError(f"{path}: saved outcome differs from the accepted intent")
    current = engine_state.load(mandate_id)
    if current != state_before and current != state_after:
        raise RecordError(f"{mandate_id}: state changed outside the unresolved intent")
    if current == state_before:
        current = engine_state.record(mandate_id, event, decision)
    if current != state_after:
        raise RecordError(f"{mandate_id}: recorded state differs from the intended transition")
    state_path = engine_state.STATE_DIR / f"{mandate_id}.json"
    with state_path.open("rb") as stream:
        os.fsync(stream.fileno())
    if not path.exists():
        write_exclusive(path, expected)
    for folder in (state_path.parent, state_path.parent.parent, path.parent, path.parent.parent):
        sync_directory(folder)
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
    """One latest accepted outcome per authorization, oldest first. Caller checks ownership."""
    with mandate_lock(mandate_id):
        folder = DECISIONS_DIR / _safe(mandate_id, "mandate_id")
        if folder.exists() and not folder.is_dir():
            raise RecordError(f"{folder} is not a decision directory")
        paths = list(folder.glob("*.json"))
        if not paths:
            state = engine_state.load(mandate_id)
            if state.handled or state.approvals or state.pending_step_ups or state.declined:
                raise RecordError(f"{mandate_id} has recorded state but no decision history")
            return []
        latest = {}
        for path in paths:
            record = _read(path)
            decision = Decision.model_validate(record["decision"])
            state = MandateState.model_validate(record["state_after"])
            auth_id = decision.authorization_id
            if path.name not in (f"{auth_id}.json", f"{auth_id}{RESOLVE_SUFFIX}") or state.mandate_id != mandate_id:
                raise RecordError(f"{path} has an authorization or mandate identity mismatch")
            accepted_at = datetime.fromisoformat(record["accepted_at"])
            if auth_id not in latest or path.name.endswith(RESOLVE_SUFFIX):
                latest[auth_id] = (accepted_at, {"decision": decision, "state_after": state})
        return [entry for _, entry in sorted(latest.values(), key=lambda item: item[0])]


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
