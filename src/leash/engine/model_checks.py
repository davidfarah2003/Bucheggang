"""Pure composition of successful history assessments into visible checks."""

from __future__ import annotations

import json

from leash.contracts.classifier import AssessmentBundle, assessment_purchase_digest
from leash.contracts import Check, Event, MandateState, PolicyDraft


def validate_assessments(
    event: Event, policy: PolicyDraft, state: MandateState, assessments: AssessmentBundle,
) -> AssessmentBundle:
    """Reject stale bindings and revalidate mutable models before composing a decision."""
    if not isinstance(assessments, AssessmentBundle):
        raise TypeError("assessments must use the shared AssessmentBundle contract")
    bundle = AssessmentBundle.model_validate(assessments.model_dump(mode="python"))
    auth, mandate = event.authorization, event.mandate
    if auth.card_id != mandate.card_id or auth.mandate_id != mandate.mandate_id:
        raise ValueError(f"{auth.authorization_id}: authorization and mandate identity differ")
    if state.mandate_id != mandate.mandate_id:
        raise ValueError(f"{auth.authorization_id}: assessment state belongs to another mandate")
    if bundle.authorization_id != auth.authorization_id:
        raise ValueError(f"{auth.authorization_id}: assessment authorization differs")
    if bundle.purchase_digest != assessment_purchase_digest(event):
        raise ValueError(f"{auth.authorization_id}: assessment purchase digest differs")
    if bundle.policy_hash != policy.hash:
        raise ValueError(f"{auth.authorization_id}: assessment policy hash differs")
    if bundle.as_of != auth.timestamp:
        raise ValueError(f"{auth.authorization_id}: assessment event time differs")
    if bundle.features.customer_id != mandate.customer_id or bundle.features.card_id != mandate.card_id:
        raise ValueError(f"{auth.authorization_id}: assessment customer or card differs")
    return bundle


def _value(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


def model_checks(bundle: AssessmentBundle) -> list[Check]:
    """Models can add uncertainty, never satisfy a required fact or create a hard failure."""
    result = []
    behaviour = bundle.behaviour
    if behaviour is not None:
        result.append(Check(
            name="model.behaviour", result="uncertain" if behaviour.escalation_fired else "pass",
            value=_value(behaviour.model_dump(mode="json")), source="model",
            note=("The historical-decline score reached the configured review threshold."
                  if behaviour.escalation_fired else "The historical-decline score adds no escalation."),
        ))
    semantic = bundle.semantic
    if semantic is not None:
        subjects = {"spend_pattern": "purchase amount", "activity_pattern": "purchasing activity"}
        for answer in sorted(semantic.answers, key=lambda item: item.question_id):
            subject = subjects[answer.question_id]
            if answer.selected == "ordinary":
                note = f"The history assessment found no additional concern about the {subject}."
            elif answer.selected == "unusual":
                note = f"The history assessment flagged unusual {subject}."
            elif answer.selected == "unclear":
                note = f"The history assessment could not establish whether the {subject} is ordinary."
            else:
                note = f"The history assessment tied between options for the {subject}."
            result.append(Check(
                name=f"model.jev.{answer.question_id}",
                result="pass" if answer.selected == "ordinary" else "uncertain",
                value=_value({
                    "requested_model": semantic.requested_model,
                    "served_model": semantic.served_model,
                    "prompt_version": semantic.prompt_version,
                    "latency_ms": semantic.latency_ms,
                    "answer": answer.model_dump(mode="json"),
                }), source="model", note=note,
            ))
    return result
