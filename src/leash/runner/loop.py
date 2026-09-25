"""Scenario run loop and deadline guard (plan 05 task 4).

The loop polls GET /v1/decision-requests/next, validates the envelope and the
Event strictly, skips a live authorization ID already in MandateState.handled,
runs leash.extract.extract_event (deterministic, no model) under its budget, calls
evaluate(event, policy, state, facts) under a deadline guard, submits the
decision through a durable intent, and records the accepted result once. Current
permissions and customer-owned spending are checked under the complete sorted
mandate-lock set. Engine state remains the only writer of financial state.

Reconcile. Startup and final coordination reconcile open intents by authoritative
reads before new dispatch. Accepted authorizations are not submitted again.

Budgets. Extract gets min(EXTRACT_CAP_S, deadline_at - now - EXTRACT_RESERVE_S).
Evaluate must return GUARD_MARGIN_S before deadline_at. Either budget failure
raises without a substitute decision. Submission is bounded by deadline_at,
including its response body. No failed operation is retried.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict

from leash.contracts import Decision, Event, MandateState, PolicyDraft, PurchaseFacts
from leash.engine import state as engine_state
from leash.extract import extract_event
from leash.policy.store import DraftStore

from . import api, records, policy_context
from .coordinator import Coordinator
from .stepups import StepUpBook

POLL_WAIT_S = 25
GUARD_MARGIN_S = 1.0
EXTRACT_CAP_S = 1.5
EXTRACT_RESERVE_S = 2.0
# The platform redelivers a pending step-up on every poll and holds the next
# request back until it resolves. The loop waits this long before polling again.
PENDING_STEP_UP_PAUSE_S = 1.0

Evaluate = Callable[[Event, PolicyDraft, MandateState, list[PurchaseFacts] | None], Decision]

log = logging.getLogger("leash.runner")
# Pending step-ups already logged as skipped in this process; the platform
# redelivers them every poll, so each is logged once.
_logged_pending: set[str] = set()


class RunLoopError(RuntimeError):
    """The run loop hit something it cannot continue past."""


class Envelope(BaseModel):
    """The poll response wrapper. Unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid", strict=True)

    run_id: str
    event_id: int
    type: Literal["authorization.request"]
    authorization_id: str
    status: str
    occurred_at: str
    data: dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


def _log(record: dict[str, Any]) -> None:
    log.info(json.dumps(record, default=str))


def start_run(scenario_id: str, mandate_id: str) -> dict:
    """POST /v1/scenario-runs; returns the run record (contains run_id)."""
    run = api.call("POST", "/v1/scenario-runs", json={"scenario_id": scenario_id, "mandate_id": mandate_id})
    if not isinstance(run, dict) or not run.get("run_id"):
        raise RunLoopError(f"POST /v1/scenario-runs returned no run_id: {run}")
    return run


def run_progress(run_id: str) -> dict:
    return api.call("GET", f"/v1/scenario-runs/{run_id}")


def poll() -> Envelope | None:
    """One long poll. None on 204."""
    response = api.request("GET", "/v1/decision-requests/next", params={"wait": POLL_WAIT_S})
    if response.status_code == 204:
        return None
    return Envelope.model_validate(response.json())


class ProcessingTimeout(RunLoopError):
    """Extraction or evaluation exceeded its budget; no decision was submitted."""


def _processing_budget(event: Event, reserve_s: float) -> float:
    if event.deadline_at.utcoffset() is None:
        raise RunLoopError("event deadline_at must have a timezone")
    return (event.deadline_at - _now()).total_seconds() - reserve_s


def _timeout(event: Event, operation: str) -> ProcessingTimeout:
    message = f"{event.authorization.authorization_id}: {operation} budget expired; no decision submitted"
    log.error(message)
    return ProcessingTimeout(message)


def requested_item(policy: PolicyDraft) -> dict[str, str] | None:
    """The requested item for extract, from the confirmed draft's equality rules on facts.product_type and facts.size."""
    requested: dict[str, str] = {}
    for rule in policy.rules:
        if rule.operator == "=" and rule.field in ("facts.product_type", "facts.size"):
            requested[rule.field.removeprefix("facts.")] = str(rule.value)
    return requested or None


def extract_with_budget(event: Event, policy: PolicyDraft, pool: ThreadPoolExecutor) -> list[PurchaseFacts]:
    """Return validated facts or raise. A timeout never becomes missing facts."""
    budget = min(EXTRACT_CAP_S, _processing_budget(event, EXTRACT_RESERVE_S))
    if budget <= 0:
        raise _timeout(event, "extraction")
    stop_at = time.monotonic() + budget
    future = pool.submit(extract_event, event.model_dump(mode="json"), requested=requested_item(policy))
    try:
        rows = future.result(timeout=max(0, stop_at - time.monotonic()))
    except FutureTimeout as exc:
        future.cancel()
        raise _timeout(event, "extraction") from exc
    facts = [PurchaseFacts.model_validate(row) for row in rows]
    if time.monotonic() >= stop_at:
        raise _timeout(event, "extraction")
    return facts


def decide_with_guard(
    evaluate: Evaluate,
    event: Event,
    policy: PolicyDraft,
    state: MandateState,
    facts: list[PurchaseFacts],
    pool: ThreadPoolExecutor,
) -> Decision:
    """Return the engine result before its guard or raise without a substitute."""
    budget = _processing_budget(event, GUARD_MARGIN_S)
    if budget <= 0:
        raise _timeout(event, "evaluation")
    stop_at = time.monotonic() + budget
    future = pool.submit(evaluate, event, policy, state, facts)
    try:
        decision = future.result(timeout=max(0, stop_at - time.monotonic()))
    except FutureTimeout as exc:
        future.cancel()
        raise _timeout(event, "evaluation") from exc
    decision = Decision.model_validate(decision.model_dump(mode="python"))
    if time.monotonic() >= stop_at:
        raise _timeout(event, "evaluation")
    if decision.authorization_id != event.authorization.authorization_id:
        raise RunLoopError(
            f"evaluate returned a decision for {decision.authorization_id}, expected {event.authorization.authorization_id}"
        )
    return decision


def submit(decision: Decision, *, deadline_at: datetime) -> Any:
    """POST /v1/authorizations/{id}/decision with the live ID in URL and body."""
    body = {
        "authorization_id": decision.authorization_id,
        "decision": decision.decision,
        "reason_codes": list(decision.reason_codes),
        "customer_message": decision.customer_message,
        "evidence": [check.model_dump(mode="json") for check in decision.evidence],
        "engine_version": decision.engine_version,
    }
    return api.call("POST", f"/v1/authorizations/{decision.authorization_id}/decision", json=body, deadline_at=deadline_at)


def handle(
    envelope: Envelope,
    evaluate: Evaluate,
    policy: PolicyDraft,
    mandate_id: str,
    book: StepUpBook,
    window_s: float,
    pool: ThreadPoolExecutor,
    store: DraftStore,
) -> Decision | None:
    """Recheck current permissions and owned spend before a journaled submission."""
    received = _now()
    event = Event.model_validate(envelope.data)
    auth_id = event.authorization.authorization_id
    if envelope.authorization_id != auth_id:
        raise RunLoopError(f"envelope authorization_id {envelope.authorization_id} != event {auth_id}")
    if event.mandate.mandate_id != mandate_id or event.authorization.mandate_id != mandate_id:
        raise RunLoopError(f"event does not belong to mandate {mandate_id}")
    if event.mandate.instruction != policy.instruction:
        raise RunLoopError(f"event mandate instruction differs from the confirmed draft {policy.draft_id}")
    coordinator = Coordinator(store, book)
    dispatch_deadline = event.deadline_at - timedelta(seconds=0.25)
    if dispatch_deadline <= _now():
        raise RunLoopError(
            f"{event.authorization.authorization_id}: deadline {event.deadline_at.isoformat()} already passed before dispatch"
        )
    with coordinator.locked(mandate_id, deadline_at=dispatch_deadline) as mandate_ids:
        record, _ = policy_context.confirmation(store, mandate_id)
        if record["hash"] != policy.hash or record["version"] != policy.version:
            raise RunLoopError(f"{mandate_id}: supplied draft differs from the saved confirmation")
        state = engine_state.load(mandate_id, customer_mandates=mandate_ids)
        seen = state.handled.get(auth_id)
        if seen is None:
            effective_event, effective_policy = policy_context.refresh(
                store, event, deadline_at=dispatch_deadline - timedelta(seconds=2),
            )
            effective_event.deadline_at = dispatch_deadline
            before = state.model_copy(deep=True, update={"customer_approvals": []})
            t0 = time.monotonic()
            facts = extract_with_budget(effective_event, effective_policy, pool)
            extract_ms = int((time.monotonic() - t0) * 1000)
            t1 = time.monotonic()
            decision = decide_with_guard(evaluate, effective_event, effective_policy, state, facts, pool)
            evaluate_ms = int((time.monotonic() - t1) * 1000)
            submitted_at = _now()
            result = coordinator.authorization(
                event=event, decision=decision, state_before=before, evaluated_state=state,
                policy=effective_policy.model_dump(mode="json"), run_id=envelope.run_id,
                deadline_at=dispatch_deadline,
            )
            recorded_at = _now()
            _log({
                "authorization_id": auth_id, "source_authorization_id": event.authorization.source_authorization_id,
                "run_id": envelope.run_id, "received_at": received.isoformat(),
                "extract_ms": extract_ms, "evaluate_ms": evaluate_ms,
                "submitted_at": submitted_at.isoformat(), "recorded_at": recorded_at.isoformat(),
                "ms_to_deadline_at_submit": int((event.deadline_at - submitted_at).total_seconds() * 1000),
                "ms_to_deadline_at_record": int((event.deadline_at - recorded_at).total_seconds() * 1000),
                "decision": result.decision, "reason_codes": list(result.reason_codes),
                "mandate_version": effective_policy.version, "policy_hash": effective_policy.hash,
                "customer_approvals": len(state.customer_approvals),
            })
            return result
    if seen.decision == "step_up":
        if auth_id not in _logged_pending:
            _logged_pending.add(auth_id)
            _log({"authorization_id": auth_id, "run_id": envelope.run_id, "skipped_handled": True, "handled_as": "step_up"})
        time.sleep(PENDING_STEP_UP_PAUSE_S)
    else:
        _log({"authorization_id": auth_id, "run_id": envelope.run_id, "skipped_handled": True, "handled_as": seen.decision})
    return None


RUN_COUNTERS = ("generated_event_count", "delivered_event_count", "finalized_event_count",
                "pending_event_count", "queued_event_count", "platform_rejected_count")


def _run_finished(progress: dict) -> bool:
    """The run is finished when the platform no longer reports it as running."""
    status = progress.get("status")
    if not isinstance(status, str):
        raise RunLoopError(f"run record has no status: {progress}")
    return status != "running"


def run_loop(
    run_id: str, evaluate: Evaluate, policy: PolicyDraft, mandate_id: str, book: StepUpBook, window_s: float, store: DraftStore
) -> MandateState:
    """Poll and decide until the run is finished and no step-up of this mandate is pending.

    The book's sweeper must be running; a sweeper failure stops the loop with that error.
    Returns the saved state.
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        while True:
            book.raise_failure()
            envelope = poll()
            if envelope is None:
                progress = run_progress(run_id)
                pending = [s.authorization_id for s in book.pending(mandate_id)]
                _log({"run_id": run_id, "poll": 204, "status": progress["status"], "pending_step_ups": pending,
                      **{key: progress.get(key) for key in RUN_COUNTERS}})
                if _run_finished(progress) and not pending:
                    with Coordinator(store, book).locked(mandate_id, deadline_at=_now() + timedelta(seconds=30)) as ids:
                        return engine_state.load(mandate_id, customer_mandates=ids)
                continue
            if envelope.run_id != run_id:
                raise RunLoopError(f"received a request for run {envelope.run_id}, loop drives {run_id}")
            handle(envelope, evaluate, policy, mandate_id, book, window_s, pool, store)


def configure_logging() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
