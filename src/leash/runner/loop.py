"""Scenario run loop and deadline guard (plan 05 task 4).

The loop polls GET /v1/decision-requests/next, validates the envelope and the
Event strictly, skips a live authorization ID already in MandateState.handled,
runs leash.extract.extract_event (deterministic, no model) under its budget, calls
evaluate(event, policy, state, facts) under a deadline guard, submits the
decision, and records the accepted result with leash.runner.records.record_accepted,
which calls leash.engine.state.record (the one writer of data/state/<mandate_id>.json)
and writes data/decisions/<mandate_id>/<authorization_id>.json.

Reconcile. Every request reads the saved state with leash.engine.state.load, so a
restarted worker skips any live authorization ID already in MandateState.handled.

Budgets. Extract gets min(EXTRACT_CAP_S, deadline_at - now - EXTRACT_RESERVE_S).
If extract does not return inside it, the loop declines with engine_timeout and
never calls evaluate with invented facts. An exception raised by extract
propagates. Evaluate must return GUARD_MARGIN_S before deadline_at; if it does
not, the loop submits step_up with engine_timeout and logs it.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict

from leash.contracts import Decision, Event, MandateState, PolicyDraft, PurchaseFacts
from leash.engine import state as engine_state
from leash.extract import extract_event

from . import api, records
from .stepups import StepUpBook, expires_at

POLL_WAIT_S = 25
GUARD_MARGIN_S = 1.0
EXTRACT_CAP_S = 1.5
EXTRACT_RESERVE_S = 2.0
RUNNER_VERSION = "runner-0.1"
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


def _engine_timeout_decision(event: Event, policy: PolicyDraft, started: float) -> Decision:
    """Evaluate missed the guard: the purchase waits for the customer."""
    return Decision(
        authorization_id=event.authorization.authorization_id,
        decision="step_up",
        reason_codes=["engine_timeout"],
        customer_message="We could not finish checking this purchase in time. Please confirm it yourself.",
        evidence=[],
        explanation="The decision engine did not return before the deadline guard; the purchase waits for the customer.",
        engine_version=RUNNER_VERSION,
        mandate_version=policy.version,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        decided_at=_now(),
    )


def _extract_timeout_decision(event: Event, policy: PolicyDraft, started: float) -> Decision:
    """Extract missed its budget: decline, never evaluate on invented facts."""
    return Decision(
        authorization_id=event.authorization.authorization_id,
        decision="decline",
        reason_codes=["engine_timeout"],
        customer_message="We could not read this purchase's details in time, so it was declined.",
        evidence=[],
        explanation="Fact extraction did not finish inside its budget; the loop declines instead of deciding without facts.",
        engine_version=RUNNER_VERSION,
        mandate_version=policy.version,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        decided_at=_now(),
    )


def requested_item(policy: PolicyDraft) -> dict[str, str] | None:
    """The requested item for extract, from the confirmed draft's equality rules on facts.product_type and facts.size."""
    requested: dict[str, str] = {}
    for rule in policy.rules:
        if rule.operator == "=" and rule.field in ("facts.product_type", "facts.size"):
            requested[rule.field.removeprefix("facts.")] = str(rule.value)
    return requested or None


def extract_with_budget(event: Event, policy: PolicyDraft, pool: ThreadPoolExecutor) -> list[PurchaseFacts] | None:
    """Run extract pass 1. None when it did not return inside its budget; its errors propagate."""
    budget = min(EXTRACT_CAP_S, (event.deadline_at - _now()).total_seconds() - EXTRACT_RESERVE_S)
    if budget <= 0:
        return None
    future = pool.submit(extract_event, event.model_dump(mode="json"), requested=requested_item(policy))
    try:
        rows = future.result(timeout=budget)
    except FutureTimeout:
        return None
    return [PurchaseFacts.model_validate(row) for row in rows]


def decide_with_guard(
    evaluate: Evaluate,
    event: Event,
    policy: PolicyDraft,
    state: MandateState,
    facts: list[PurchaseFacts],
    pool: ThreadPoolExecutor,
) -> tuple[Decision, bool]:
    """Run evaluate; return (decision, guard_fired). Errors from evaluate propagate."""
    started = time.monotonic()
    budget = (event.deadline_at - _now()).total_seconds() - GUARD_MARGIN_S
    if budget <= 0:
        return _engine_timeout_decision(event, policy, started), True
    future = pool.submit(evaluate, event, policy, state, facts)
    try:
        decision = future.result(timeout=budget)
    except FutureTimeout:
        return _engine_timeout_decision(event, policy, started), True
    if decision.authorization_id != event.authorization.authorization_id:
        raise RunLoopError(
            f"evaluate returned a decision for {decision.authorization_id}, expected {event.authorization.authorization_id}"
        )
    return decision, False


def submit(decision: Decision) -> Any:
    """POST /v1/authorizations/{id}/decision with the live ID in URL and body."""
    body = {
        "authorization_id": decision.authorization_id,
        "decision": decision.decision,
        "reason_codes": list(decision.reason_codes),
        "customer_message": decision.customer_message,
        "evidence": [check.model_dump(mode="json") for check in decision.evidence],
        "engine_version": decision.engine_version,
    }
    return api.call("POST", f"/v1/authorizations/{decision.authorization_id}/decision", json=body)


def handle(
    envelope: Envelope,
    evaluate: Evaluate,
    policy: PolicyDraft,
    mandate_id: str,
    book: StepUpBook,
    window_s: float,
    pool: ThreadPoolExecutor,
) -> Decision | None:
    """Handle one delivered request. Returns the submitted decision, or None for a handled ID."""
    received = _now()
    event = Event.model_validate(envelope.data)
    auth_id = event.authorization.authorization_id
    if envelope.authorization_id != auth_id:
        raise RunLoopError(f"envelope authorization_id {envelope.authorization_id} != event {auth_id}")
    if event.mandate.mandate_id != mandate_id:
        raise RunLoopError(f"event for mandate {event.mandate.mandate_id}, loop holds {mandate_id}")
    if event.mandate.instruction != policy.instruction:
        raise RunLoopError(f"event mandate instruction differs from the confirmed draft {policy.draft_id}")
    with records.mandate_lock(mandate_id):
        state = engine_state.load(mandate_id)
    seen = state.handled.get(auth_id)
    if seen is not None:
        if seen.decision == "step_up":
            if auth_id not in _logged_pending:
                _logged_pending.add(auth_id)
                _log({"authorization_id": auth_id, "run_id": envelope.run_id, "skipped_handled": True, "handled_as": "step_up"})
            time.sleep(PENDING_STEP_UP_PAUSE_S)
            return None
        _log({"authorization_id": auth_id, "run_id": envelope.run_id, "skipped_handled": True, "handled_as": seen.decision})
        return None
    t0 = time.monotonic()
    facts = extract_with_budget(event, policy, pool)
    extract_ms = int((time.monotonic() - t0) * 1000)
    t1 = time.monotonic()
    extract_timed_out = facts is None
    if extract_timed_out:
        decision, guard_fired = _extract_timeout_decision(event, policy, t0), False
        log.error("extract missed its budget for %s: declined engine_timeout", auth_id)
    else:
        decision, guard_fired = decide_with_guard(evaluate, event, policy, state, facts, pool)
    evaluate_ms = int((time.monotonic() - t1) * 1000)
    submitted_at = _now()
    accepted = submit(decision)
    accepted_at = _now()
    with records.mandate_lock(mandate_id):
        records.record_accepted(event, decision, accepted_at, accepted, resolution=False)
        step_up = (
            book.add(event, decision, expires_at(accepted_at, window_s)) if decision.decision == "step_up" else None
        )
    if guard_fired:
        log.error("deadline guard fired for %s: submitted step_up engine_timeout", auth_id)
    _log({
        "authorization_id": auth_id,
        "source_authorization_id": event.authorization.source_authorization_id,
        "run_id": envelope.run_id,
        "received_at": received.isoformat(),
        "extract_ms": extract_ms,
        "evaluate_ms": evaluate_ms,
        "submitted_at": submitted_at.isoformat(),
        "ms_to_deadline_at_submit": int((event.deadline_at - submitted_at).total_seconds() * 1000),
        "decision": decision.decision,
        "reason_codes": list(decision.reason_codes),
        "extract_timed_out": extract_timed_out,
        "guard_fired": guard_fired,
        "accepted": accepted,
        "step_up_expires_at": step_up.expires_at.isoformat() if step_up else None,
    })
    return decision


RUN_COUNTERS = ("generated_event_count", "delivered_event_count", "finalized_event_count",
                "pending_event_count", "queued_event_count", "platform_rejected_count")


def _run_finished(progress: dict) -> bool:
    """The run is finished when the platform no longer reports it as running."""
    status = progress.get("status")
    if not isinstance(status, str):
        raise RunLoopError(f"run record has no status: {progress}")
    return status != "running"


def run_loop(
    run_id: str, evaluate: Evaluate, policy: PolicyDraft, mandate_id: str, book: StepUpBook, window_s: float
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
                    return engine_state.load(mandate_id)
                continue
            if envelope.run_id != run_id:
                raise RunLoopError(f"received a request for run {envelope.run_id}, loop drives {run_id}")
            handle(envelope, evaluate, policy, mandate_id, book, window_s, pool)


def configure_logging() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
