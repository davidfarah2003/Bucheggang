"""Scenario run loop and deadline guard (plan 05 task 4).

The loop polls GET /v1/decision-requests/next, validates the envelope and the
Event strictly, skips a live authorization ID already in MandateState.handled,
calls the given evaluate callable under a deadline guard, submits the decision,
and records the accepted result in the in-memory MandateState.

The deadline guard: if evaluate has not returned GUARD_MARGIN_S before
deadline_at, the loop submits step_up with reason engine_timeout and logs it.
That is the plan's specified outcome for a slow engine, never an approval.
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

from leash.contracts import Approval, Decision, Event, MandateState

from . import api

POLL_WAIT_S = 25
GUARD_MARGIN_S = 1.0
RUNNER_VERSION = "runner-0.1"

Evaluate = Callable[[Event, MandateState], Decision]

log = logging.getLogger("leash.runner")


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


def _engine_timeout_decision(event: Event, state: MandateState, started: float) -> Decision:
    return Decision(
        authorization_id=event.authorization.authorization_id,
        decision="step_up",
        reason_codes=["engine_timeout"],
        customer_message="We could not finish checking this purchase in time. Please confirm it yourself.",
        evidence=[],
        explanation="The decision engine did not return before the deadline guard; the purchase waits for the customer.",
        engine_version=RUNNER_VERSION,
        mandate_version=0,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        decided_at=_now(),
    )


def decide_with_guard(evaluate: Evaluate, event: Event, state: MandateState, pool: ThreadPoolExecutor) -> tuple[Decision, bool]:
    """Run evaluate; return (decision, guard_fired). Errors from evaluate propagate."""
    started = time.monotonic()
    budget = (event.deadline_at - _now()).total_seconds() - GUARD_MARGIN_S
    if budget <= 0:
        return _engine_timeout_decision(event, state, started), True
    future = pool.submit(evaluate, event, state)
    try:
        decision = future.result(timeout=budget)
    except FutureTimeout:
        return _engine_timeout_decision(event, state, started), True
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


def record(state: MandateState, event: Event, decision: Decision) -> None:
    """Record an accepted decision once. Only a final approve counts as spend."""
    auth = event.authorization
    state.handled[auth.authorization_id] = decision
    if decision.decision == "approve":
        state.approvals.append(
            Approval(authorization_id=auth.authorization_id, amount_chf=auth.billing_amount_chf, timestamp=auth.timestamp)
        )
    elif decision.decision == "step_up":
        state.pending_step_ups.append(auth.authorization_id)
    else:
        state.declined.append(auth.authorization_id)


def handle(envelope: Envelope, evaluate: Evaluate, state: MandateState, pool: ThreadPoolExecutor) -> Decision | None:
    """Handle one delivered request. Returns the submitted decision, or None for a redelivery."""
    received = _now()
    event = Event.model_validate(envelope.data)
    auth_id = event.authorization.authorization_id
    if envelope.authorization_id != auth_id:
        raise RunLoopError(f"envelope authorization_id {envelope.authorization_id} != event {auth_id}")
    if event.mandate.mandate_id != state.mandate_id:
        raise RunLoopError(f"event for mandate {event.mandate.mandate_id}, loop holds {state.mandate_id}")
    if auth_id in state.handled:
        _log({"authorization_id": auth_id, "run_id": envelope.run_id, "redelivery": True,
              "handled_as": state.handled[auth_id].decision})
        return None
    t0 = time.monotonic()
    decision, guard_fired = decide_with_guard(evaluate, event, state, pool)
    evaluate_ms = int((time.monotonic() - t0) * 1000)
    submitted_at = _now()
    accepted = submit(decision)
    record(state, event, decision)
    if guard_fired:
        log.error("deadline guard fired for %s: submitted step_up engine_timeout", auth_id)
    _log({
        "authorization_id": auth_id,
        "source_authorization_id": event.authorization.source_authorization_id,
        "run_id": envelope.run_id,
        "received_at": received.isoformat(),
        "evaluate_ms": evaluate_ms,
        "submitted_at": submitted_at.isoformat(),
        "ms_to_deadline_at_submit": int((event.deadline_at - submitted_at).total_seconds() * 1000),
        "decision": decision.decision,
        "reason_codes": list(decision.reason_codes),
        "guard_fired": guard_fired,
        "accepted": accepted,
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


def run_loop(run_id: str, evaluate: Evaluate, state: MandateState) -> MandateState:
    """Poll and decide until the run reports no remaining work."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        while True:
            envelope = poll()
            if envelope is None:
                progress = run_progress(run_id)
                _log({"run_id": run_id, "poll": 204, "status": progress["status"],
                      **{key: progress.get(key) for key in RUN_COUNTERS}})
                if _run_finished(progress):
                    return state
                continue
            if envelope.run_id != run_id:
                raise RunLoopError(f"received a request for run {envelope.run_id}, loop drives {run_id}")
            handle(envelope, evaluate, state, pool)


def configure_logging() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
