"""Step-up handling (plan 05 task 5).

A step_up the simulator accepted is held here as a pending StepUp until the
customer answers through the app or its expires_at passes.

- The customer's answer arrives on POST /step-ups/{authorization_id}/answer.
  The runner sends it to POST /v1/authorizations/{id}/resolve unchanged and
  records the result.
- A sweeper thread resolves every step-up whose expires_at has passed with
  decline and step_up_timeout. The runner never invents an approve.

expires_at = the time the step_up was accepted + bootstrap
limits.step_up_timeout_seconds - EXPIRY_MARGIN_S. The margin makes the runner's
timeout decline reach the simulator before the platform's own window closes.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from leash.contracts import Decision, Event, MandateState, StepUp, StepUpAnswer

from . import api

EXPIRY_MARGIN_S = 5.0
SWEEP_INTERVAL_S = 1.0

log = logging.getLogger("leash.runner.stepups")


class StepUpError(RuntimeError):
    """A step-up could not be registered or resolved."""


def human_window_s() -> float:
    """limits.step_up_timeout_seconds from GET /v1/bootstrap."""
    limits = api.bootstrap().get("limits")
    if not isinstance(limits, dict) or not isinstance(limits.get("step_up_timeout_seconds"), (int, float)):
        raise StepUpError(f"bootstrap has no limits.step_up_timeout_seconds: {limits}")
    return float(limits["step_up_timeout_seconds"])


def _now() -> datetime:
    return datetime.now(UTC)


def resolve(authorization_id: str, decision: str, customer_message: str) -> Any:
    """POST /v1/authorizations/{id}/resolve. Raises ApiError on non-2xx.

    The simulator's resolve body accepts decision, customer_message and evidence
    only (reason_codes is refused with 422 extra_forbidden), so reason codes such
    as step_up_timeout live in our recorded Decision.
    """
    body = {"decision": decision, "customer_message": customer_message, "evidence": []}
    return api.call("POST", f"/v1/authorizations/{authorization_id}/resolve", json=body)


class StepUpBook:
    """Pending step-ups and the MandateState they belong to, behind one lock.

    The run loop and the HTTP routes share one book. Every state change goes
    through `lock`.
    """

    def __init__(self, state: MandateState, window_s: float):
        self.state = state
        self.window_s = window_s
        self.lock = threading.RLock()
        self._pending: dict[str, StepUp] = {}
        self._stop = threading.Event()
        self._sweeper: threading.Thread | None = None
        self.failure: BaseException | None = None

    def add(self, event: Event, decision: Decision, accepted_at: datetime) -> StepUp:
        if decision.decision != "step_up":
            raise StepUpError(f"{decision.authorization_id} is {decision.decision}, not step_up")
        step_up = StepUp(
            authorization_id=decision.authorization_id,
            decision=decision,
            event=event,
            expires_at=accepted_at + timedelta(seconds=self.window_s - EXPIRY_MARGIN_S),
        )
        with self.lock:
            if step_up.authorization_id in self._pending:
                raise StepUpError(f"step-up {step_up.authorization_id} is already pending")
            self._pending[step_up.authorization_id] = step_up
        return step_up

    def pending(self) -> list[StepUp]:
        with self.lock:
            return sorted(self._pending.values(), key=lambda s: s.expires_at)

    def has_pending(self) -> bool:
        with self.lock:
            return bool(self._pending)

    def _finish(self, step_up: StepUp, outcome: str, reason_codes: list[str], message: str, explanation: str) -> Any:
        """Resolve on the simulator, then record. Caller holds the lock."""
        auth_id = step_up.authorization_id
        accepted = resolve(auth_id, outcome, message)
        final = Decision(
            authorization_id=auth_id,
            decision=outcome,
            reason_codes=reason_codes,
            customer_message=message,
            evidence=step_up.decision.evidence,
            explanation=explanation,
            engine_version=step_up.decision.engine_version,
            mandate_version=step_up.decision.mandate_version,
            elapsed_ms=step_up.decision.elapsed_ms,
            decided_at=_now(),
        )
        from .loop import record_resolution  # loop imports this module

        record_resolution(self.state, step_up.event, final)
        del self._pending[auth_id]
        log.info("resolved %s %s %s accepted=%s", auth_id, outcome, reason_codes, accepted)
        return accepted

    def answer(self, answer: StepUpAnswer) -> Any:
        """Send the customer's answer to /resolve and record it."""
        with self.lock:
            step_up = self._pending.get(answer.authorization_id)
            if step_up is None:
                raise KeyError(answer.authorization_id)
            if _now() >= step_up.expires_at:
                raise StepUpError(f"step-up {answer.authorization_id} expired at {step_up.expires_at.isoformat()}")
            code = "customer_confirmation" if answer.decision == "approve" else "customer_declined"
            return self._finish(
                step_up,
                answer.decision,
                [code],
                answer.customer_message,
                f"The customer answered {answer.decision} at {answer.answered_at.isoformat()}.",
            )

    def sweep(self) -> list[str]:
        """Resolve every expired step-up with decline step_up_timeout."""
        done = []
        with self.lock:
            now = _now()
            for step_up in [s for s in self._pending.values() if now >= s.expires_at]:
                self._finish(
                    step_up,
                    "decline",
                    ["step_up_timeout"],
                    "You did not answer in time, so this purchase was declined.",
                    f"No customer answer before {step_up.expires_at.isoformat()}; declined on timeout.",
                )
                done.append(step_up.authorization_id)
        return done

    def _sweep_forever(self) -> None:
        try:
            while not self._stop.wait(SWEEP_INTERVAL_S):
                self.sweep()
        except BaseException as exc:
            # Kept for the run loop, which re-raises it; the thread then ends.
            self.failure = exc
            log.error("step-up sweeper stopped: %r", exc)
            raise

    def raise_failure(self) -> None:
        if self.failure is not None:
            raise StepUpError("step-up sweeper failed; pending step-ups are no longer timed out") from self.failure

    def start(self) -> None:
        self._sweeper = threading.Thread(target=self._sweep_forever, name="step-up-sweeper", daemon=True)
        self._sweeper.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sweeper is not None:
            self._sweeper.join()

    def sweeper_alive(self) -> bool:
        return self._sweeper is not None and self._sweeper.is_alive()
