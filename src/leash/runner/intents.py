"""Write-ahead records for remote mutations. Callers hold the mandate lock.

A prepared intent remains unresolved after any exception or process exit.
Only an observed response and durable local recording can complete it.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from leash.contracts import Decision, Event, MandateState

from . import records

INTENTS_DIR = records.DATA_DIR / "intents"
Operation = Literal["submit", "resolve", "tighten", "revoke"]


class UnresolvedMutation(RuntimeError):
    """A prior mutation must be reconciled before another can be dispatched."""


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    intent_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    mandate_id: str = Field(min_length=1)
    operation: Operation
    method: Literal["POST", "PATCH", "DELETE"]
    path: str = Field(min_length=1)
    body: dict[str, Any] | None
    context: dict[str, Any]
    created_at: AwareDatetime
    deadline_at: AwareDatetime
    status: Literal["prepared", "accepted", "recorded"]
    accepted_at: AwareDatetime | None = None
    accepted: Any = None

    @model_validator(mode="after")
    def consistent(self) -> "Intent":
        records._safe(self.mandate_id, "mandate_id")
        if self.deadline_at <= self.created_at:
            raise ValueError("intent deadline must follow its creation")
        method = {"submit": "POST", "resolve": "POST", "tighten": "PATCH", "revoke": "DELETE"}[self.operation]
        if self.method != method:
            raise ValueError("intent method differs from its operation")
        if self.operation in ("submit", "resolve"):
            auth_id = records._safe(self.context["authorization_id"], "authorization_id")
            suffix = "decision" if self.operation == "submit" else "resolve"
            expected = f"/v1/authorizations/{auth_id}/{suffix}"
            if not isinstance(self.body, dict) or self.body.get("decision") not in ("approve", "decline", "step_up"):
                raise ValueError("authorization intent has no decision payload")
            if self.operation == "submit" and self.body.get("authorization_id") != auth_id:
                raise ValueError("submission payload authorization differs")
            if self.operation == "resolve" and self.body["decision"] == "step_up":
                raise ValueError("a resolution cannot request another step-up")
            event = Event.model_validate(self.context["event"])
            decision = Decision.model_validate(self.context["decision"])
            before = MandateState.model_validate(self.context["state_before"])
            if (event.authorization.authorization_id != auth_id or decision.authorization_id != auth_id
                    or event.mandate.mandate_id != self.mandate_id
                    or event.authorization.mandate_id != self.mandate_id or before.mandate_id != self.mandate_id):
                raise ValueError("intent event, decision and state identities differ")
            if decision.decision != self.body["decision"] or decision.customer_message != self.body.get("customer_message"):
                raise ValueError("intent decision differs from the dispatch payload")
            if not isinstance(self.context.get("run_id"), str) or not self.context["run_id"]:
                raise ValueError("authorization intent requires the originating run_id")
        else:
            expected = f"/v1/mandates/{self.mandate_id}"
            before = self.context["remote_before"]
            if not isinstance(before, dict) or before.get("mandate_id") != self.mandate_id:
                raise ValueError("mandate intent needs its bound pre-mutation response")
            if not all(isinstance(before.get(key), str) and before[key] for key in ("draft_id", "instruction")):
                raise ValueError("mandate intent lacks its confirmed draft binding")
            if self.operation == "revoke" and self.body is not None:
                raise ValueError("revocation must not carry a request body")
            if self.operation == "tighten" and (not isinstance(self.body, dict) or not self.body):
                raise ValueError("tightening requires its request payload")
        if self.path != expected:
            raise ValueError("intent path differs from its bound operation")
        if self.status == "prepared" and (self.accepted_at is not None or self.accepted is not None):
            raise ValueError("prepared intent cannot contain an accepted response")
        if self.status != "prepared":
            if self.accepted_at is None:
                raise ValueError("accepted intent must record its observation time")
            verify_response(self, self.accepted)
        return self


def verify_response(intent: Intent, accepted: Any) -> None:
    """Reject an unexpected result before recording any financial state."""
    if not isinstance(accepted, dict):
        raise UnresolvedMutation(f"{intent.intent_id}: mutation result must be an object")
    if intent.operation in ("submit", "resolve"):
        auth_id = intent.context["authorization_id"]
        expected = intent.body
        decision = accepted.get("decision")
        status = {"approve": "approved", "decline": "declined", "step_up": "pending_step_up"}[expected["decision"]]
        if (accepted.get("authorization_id") != auth_id or accepted.get("status") != status
                or not isinstance(decision, dict) or decision.get("authorization_id") != auth_id
                or decision.get("decision") != expected["decision"]):
            raise UnresolvedMutation(f"{intent.intent_id}: observed authorization result differs from the intent")
        source = "team" if intent.operation == "submit" else "human"
        if decision.get("decision_source") != source:
            raise UnresolvedMutation(f"{intent.intent_id}: observed decision source differs")
        fields = ("customer_message", "evidence", "reason_codes", "engine_version") if intent.operation == "submit" else ("customer_message", "evidence")
        if any(decision.get(key) != expected[key] for key in fields):
            raise UnresolvedMutation(f"{intent.intent_id}: observed decision payload differs")
    else:
        if accepted.get("mandate_id") != intent.mandate_id:
            raise UnresolvedMutation(f"{intent.intent_id}: observed mandate differs")
        before = intent.context["remote_before"]
        if any(accepted.get(key) != before[key] for key in ("draft_id", "instruction")):
            raise UnresolvedMutation(f"{intent.intent_id}: observed mandate binding differs")
        if intent.operation == "revoke":
            if accepted.get("status") != "revoked":
                raise UnresolvedMutation(f"{intent.intent_id}: revocation is not confirmed by the simulator")
        else:
            for key, value in intent.body.items():
                actual = accepted.get(key)
                if key == "hard_rules" and isinstance(actual, list):
                    actual = [{k: v for k, v in rule.items() if v is not None} for rule in actual]
                if actual != value:
                    raise UnresolvedMutation(f"{intent.intent_id}: observed tightened {key} differs")


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _make_directories(path: Path) -> None:
    missing = []
    while not path.exists():
        missing.append(path)
        path = path.parent
    for folder in reversed(missing):
        folder.mkdir(mode=0o700, exist_ok=True)
        _sync_directory(folder.parent)


def _persist(path: Path, intent: Intent, *, exclusive: bool) -> None:
    _make_directories(path.parent)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(intent.model_dump(mode="json"), stream, allow_nan=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


class MutationJournal:
    def __init__(self, root: Path = INTENTS_DIR):
        self.root = Path(root)

    def _path(self, mandate_id: str, intent_id: str) -> Path:
        return self.root / records._safe(mandate_id, "mandate_id") / f"{records._safe(intent_id, 'intent_id')}.json"

    def read(self, mandate_id: str, intent_id: str) -> Intent:
        path = self._path(mandate_id, intent_id)
        intent = Intent.model_validate_json(path.read_text())
        if intent.mandate_id != mandate_id or intent.intent_id != intent_id:
            raise UnresolvedMutation(f"{path}: mutation identity differs from its saved path")
        return intent

    def pending(self, mandate_id: str) -> list[Intent]:
        folder = self.root / records._safe(mandate_id, "mandate_id")
        if folder.exists() and not folder.is_dir():
            raise UnresolvedMutation(f"{folder}: intent store is not a directory")
        intents = [self.read(mandate_id, path.stem) for path in sorted(folder.glob("*.json"))]
        return [intent for intent in intents if intent.status != "recorded"]

    def require_clear(self, mandate_ids: list[str]) -> None:
        for mandate_id in sorted(set(mandate_ids)):
            pending = self.pending(mandate_id)
            if pending:
                raise UnresolvedMutation(f"{mandate_id}: mutation {pending[0].intent_id} is unresolved; dispatch refused")

    def prepare(
        self, mandate_id: str, operation: Operation, *, method: str, path: str,
        body: dict | None, context: dict, deadline_at: datetime,
    ) -> Intent:
        self.require_clear([mandate_id])
        intent = Intent(
            intent_id=uuid4().hex, mandate_id=mandate_id, operation=operation,
            method=method, path=path, body=body, context=context,
            created_at=datetime.now(UTC), deadline_at=deadline_at, status="prepared",
        )
        _persist(self._path(mandate_id, intent.intent_id), intent, exclusive=True)
        return intent

    def accept(self, intent: Intent, accepted: Any, accepted_at: datetime) -> Intent:
        current = self.read(intent.mandate_id, intent.intent_id)
        if current != intent or current.status != "prepared":
            raise UnresolvedMutation(f"{intent.intent_id}: only the unchanged prepared mutation can be accepted")
        verify_response(current, accepted)
        updated = Intent.model_validate({**current.model_dump(mode="python"), "status": "accepted",
                                         "accepted": accepted, "accepted_at": accepted_at})
        _persist(self._path(intent.mandate_id, intent.intent_id), updated, exclusive=False)
        return updated

    def complete(self, intent: Intent) -> Intent:
        current = self.read(intent.mandate_id, intent.intent_id)
        if current != intent or current.status != "accepted":
            raise UnresolvedMutation(f"{intent.intent_id}: only an unchanged accepted mutation can be recorded")
        updated = Intent.model_validate({**current.model_dump(mode="python"), "status": "recorded"})
        _persist(self._path(intent.mandate_id, intent.intent_id), updated, exclusive=False)
        return updated
