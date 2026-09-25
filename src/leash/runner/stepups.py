"""Step-up handling (plan 05 tasks 5 and 6).

A step_up the simulator accepted is held as a file until the customer answers
through the app or its expires_at passes:

    data/stepups/<mandate_id>/<authorization_id>.json
    { step_up: StepUp, status: "pending" | "resolved", resolution: {...} | null }

The run loop and the API shell are two processes. Both build StepUpBook() and
read the same files, and every change happens under
leash.runner.records.mandate_lock with one atomic write (temp file, rename).

- The customer's answer arrives on POST /step-ups/{authorization_id}/answer
  (API process). The runner sends it to POST /v1/authorizations/{id}/resolve,
  records it through leash.engine.state.record, writes the decision file and
  marks the step-up file resolved.
- The run loop's sweeper thread does the same with decline and step_up_timeout
  for every pending step-up whose expires_at has passed. The runner never
  invents an approve.

expires_at = the time the step_up was accepted + bootstrap
limits.step_up_timeout_seconds - EXPIRY_MARGIN_S. The margin makes the runner's
timeout decline reach the simulator before the platform's own window closes.
A missing or malformed step-up file raises.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from leash.contracts import Decision, Event, StepUp, StepUpAnswer
from leash.contracts.event import Authorization

from . import api, records

EXPIRY_MARGIN_S = 5.0
SWEEP_INTERVAL_S = 1.0
STEPUPS_DIR = records.DATA_DIR / "stepups"

log = logging.getLogger("leash.runner.stepups")


class StepUpError(RuntimeError):
    """A step-up could not be registered or resolved."""


def human_window_s() -> float:
    """limits.step_up_timeout_seconds from GET /v1/bootstrap."""
    limits = api.bootstrap().get("limits")
    if not isinstance(limits, dict) or not isinstance(limits.get("step_up_timeout_seconds"), (int, float)):
        raise StepUpError(f"bootstrap has no limits.step_up_timeout_seconds: {limits}")
    window = limits["step_up_timeout_seconds"]
    _validate_window(window)
    return float(window)


def _validate_window(window_s: float) -> None:
    if isinstance(window_s, bool) or not math.isfinite(window_s) or window_s <= EXPIRY_MARGIN_S:
        raise StepUpError("human window must be finite and longer than the expiry margin")


def expires_at(accepted_at: datetime, window_s: float) -> datetime:
    _validate_window(window_s)
    if accepted_at.utcoffset() is None:
        raise StepUpError("step-up accepted_at must have a timezone")
    return accepted_at + timedelta(seconds=window_s - EXPIRY_MARGIN_S)


def _now() -> datetime:
    return datetime.now(UTC)


def resolve(authorization_id: str, decision: str, customer_message: str, *, deadline_at: datetime) -> Any:
    """POST /v1/authorizations/{id}/resolve. Raises ApiError on non-2xx.

    The simulator's resolve body accepts decision, customer_message and evidence
    only (reason_codes is refused with 422 extra_forbidden), so reason codes such
    as step_up_timeout live in our recorded Decision.
    """
    body = {"decision": decision, "customer_message": customer_message, "evidence": []}
    return api.call("POST", f"/v1/authorizations/{authorization_id}/resolve", json=body, deadline_at=deadline_at)


class StepUpBook:
    """File-backed pending step-ups. Any process can build one over the same root."""

    def __init__(self, root: Path = STEPUPS_DIR):
        self.root = Path(root)
        self._stop = threading.Event()
        self._sweeper: threading.Thread | None = None
        self.failure: BaseException | None = None

    # files

    def _path(self, mandate_id: str, authorization_id: str) -> Path:
        return self.root / records._safe(mandate_id, "mandate_id") / f"{records._safe(authorization_id, 'authorization_id')}.json"

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        record = json.loads(path.read_text())
        if record.get("status") not in ("pending", "resolved") or "step_up" not in record:
            raise StepUpError(f"{path} is not a step-up record")
        record["step_up"] = StepUp.model_validate(record["step_up"])
        return record

    def _find(self, authorization_id: str) -> Path:
        found = list(self.root.glob(f"*/{records._safe(authorization_id, 'authorization_id')}.json"))
        if not found:
            raise KeyError(authorization_id)
        if len(found) > 1:
            raise StepUpError(f"step-up {authorization_id} exists under more than one mandate: {found}")
        return found[0]

    def _records(self, mandate_id: str | None = None) -> list[dict[str, Any]]:
        pattern = f"{records._safe(mandate_id, 'mandate_id')}/*.json" if mandate_id else "*/*.json"
        return [self._read(p) for p in self.root.glob(pattern)]

    # reads

    def pending(self, mandate_id: str | None = None) -> list[StepUp]:
        return sorted(
            (r["step_up"] for r in self._records(mandate_id) if r["status"] == "pending"),
            key=lambda s: s.expires_at,
        )

    def get(self, authorization_id: str) -> StepUp:
        path = self._find(authorization_id)
        step_up = self._read(path)["step_up"]
        if (step_up.authorization_id != authorization_id
                or step_up.event.authorization.authorization_id != authorization_id
                or step_up.event.mandate.mandate_id != path.parent.name):
            raise StepUpError(f"step-up {authorization_id} identity differs from its saved path")
        return step_up

    def has_pending(self, mandate_id: str) -> bool:
        return bool(self.pending(mandate_id))

    # writes

    def add(self, event: Event, decision: Decision, expires: datetime) -> StepUp:
        """Write the pending record. The caller holds mandate_lock for the event's mandate."""
        if decision.decision != "step_up":
            raise StepUpError(f"{decision.authorization_id} is {decision.decision}, not step_up")
        step_up = StepUp(authorization_id=decision.authorization_id, decision=decision, event=event, expires_at=expires)
        path = self._path(event.mandate.mandate_id, step_up.authorization_id)
        if path.exists():
            raise StepUpError(f"step-up {step_up.authorization_id} is already recorded at {path}")
        records.write_atomic(path, {"step_up": step_up.model_dump(mode="json"), "status": "pending", "resolution": None})
        return step_up

    def _finish(
        self, path: Path, step_up: StepUp, outcome: str, reason_codes: list[str], message: str, explanation: str,
        *, deadline_at: datetime,
    ) -> Any:
        """Resolve within the human window, then record. Caller holds the mandate lock."""
        auth_id = step_up.authorization_id
        accepted = resolve(auth_id, outcome, message, deadline_at=deadline_at)
        accepted_at = _now()
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
            decided_at=accepted_at,
        )
        self._record_resolution(path, step_up, final, accepted_at, accepted)
        log.info("resolved %s %s %s accepted=%s", auth_id, outcome, reason_codes, accepted)
        return accepted

    @staticmethod
    def _record_resolution(path: Path, step_up: StepUp, final: Decision, accepted_at: datetime, accepted: Any) -> None:
        records.record_accepted(step_up.event, final, accepted_at, accepted, resolution=True)
        records.write_atomic(path, {
            "step_up": step_up.model_dump(mode="json"),
            "status": "resolved",
            "resolution": {"decision": final.model_dump(mode="json"), "accepted": accepted, "accepted_at": accepted_at.isoformat()},
        })

    def _reconcile_expired(self, path: Path, step_up: StepUp, run_id: str) -> None:
        """Record a verified platform expiry. Never infer an outcome from the 409 alone."""
        auth_id = step_up.authorization_id
        rows = api.call("GET", "/v1/authorizations", params={"run_id": run_id})
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise StepUpError("GET /v1/authorizations did not return a list of authorization records")
        found = [row for row in rows if row.get("authorization_id") == auth_id]
        if len(found) != 1:
            raise StepUpError(f"{auth_id}: expected one authoritative authorization, found {len(found)}")
        accepted = found[0]
        decision = accepted.get("decision")
        if (accepted.get("run_id") != run_id or accepted.get("status") != "declined"
                or accepted.get("decision_source") != "timeout"
                or accepted.get("reason_codes") != ["step_up_expired"]
                or not isinstance(decision, dict)
                or decision.get("authorization_id") != auth_id or decision.get("decision") != "decline"
                or decision.get("decision_source") != "timeout"
                or decision.get("reason_codes") != ["step_up_expired"]):
            raise StepUpError(f"{auth_id}: platform record is not a finalized step-up timeout decline")
        authorization = Authorization.model_validate(accepted.get("authorization"))
        if authorization != step_up.event.authorization:
            raise StepUpError(f"{auth_id}: platform authorization differs from the stored pending event")
        finalized = accepted.get("finalized_at")
        if not isinstance(finalized, str):
            raise StepUpError(f"{auth_id}: platform timeout has no finalized_at")
        accepted_at = datetime.fromisoformat(finalized.replace("Z", "+00:00"))
        if accepted_at.tzinfo is None or not step_up.expires_at <= accepted_at <= _now():
            raise StepUpError(f"{auth_id}: platform finalized_at is outside the expiry-to-now interval")
        final = Decision(
            authorization_id=auth_id, decision="decline", reason_codes=["step_up_timeout"],
            customer_message=decision.get("customer_message"), evidence=decision.get("evidence"),
            explanation="The simulator expired the unanswered step-up. Recorded its verified timeout decline without resubmitting.",
            engine_version="simulator-step-up-expiry", mandate_version=step_up.decision.mandate_version,
            elapsed_ms=0, decided_at=accepted_at,
        )
        self._record_resolution(path, step_up, final, accepted_at, accepted)
        log.info("reconciled %s declined decision_source=timeout reason=step_up_expired finalized_at=%s",
                 auth_id, finalized)

    def answer(self, answer: StepUpAnswer) -> Any:
        """Send the customer's answer to /resolve and record it. KeyError when unknown."""
        path = self._find(answer.authorization_id)
        mandate_id = path.parent.name
        with records.mandate_lock(mandate_id):
            record = self._read(path)
            step_up = record["step_up"]
            if record["status"] != "pending":
                raise StepUpError(f"step-up {answer.authorization_id} is already resolved")
            if _now() >= step_up.expires_at:
                raise StepUpError(f"step-up {answer.authorization_id} expired at {step_up.expires_at.isoformat()}")
            code = "customer_confirmation" if answer.decision == "approve" else "customer_declined"
            return self._finish(
                path,
                step_up,
                answer.decision,
                [code],
                answer.customer_message,
                f"The customer answered {answer.decision} at {answer.answered_at.isoformat()}.",
                deadline_at=step_up.expires_at,
            )

    def sweep(self, mandate_id: str, run_id: str) -> list[str]:
        """Resolve expired step-ups, or reconcile a timeout the platform already recorded."""
        done = []
        with records.mandate_lock(mandate_id):
            now = _now()
            for step_up in self.pending(mandate_id):
                if now < step_up.expires_at:
                    continue
                path = self._path(mandate_id, step_up.authorization_id)
                timeout_deadline = step_up.expires_at + timedelta(seconds=EXPIRY_MARGIN_S)
                if _now() >= timeout_deadline:
                    self._reconcile_expired(path, step_up, run_id)
                    done.append(step_up.authorization_id)
                    continue
                try:
                    self._finish(
                        path, step_up, "decline", ["step_up_timeout"],
                        "You did not answer in time, so this purchase was declined.",
                        f"No customer answer before {step_up.expires_at.isoformat()}; declined on timeout.",
                        deadline_at=timeout_deadline,
                    )
                except api.ApiError as exc:
                    error = exc.body.get("error") if isinstance(exc.body, dict) else None
                    if (exc.status != 409 or not isinstance(error, dict)
                            or error.get("code") != "authorization_not_pending"):
                        raise
                    self._reconcile_expired(path, step_up, run_id)
                done.append(step_up.authorization_id)
        return done

    # sweeper thread (run loop process only)

    def _sweep_forever(self, mandate_id: str, run_id: str) -> None:
        try:
            while not self._stop.wait(SWEEP_INTERVAL_S):
                self.sweep(mandate_id, run_id)
        except BaseException as exc:
            # Kept for the run loop, which re-raises it; the thread then ends.
            self.failure = exc
            log.error("step-up sweeper stopped: %r", exc)
            raise

    def raise_failure(self) -> None:
        if self.failure is not None:
            raise StepUpError("step-up sweeper failed; pending step-ups are no longer timed out") from self.failure

    def start(self, mandate_id: str, run_id: str) -> None:
        self._sweeper = threading.Thread(target=self._sweep_forever, args=(mandate_id, run_id), name="step-up-sweeper", daemon=True)
        self._sweeper.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sweeper is not None:
            self._sweeper.join()
