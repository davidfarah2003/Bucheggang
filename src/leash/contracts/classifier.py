"""History-only classifier inputs and successful assessment outputs."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ._base import Contract, NonEmpty, Timestamp
from .event import Event

FEATURE_SCHEMA_VERSION = "hist-1"
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Count = Annotated[int, Field(ge=0)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
HistoryOption = Literal["ordinary", "unusual", "unclear"]
HISTORY_QUESTIONS = frozenset({"spend_pattern", "activity_pattern"})
HISTORY_OPTIONS = frozenset({"ordinary", "unusual", "unclear"})


class HistoryFeatures(Contract):
    schema_version: Literal["hist-1"]
    customer_id: NonEmpty
    card_id: NonEmpty
    as_of: Timestamp
    values: dict[str, Finite | None] = Field(min_length=1)
    missing: dict[str, NonEmpty]
    support: dict[str, Count]

    @model_validator(mode="after")
    def complete_metadata(self) -> "HistoryFeatures":
        if self.as_of.tzinfo is None:
            raise ValueError("history as_of must have a timezone")
        if self.support.keys() != self.values.keys():
            raise ValueError("history support must cover exactly the feature values")
        if set(self.missing) != {name for name, value in self.values.items() if value is None}:
            raise ValueError("history missing reasons must cover exactly the undefined values")
        return self


class BehaviorAssessment(Contract):
    score: Probability
    model_id: NonEmpty
    artifact_version: Digest
    feature_schema_version: NonEmpty
    support: dict[str, Count]
    escalation_fired: bool


class JevAnswer(Contract):
    question_id: Literal["spend_pattern", "activity_pattern"]
    options: dict[str, Probability]
    selected: HistoryOption | None

    @model_validator(mode="after")
    def distribution(self) -> "JevAnswer":
        if set(self.options) != HISTORY_OPTIONS:
            raise ValueError("history answer options differ from the requested options")
        if not math.isclose(sum(self.options.values()), 1.0, rel_tol=0, abs_tol=1e-6):
            raise ValueError("history answer probabilities do not sum to one")
        top = max(self.options.values())
        winners = [option for option, value in self.options.items() if value == top]
        if len(winners) == 1 and self.selected != winners[0]:
            raise ValueError("history answer selection differs from its unique argmax")
        if len(winners) > 1 and self.selected is not None:
            raise ValueError("a tied history answer must remain uncertain")
        return self


class SemanticAssessment(Contract):
    requested_model: NonEmpty
    served_model: NonEmpty
    prompt_version: NonEmpty
    answers: list[JevAnswer]
    latency_ms: Count

    @model_validator(mode="after")
    def complete_answers(self) -> "SemanticAssessment":
        if self.requested_model != self.served_model:
            raise ValueError("served assessment model differs from the requested model")
        if len(self.answers) != len(HISTORY_QUESTIONS) or {a.question_id for a in self.answers} != HISTORY_QUESTIONS:
            raise ValueError("history assessment must answer each requested question exactly once")
        return self


class AssessmentBundle(Contract):
    authorization_id: NonEmpty
    purchase_digest: Digest
    policy_hash: Digest
    as_of: Timestamp
    features: HistoryFeatures
    behaviour: BehaviorAssessment | None
    semantic: SemanticAssessment | None

    @model_validator(mode="after")
    def consistent_profile(self) -> "AssessmentBundle":
        if self.as_of.tzinfo is None or self.as_of != self.features.as_of:
            raise ValueError("assessment and history times must match and have a timezone")
        if self.behaviour is not None and self.behaviour.feature_schema_version != self.features.schema_version:
            raise ValueError("behaviour artifact and history feature schemas differ")
        return self


def assessment_purchase_digest(event: Event, features: HistoryFeatures) -> str:
    """Bind purchase and feature content locally; this is integrity checking, not authentication."""
    payload = {
        "authorization": event.authorization.model_dump(mode="json"),
        "mandate_id": event.mandate.mandate_id,
        "customer_id": event.mandate.customer_id,
        "card_id": event.mandate.card_id,
        "features": features.model_dump(mode="json"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
