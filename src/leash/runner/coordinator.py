"""Serialize customer-owned mutations and finish their durable local records."""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Iterator

from leash.contracts import Decision, Event, MandateState, StepUp
from leash.policy.store import DraftStore

from . import records
from .intents import Intent, MutationJournal, UnresolvedMutation
from .policy_context import confirmation, confirmation_record

if TYPE_CHECKING:
    from .stepups import StepUpBook


class Coordinator:
    def __init__(self, store: DraftStore, book: StepUpBook):
        self.store = store
        self.book = book
        self.journal = MutationJournal()

    @contextmanager
    def locked(self, mandate_id: str, *, deadline_at: datetime) -> Iterator[list[str]]:
        if deadline_at.utcoffset() is None:
            raise ValueError("coordination deadline must have a timezone")
        stop_at = time.monotonic() + (deadline_at - datetime.now(UTC)).total_seconds()
        owner_record = confirmation_record(self.store, mandate_id)
        with records.customer_lock(owner_record["confirmed_by"], stop_at=stop_at):
            record, mandate_ids = confirmation(self.store, mandate_id)
            if record != owner_record:
                raise UnresolvedMutation(f"{mandate_id}: confirmation owner changed while acquiring the customer guard")
            with records.mandate_locks(mandate_ids, deadline_at=deadline_at, stop_at=stop_at):
                current, current_ids = confirmation(self.store, mandate_id)
                if current != record or current_ids != mandate_ids:
                    raise UnresolvedMutation(f"{mandate_id}: customer confirmation set changed while acquiring locks")
                from leash.policy.purchases import recover_local_purchases

                for owned_id in mandate_ids:
                    pending = self.journal.pending(owned_id)
                    recover_local_purchases(owned_id, self.book, remote_pending=bool(pending))
                    for intent in pending:
                        accepted = self.journal.reconcile(intent, deadline_at=deadline_at)
                        self.record(accepted)
                    records.check_consistent(owned_id)
                self.journal.require_clear(mandate_ids)
                yield mandate_ids

    def record(self, intent: Intent) -> Decision | None:
        """Finish an accepted intent. Caller holds the complete owned mandate set."""
        if intent.status != "accepted":
            raise UnresolvedMutation(f"{intent.intent_id}: local recording requires an accepted intent")
        if intent.operation in ("tighten", "revoke"):
            self._record_mandate(intent)
            self.journal.complete(intent)
            return None
        event = Event.model_validate(intent.context["event"])
        decision = intent.observed_decision or Decision.model_validate(intent.context["decision"])
        before = MandateState.model_validate(intent.context["state_before"])
        records.recover_accepted(
            event, decision, intent.accepted_at, intent.accepted,
            resolution=intent.operation == "resolve", state_before=before,
        )
        path = self.book._path(intent.mandate_id, decision.authorization_id)
        if intent.operation == "resolve":
            step_up = StepUp.model_validate(intent.context["step_up"])
            saved = self.book._read(path)
            expected = {
                "step_up": step_up.model_dump(mode="json"), "status": "resolved",
                "run_id": intent.context["run_id"],
                "resolution": {"decision": decision.model_dump(mode="json"), "accepted": intent.accepted,
                               "accepted_at": intent.accepted_at.isoformat()},
            }
            if saved["step_up"] != step_up:
                raise UnresolvedMutation(f"{intent.intent_id}: saved pending purchase differs")
            if saved["status"] == "resolved":
                saved["step_up"] = saved["step_up"].model_dump(mode="json")
                if saved != expected:
                    raise UnresolvedMutation(f"{intent.intent_id}: saved resolution differs")
            else:
                records.write_atomic(path, expected)
        elif decision.decision == "step_up":
            from .stepups import EXPIRY_MARGIN_S

            expiry = datetime.fromisoformat(intent.accepted["step_up_expires_at"].replace("Z", "+00:00"))
            step_up = StepUp(
                authorization_id=decision.authorization_id, decision=decision, event=event,
                expires_at=expiry - timedelta(seconds=EXPIRY_MARGIN_S),
            )
            expected = {"step_up": step_up.model_dump(mode="json"), "status": "pending",
                        "resolution": None, "run_id": intent.context["run_id"]}
            if path.exists():
                saved = self.book._read(path)
                saved["step_up"] = saved["step_up"].model_dump(mode="json")
                if saved != expected:
                    raise UnresolvedMutation(f"{intent.intent_id}: saved step-up differs")
            else:
                records.write_atomic(path, expected)
        self.journal.complete(intent)
        return decision

    def _record_mandate(self, intent: Intent) -> None:
        from leash.api.mandates import MandateEdits, _effective

        if intent.operation == "revoke":
            return
        edits_store = MandateEdits(self.store)
        before, after = intent.context["edits_before"], intent.context["edits_after"]
        current = edits_store.read(intent.mandate_id)
        if current != before and current != after:
            raise UnresolvedMutation(f"{intent.intent_id}: mandate edits changed outside the intent")
        _effective(intent.accepted, intent.context["draft"], after, intent.context["confirmation"])
        if current == before:
            edits_store.write(intent.mandate_id, after)
        records.sync_directory(edits_store.root)
        records.sync_directory(edits_store.root.parent)

    def authorization(
        self, *, event: Event, decision: Decision, state_before: MandateState,
        run_id: str, deadline_at: datetime, step_up: StepUp | None = None,
        evaluated_state: MandateState | None = None, policy: dict | None = None, observe_expiry: bool = False,
    ) -> Decision:
        """Prepare, send once, then record. Caller holds the owned mandate locks."""
        resolution = step_up is not None
        if observe_expiry and (step_up is None or decision.decision != "decline" or datetime.now(UTC) < step_up.expires_at):
            raise UnresolvedMutation("expiry observation requires an expired pending purchase and a decline")
        body = {
            "decision": decision.decision, "customer_message": decision.customer_message,
            "evidence": [check.model_dump(mode="json") for check in decision.evidence],
        }
        if not resolution:
            body.update(authorization_id=decision.authorization_id,
                        reason_codes=list(decision.reason_codes), engine_version=decision.engine_version)
        context = {
            "authorization_id": decision.authorization_id, "run_id": run_id,
            "event": event.model_dump(mode="json"), "decision": decision.model_dump(mode="json"),
            "state_before": state_before.model_dump(mode="json"),
        }
        if step_up is not None:
            context["step_up"] = step_up.model_dump(mode="json")
        if evaluated_state is not None:
            context["evaluated_state"] = evaluated_state.model_dump(mode="json")
        if policy is not None:
            context["effective_policy"] = policy
        suffix = "resolve" if resolution else "decision"
        intent = self.journal.prepare(
            event.mandate.mandate_id, "resolve" if resolution else "submit", method="POST",
            path=f"/v1/authorizations/{decision.authorization_id}/{suffix}",
            body=body, context=context, deadline_at=deadline_at, dispatch_allowed=not observe_expiry,
        )
        accepted = (self.journal.reconcile(intent, deadline_at=deadline_at) if observe_expiry
                    else self.journal.dispatch(intent))
        result = self.record(accepted)
        if result is None:
            raise UnresolvedMutation(f"{intent.intent_id}: authorization recording produced no decision")
        return result
