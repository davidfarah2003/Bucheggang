"""Customer-only mandate read, tightening and revocation routes."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, model_validator

from leash.contracts import Mandate, MandateState, PolicyDraft, Rule
from leash.policy.global_policy import rules_hash
from leash.policy.ownership import owned_confirmations
from leash.policy.store import DraftStore
from leash.runner import mandates, records
from leash.runner.coordinator import Coordinator
from leash.runner.intents import UnresolvedMutation
from leash.runner.stepups import StepUpBook
from leash.runner.api import ApiError, ApiTimeout


class TightenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: list[Rule] | None = None
    uncertainty_policy: str | None = None

    @model_validator(mode="after")
    def one_change(self) -> "TightenBody":
        if (self.rules is None) == (self.uncertainty_policy is None):
            raise ValueError("provide either new rules or uncertainty_policy, not both")
        if self.rules is not None and not self.rules:
            raise ValueError("rules must contain at least one new restriction")
        if self.uncertainty_policy is not None and self.uncertainty_policy != "decline":
            raise ValueError("uncertainty_policy can only be tightened to decline")
        return self


def _mandate_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise HTTPException(status_code=400, detail="mandate_id has invalid characters")
    return value


def _confirmation(store: DraftStore, mandate_id: str, customer: str) -> tuple[dict, dict]:
    if not customer:
        raise HTTPException(status_code=401, detail="customer login is required")
    confirmations = owned_confirmations(store, customer)
    if mandate_id not in confirmations:
        raise HTTPException(status_code=404, detail="mandate was not found for this customer")
    record = confirmations[mandate_id]
    draft = store.get(record["draft_id"])
    if draft["version"] != record["version"] or draft["hash"] != record["hash"]:
        raise RuntimeError(f"confirmed draft for mandate {mandate_id} has changed")
    return record, draft


class MandateEdits:
    """Keep customer-authored rule labels beside the simulator's stripped rules."""

    def __init__(self, store: DraftStore):
        self.root = store.root.parent / "mandate_edits"
        self.root.mkdir(parents=True, exist_ok=True)

    def read(self, mandate_id: str) -> dict:
        path = self.root / f"{mandate_id}.json"
        if not path.exists():
            return {"rules": [], "revision": 0, "uncertainty_policy": None}
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or not isinstance(data.get("revision"), int) or data["revision"] < 1:
            raise RuntimeError(f"invalid saved mandate edits for {mandate_id}")
        if not isinstance(data.get("rules"), list) or not all(isinstance(rule, dict) for rule in data["rules"]):
            raise RuntimeError(f"invalid saved rule edits for {mandate_id}")
        data["rules"] = [Rule.model_validate(rule).model_dump(mode="json") for rule in data["rules"]]
        if data.get("uncertainty_policy") not in (None, "decline"):
            raise RuntimeError(f"invalid saved uncertainty policy for {mandate_id}")
        return data

    @contextmanager
    def locked(self, mandate_id: str):
        with records.mandate_lock(mandate_id):
            yield

    def write(self, mandate_id: str, data: dict) -> None:
        path = self.root / f"{mandate_id}.json"
        temporary = self.root / f".{mandate_id}.{uuid4().hex}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(data, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def _simulator_call(action: Callable, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except ApiTimeout as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except ApiError as exc:
        status = exc.status if 400 <= exc.status < 500 else 502
        raise HTTPException(status_code=status, detail=f"Simulator {exc.method} {exc.path} failed: {exc.body}") from exc


def _remote(mandate_id: str, record: dict, draft: dict, *, deadline_at: datetime | None = None) -> dict:
    remote = _simulator_call(mandates.get, mandate_id, deadline_at=deadline_at)
    if not isinstance(remote, dict) or remote.get("mandate_id") != mandate_id:
        raise RuntimeError(f"simulator returned the wrong mandate for {mandate_id}")
    if remote.get("draft_id") != record["simulator_draft_id"] or remote.get("instruction") != draft["instruction"]:
        raise RuntimeError(f"simulator mandate {mandate_id} does not match the confirmed draft")
    return remote


def _effective(remote: dict, draft: dict, edits: dict, record: dict) -> dict:
    global_rules = record.get("global_rules", [])
    if not isinstance(global_rules, list):
        raise RuntimeError("confirmation record has invalid global_rules")
    expected_hash = record.get("global_hash", rules_hash(global_rules))
    if expected_hash != rules_hash(global_rules):
        raise RuntimeError("confirmation record global policy hash mismatch")
    rules = [Rule.model_validate(rule) for rule in [*global_rules, *draft["rules"], *edits["rules"]]]
    expected = [rule.simulator_rule() for rule in rules]
    actual = remote.get("hard_rules")
    if not isinstance(actual, list) or not all(isinstance(rule, dict) for rule in actual):
        raise RuntimeError("simulator mandate has no hard_rules list")
    actual = [{key: value for key, value in rule.items() if value is not None} for rule in actual]
    if actual != expected:
        raise RuntimeError("simulator rules differ from the confirmed draft and customer edits")
    policy = edits["uncertainty_policy"] or draft["uncertainty_policy"]
    if remote.get("uncertainty_policy") != policy:
        raise RuntimeError("simulator uncertainty policy differs from customer edits")
    return {"rules": [rule.model_dump(mode="json") for rule in rules], "uncertainty_policy": policy}


def _mandate(mandate_id: str, record: dict, remote: dict, edits: dict) -> dict:
    return Mandate.model_validate({
        "mandate_id": mandate_id,
        "draft_id": record["draft_id"],
        "version": record["version"] + edits["revision"],
        "hash": record["hash"],
        "status": remote["status"],
        "confirmed_at": record["confirmed_at"],
    }).model_dump(mode="json")


def mandate_router(
    store: DraftStore,
    authenticated_customer: Callable[..., str],
    load_state: Callable[..., MandateState] | None = None,
    *, step_up_book: StepUpBook | None = None,
) -> APIRouter:
    """Mount beside the policy router, with the shell's session dependency."""
    router = APIRouter()
    edits_store = MandateEdits(store)
    coordinator = Coordinator(store, step_up_book if step_up_book is not None else StepUpBook())

    @contextmanager
    def mutation(mandate_id: str, deadline_at: datetime):
        try:
            with coordinator.locked(mandate_id, deadline_at=deadline_at):
                yield
        except UnresolvedMutation as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc

    @router.get("/mandates")
    def list_mandates(
        status: str = Query(default="all"), customer: str = Depends(authenticated_customer)
    ) -> list[dict]:
        if not customer:
            raise HTTPException(status_code=401, detail="customer login is required")
        if status not in {"active", "superseded", "revoked", "expired", "all"}:
            raise HTTPException(status_code=422, detail="status must be active, superseded, revoked, expired or all")
        if load_state is None:
            raise HTTPException(status_code=503, detail="mandate state reader is not available")
        deadline_at = datetime.now(UTC) + timedelta(seconds=30)
        stop_at = time.monotonic() + 30
        with records.customer_lock(customer, stop_at=stop_at):
            confirmations = owned_confirmations(store, customer)
            mandate_ids = sorted(confirmations)
            with records.mandate_locks(mandate_ids, deadline_at=deadline_at, stop_at=stop_at):
                if owned_confirmations(store, customer) != confirmations:
                    raise RuntimeError("owned mandate set changed while locking the list")
                items = []
                for mandate_id, record in confirmations.items():
                    draft = store.get(record["draft_id"])
                    if draft["version"] != record["version"] or draft["hash"] != record["hash"]:
                        raise RuntimeError(f"confirmed draft for mandate {mandate_id} has changed")
                    remote = _remote(mandate_id, record, draft, deadline_at=deadline_at)
                    edits = edits_store.read(mandate_id)
                    _effective(remote, draft, edits, record)
                    mandate = _mandate(mandate_id, record, remote, edits)
                    if status != "all" and mandate["status"] != status:
                        continue
                    state_value = MandateState.model_validate(load_state(mandate_id, customer_mandates=mandate_ids))
                    if state_value.mandate_id != mandate_id:
                        raise RuntimeError(f"state reader returned a different mandate for {mandate_id}")
                    items.append({
                        **mandate,
                        "instruction": draft["instruction"],
                        "approvals_count": len(state_value.approvals),
                        "pending_step_ups": len(state_value.pending_step_ups),
                        "global_policy_version": record.get("global_version", 0),
                        "global_policy_hash": record.get("global_hash", rules_hash([])),
                    })
                return sorted(items, key=lambda item: (item["confirmed_at"], item["mandate_id"]), reverse=True)

    @router.get("/mandates/{mandate_id}")
    def get_mandate(mandate_id: str, customer: str = Depends(authenticated_customer)) -> dict:
        mandate_id = _mandate_id(mandate_id)
        if load_state is None:
            raise HTTPException(status_code=503, detail="mandate state reader is not available")
        deadline_at = datetime.now(UTC) + timedelta(seconds=30)
        stop_at = time.monotonic() + 30
        with records.customer_lock(customer, stop_at=stop_at):
            record, draft = _confirmation(store, mandate_id, customer)
            confirmations = owned_confirmations(store, customer)
            mandate_ids = sorted(confirmations)
            with records.mandate_locks(mandate_ids, deadline_at=deadline_at, stop_at=stop_at):
                if owned_confirmations(store, customer) != confirmations:
                    raise RuntimeError("owned mandate set changed while locking the detail")
                remote = _remote(mandate_id, record, draft, deadline_at=deadline_at)
                edits = edits_store.read(mandate_id)
                policy = _effective(remote, draft, edits, record)
                state = MandateState.model_validate(load_state(mandate_id, customer_mandates=mandate_ids)).model_dump(mode="json")
                if state["mandate_id"] != mandate_id:
                    raise RuntimeError(f"state reader returned a different mandate for {mandate_id}")
                return {"mandate": _mandate(mandate_id, record, remote, edits), "draft": PolicyDraft.model_validate(draft).model_dump(mode="json"), "effective_policy": policy, "state": state, "global_policy_version": record.get("global_version", 0), "global_policy_hash": record.get("global_hash", rules_hash([]))}

    @router.post("/mandates/{mandate_id}/tighten")
    def tighten_mandate(mandate_id: str, body: TightenBody, customer: str = Depends(authenticated_customer)) -> dict:
        mandate_id = _mandate_id(mandate_id)
        record, draft = _confirmation(store, mandate_id, customer)
        deadline_at = datetime.now(UTC) + timedelta(seconds=30)
        with mutation(mandate_id, deadline_at):
            edits = edits_store.read(mandate_id)
            remote = _remote(mandate_id, record, draft, deadline_at=deadline_at)
            effective = _effective(remote, draft, edits, record)
            if remote["status"] != "active":
                raise HTTPException(status_code=409, detail="only an active mandate can be tightened")
            updated = dict(edits)
            if body.rules is not None:
                rules = [Rule.model_validate(rule) for rule in [*effective["rules"], *body.rules]]
                patch = {"hard_rules": [rule.simulator_rule() for rule in rules]}
                updated["rules"] = [*edits["rules"], *(rule.model_dump(mode="json") for rule in body.rules)]
            else:
                if remote["uncertainty_policy"] == "decline":
                    raise HTTPException(status_code=409, detail="mandate already declines uncertain purchases")
                patch = {"uncertainty_policy": "decline"}
                updated["uncertainty_policy"] = "decline"
            updated["revision"] += 1
            intent = coordinator.journal.prepare(
                mandate_id, "tighten", method="PATCH", path=f"/v1/mandates/{mandate_id}",
                body=patch, deadline_at=deadline_at,
                context={"remote_before": remote, "draft": draft, "confirmation": record,
                         "edits_before": edits, "edits_after": updated},
            )
            accepted = _simulator_call(coordinator.journal.dispatch, intent)
            coordinator.record(accepted)
            return _mandate(mandate_id, record, accepted.accepted, updated)

    @router.post("/mandates/{mandate_id}/revoke")
    def revoke_mandate(mandate_id: str, customer: str = Depends(authenticated_customer)) -> dict:
        mandate_id = _mandate_id(mandate_id)
        record, draft = _confirmation(store, mandate_id, customer)
        deadline_at = datetime.now(UTC) + timedelta(seconds=30)
        with mutation(mandate_id, deadline_at):
            edits = edits_store.read(mandate_id)
            remote = _remote(mandate_id, record, draft, deadline_at=deadline_at)
            _effective(remote, draft, edits, record)
            if remote["status"] != "active":
                raise HTTPException(status_code=409, detail="only an active mandate can be revoked")
            intent = coordinator.journal.prepare(
                mandate_id, "revoke", method="DELETE", path=f"/v1/mandates/{mandate_id}",
                body=None, deadline_at=deadline_at,
                context={"remote_before": remote, "draft": draft, "confirmation": record},
            )
            accepted = _simulator_call(coordinator.journal.dispatch, intent)
            coordinator.record(accepted)
            return _mandate(mandate_id, record, accepted.accepted, edits)

    return router
