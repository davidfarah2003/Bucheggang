"""Classifier lane types (design section 9). Local to the lane until P1/P2 move them into contracts.

Every builder in the classifier lane codes against these. A change here is agreed on
team.zurichbuchegg.classifier first, then lands on lane/classifier before any branch depends on it.
"""

from __future__ import annotations

from typing import Literal

from leash.contracts._base import Contract, NonEmpty, Timestamp

FEATURE_SCHEMA_VERSION = "hist-1"

Scope = Literal["card", "customer"]


class HistoryFeatures(Contract):
    """Features for one purchase, built from rows strictly before `as_of` in (timestamp, authorization_id) order.

    `values[name]` is None when the feature is undefined for this purchase (empty history, no device).
    `missing[name]` says why: "empty_history", "no_device", "no_prior_in_category" and so on.
    `support[name]` is the number of rows the value was computed from.
    """

    schema_version: NonEmpty
    customer_id: NonEmpty
    card_id: NonEmpty
    as_of: Timestamp
    values: dict[str, float | None]
    missing: dict[str, str]
    support: dict[str, int]


class BehaviorAssessment(Contract):
    """Output of the behavioural model for one purchase."""

    score: float  # calibrated probability of a historical decline, in [0, 1]
    model_id: NonEmpty  # "lr" or "catboost"
    artifact_version: NonEmpty  # sha256 of the artifact file
    feature_schema_version: NonEmpty
    support: dict[str, int]
    escalation_fired: bool  # False until owner ruling O4 sets a threshold


class JevAnswer(Contract):
    question_id: NonEmpty
    options: dict[str, float]  # validated distribution, sums to 1 within 1e-6
    selected: str | None  # local argmax; None on an exact tie


class SemanticAssessment(Contract):
    """Output of one Jev call over the customer's own history."""

    requested_model: NonEmpty
    served_model: NonEmpty
    prompt_version: NonEmpty
    answers: list[JevAnswer]
    latency_ms: int


class AssessmentBundle(Contract):
    authorization_id: NonEmpty
    purchase_digest: NonEmpty
    policy_hash: NonEmpty
    as_of: Timestamp
    features: HistoryFeatures
    behaviour: BehaviorAssessment | None
    semantic: SemanticAssessment | None
