"""Explicit history-only evaluator for a runner configured without model calls."""

from __future__ import annotations

from leash.contracts import Check, Decision, Event, MandateState, PolicyDraft, PurchaseFacts
from leash.engine.evaluate import evaluate

from .assess import history_bundle, validate_bundle
from .history import HistoryIndex


class HistoryOnlyEvaluator:
    def __init__(self, history: HistoryIndex) -> None:
        self.history = history

    def __call__(self, event: Event, policy: PolicyDraft, state: MandateState,
                 facts: list[PurchaseFacts] | None) -> Decision:
        if facts is None:
            raise ValueError(f"{event.authorization.authorization_id}: extraction facts are missing")
        bundle = history_bundle(event, policy, self.history)
        validate_bundle(event, policy, bundle)
        decision = evaluate(event, policy, state, facts, assessments=bundle)
        if event.authorization.authorization_id in state.handled:
            return decision
        check = Check(
            name="personal history profile", result="pass", value=bundle.purchase_digest,
            source="history",
            note=f"Authorized {bundle.features.schema_version} pre-event card and customer features were validated for this purchase.",
        )
        return Decision.model_validate(decision.model_copy(update={
            "evidence": [*decision.evidence, check],
        }).model_dump(mode="python"))
