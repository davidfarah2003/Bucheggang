"""Explicit history-only evaluator for a runner configured without model calls."""

from __future__ import annotations

from leash.contracts import Decision, Event, MandateState, PolicyDraft, PurchaseFacts
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
        return evaluate(event, policy, state, facts, assessments=bundle)
