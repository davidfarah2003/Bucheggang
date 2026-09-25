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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from leash.contracts import Decision, Event, MandateState, StepUp, StepUpAnswer
from leash.engine import state as engine_state
from leash.engine.evaluate import evaluate
from leash.policy.store import DraftStore

from . import api, records, policy_context
from .coordinator import Coordinator

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

    def _checked_decision(
        self, step_up: StepUp, store: DraftStore, mandate_ids: list[str], deadline_at: datetime,
    ) -> tuple[Decision, MandateState, dict]:
        from .loop import extract_with_budget, decide_with_guard

        state = engine_state.load(step_up.event.mandate.mandate_id, customer_mandates=mandate_ids)
        if state.handled.get(step_up.authorization_id) != step_up.decision:
            raise StepUpError(f"{step_up.authorization_id}: saved state differs from the pending decision")
        unchecked = state.model_copy(deep=True)
        del unchecked.handled[step_up.authorization_id]
        unchecked.pending_step_ups.remove(step_up.authorization_id)
        event, policy = policy_context.refresh(store, step_up.event, deadline_at=deadline_at - timedelta(seconds=2))
        event.deadline_at = deadline_at
        with ThreadPoolExecutor(max_workers=1) as pool:
            facts = extract_with_budget(event, policy, pool)
            checked = decide_with_guard(evaluate, event, policy, unchecked, facts, pool)
        return checked, state, policy.model_dump(mode="json")

    def _finish(
        self, step_up: StepUp, decision: Decision, coordinator: Coordinator,
        *, run_id: str, mandate_ids: list[str], deadline_at: datetime, evaluated_state: MandateState | None = None,
        policy: dict | None = None, observe_expiry: bool = False,
    ) -> Any:
        """Write ahead, resolve once, and finish the accepted state and history."""
        coordinator.authorization(
            event=step_up.event, decision=decision,
            state_before=engine_state.load(step_up.event.mandate.mandate_id, customer_mandates=mandate_ids).model_copy(update={"customer_approvals": []}),
            run_id=run_id, deadline_at=deadline_at, step_up=step_up,
            evaluated_state=evaluated_state, policy=policy, observe_expiry=observe_expiry,
        )
        saved = self._read(self._path(step_up.event.mandate.mandate_id, step_up.authorization_id))
        log.info("resolved %s %s %s", step_up.authorization_id, decision.decision, decision.reason_codes)
        return saved["resolution"]["accepted"]

    @staticmethod
    def _final(step_up: StepUp, outcome: str, codes: list[str], message: str, explanation: str) -> Decision:
        return Decision(
            authorization_id=step_up.authorization_id, decision=outcome, reason_codes=codes,
            customer_message=message, evidence=step_up.decision.evidence, explanation=explanation,
            engine_version=step_up.decision.engine_version, mandate_version=step_up.decision.mandate_version,
            elapsed_ms=step_up.decision.elapsed_ms, decided_at=_now(),
        )

    def answer(self, answer: StepUpAnswer, store: DraftStore) -> Any:
        """Resolve an actual customer answer after checking current permissions and spend."""
        step_up = self.get(answer.authorization_id)
        mandate_id = step_up.event.mandate.mandate_id
        coordinator = Coordinator(store, self)
        with coordinator.locked(mandate_id, deadline_at=step_up.expires_at) as mandate_ids:
            record = self._read(self._path(mandate_id, answer.authorization_id))
            if record["status"] != "pending":
                raise StepUpError(f"step-up {answer.authorization_id} is already resolved")
            if _now() >= step_up.expires_at:
                raise StepUpError(f"step-up {answer.authorization_id} expired at {step_up.expires_at.isoformat()}")
            run_id = record.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                raise StepUpError(f"step-up {answer.authorization_id} lacks its recorded run identity")
            checked_state, policy = None, None
            if answer.decision == "approve":
                checked, checked_state, policy = self._checked_decision(step_up, store, mandate_ids, step_up.expires_at)
                if checked.decision == "decline":
                    final = checked
                else:
                    final = checked.model_copy(update={
                        "decision": "approve", "reason_codes": ["customer_confirmation"],
                        "customer_message": answer.customer_message,
                        "explanation": "The customer approved this purchase. Current permissions, spending and count limits were checked again before resolution.",
                    })
            else:
                final = self._final(
                    step_up, "decline", ["customer_declined"], answer.customer_message,
                    "The customer declined this purchase.",
                )
            return self._finish(
                step_up, final, coordinator, run_id=run_id, mandate_ids=mandate_ids, deadline_at=step_up.expires_at,
                evaluated_state=checked_state, policy=policy,
            )

    def sweep(self, mandate_id: str, run_id: str, store: DraftStore) -> list[str]:
        """Resolve expired or withdrawn permissions, reading back uncertain outcomes."""
        done = []
        coordinator = Coordinator(store, self)
        with coordinator.locked(mandate_id, deadline_at=_now() + timedelta(seconds=30)) as mandate_ids:
            for step_up in self.pending(mandate_id):
                now = _now()
                if now >= step_up.expires_at:
                    final = self._final(
                        step_up, "decline", ["step_up_timeout"],
                        "You did not answer in time, so this purchase was declined.",
                        f"No customer answer before {step_up.expires_at.isoformat()}; declined on timeout.",
                    )
                    timeout_deadline = step_up.expires_at + timedelta(seconds=EXPIRY_MARGIN_S)
                    observe = now >= timeout_deadline
                    self._finish(
                        step_up, final, coordinator, run_id=run_id, mandate_ids=mandate_ids, observe_expiry=observe,
                        deadline_at=now + timedelta(seconds=30) if observe else timeout_deadline,
                    )
                    done.append(step_up.authorization_id)
                    continue
                if now >= step_up.expires_at - timedelta(seconds=3):
                    continue  # Keep the remaining window for the scheduled timeout resolution.
                event, _ = policy_context.refresh(store, step_up.event, deadline_at=step_up.expires_at - timedelta(seconds=2))
                if event.mandate.status != "active":
                    checked, state, policy = self._checked_decision(step_up, store, mandate_ids, step_up.expires_at)
                    if checked.decision != "decline":
                        raise StepUpError(f"{step_up.authorization_id}: inactive mandate did not produce a decline")
                    self._finish(
                        step_up, checked, coordinator, run_id=run_id, mandate_ids=mandate_ids, deadline_at=step_up.expires_at,
                        evaluated_state=state, policy=policy,
                    )
                    done.append(step_up.authorization_id)
        return done

    # sweeper thread (run loop process only)

    def _sweep_forever(self, mandate_id: str, run_id: str, store: DraftStore) -> None:
        try:
            while not self._stop.wait(SWEEP_INTERVAL_S):
                self.sweep(mandate_id, run_id, store)
        except BaseException as exc:
            # Kept for the run loop, which re-raises it; the thread then ends.
            self.failure = exc
            log.error("step-up sweeper stopped: %r", exc)
            raise

    def raise_failure(self) -> None:
        if self.failure is not None:
            raise StepUpError("step-up sweeper failed; pending step-ups are no longer timed out") from self.failure

    def start(self, mandate_id: str, run_id: str, store: DraftStore) -> None:
        self._sweeper = threading.Thread(target=self._sweep_forever, args=(mandate_id, run_id, store), name="step-up-sweeper", daemon=True)
        self._sweeper.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sweeper is not None:
            self._sweeper.join()
