"""Bind a pre-event customer history profile to one authorized purchase."""

from __future__ import annotations

import hashlib
import json

from leash.contracts import Event, PolicyDraft

from .history import HistoryIndex
from .types import AssessmentBundle, HistoryFeatures


def purchase_digest(event: Event, features: HistoryFeatures) -> str:
    """Bind the purchase and feature map locally; this is an integrity check, not authentication."""
    payload = {
        "authorization": event.authorization.model_dump(mode="json"),
        "mandate_id": event.mandate.mandate_id,
        "customer_id": event.mandate.customer_id,
        "card_id": event.mandate.card_id,
        "features": features.model_dump(mode="json"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def history_bundle(event: Event, policy: PolicyDraft, history: HistoryIndex) -> AssessmentBundle:
    """The explicit model-off stage; a failed history read raises before evaluation."""
    features = history.for_event(event)
    return AssessmentBundle(
        authorization_id=event.authorization.authorization_id,
        purchase_digest=purchase_digest(event, features), policy_hash=policy.hash,
        as_of=event.authorization.timestamp, features=features,
        behaviour=None, semantic=None,
    )


def validate_bundle(event: Event, policy: PolicyDraft, bundle: AssessmentBundle) -> None:
    auth, mandate = event.authorization, event.mandate
    if bundle.authorization_id != auth.authorization_id:
        raise ValueError(f"{auth.authorization_id}: assessment authorization differs")
    if bundle.purchase_digest != purchase_digest(event, bundle.features):
        raise ValueError(f"{auth.authorization_id}: assessment purchase digest differs")
    if bundle.policy_hash != policy.hash:
        raise ValueError(f"{auth.authorization_id}: assessment policy hash differs")
    if bundle.as_of != auth.timestamp or bundle.features.as_of != auth.timestamp:
        raise ValueError(f"{auth.authorization_id}: assessment event time differs")
    if bundle.features.customer_id != mandate.customer_id or bundle.features.card_id != mandate.card_id:
        raise ValueError(f"{auth.authorization_id}: assessment customer or card differs")
