"""Bind a pre-event customer history profile to one authorized purchase."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from leash.contracts import Event, MandateState, PolicyDraft

from .history import HistoryIndex
from .jev import assess_jev
from .types import AssessmentBundle, HistoryFeatures

if TYPE_CHECKING:
    from .behaviour import BehaviorModel


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


async def assess(event: Event, policy: PolicyDraft, state: MandateState,
                 history: HistoryIndex, *, api_key: str,
                 behaviour_model: BehaviorModel | None = None) -> AssessmentBundle:
    """Call Jev on this mandate's own numeric history; dependency failures propagate."""
    if state.mandate_id != event.mandate.mandate_id:
        raise ValueError(f"{event.authorization.authorization_id}: assessment state mandate differs")
    base = history_bundle(event, policy, history)
    behaviour = behaviour_model.score(base.features) if behaviour_model is not None else None
    semantic = await assess_jev(base.features, event.deadline_at, api_key=api_key)
    result = AssessmentBundle(
        authorization_id=base.authorization_id, purchase_digest=base.purchase_digest,
        policy_hash=base.policy_hash, as_of=base.as_of, features=base.features,
        behaviour=behaviour, semantic=semantic,
    )
    validate_bundle(event, policy, result)
    return result
