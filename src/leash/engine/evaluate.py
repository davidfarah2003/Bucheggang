"""evaluate(event, policy, state, facts) -> Decision. Pure: no I/O, no model."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from leash.contracts import Check, Decision, Event, MandateState, PolicyDraft, PurchaseFacts
from leash.contracts.event import MandateRule

from . import checks
from .rules import RuleContext, evaluate_rule, reason_code
from .words import Finding, compose

ENGINE_VERSION = "leash-engine 0.4"
STRICTNESS = {"approve": 0, "ask": 1, "decline": 2}
FACT_FIELDS = ("product_type", "size", "return_days", "is_addon", "is_gift_card", "is_subscription",
               "is_protection_plan", "matches_request")


def _rules(policy: PolicyDraft, event: Event) -> list:
    """The confirmed draft's rules plus any rule the simulator holds beyond them (a tighten)."""
    ours = [r.simulator_rule() for r in policy.rules]
    extra = [r for r in event.mandate.hard_rules if r.model_dump(exclude_none=True) not in ours]
    return [*policy.rules, *extra]


def _quarantine(facts: list[PurchaseFacts] | None) -> list[PurchaseFacts] | None:
    """A line whose merchant text addresses the agent keeps none of its extracted facts."""
    if facts is None:
        return None
    return [
        f.model_copy(update={name: None for name in FACT_FIELDS} | {"sources": {}}) if f.contains_instructions else f
        for f in facts
    ]


def _uncertainty(policy: PolicyDraft, event: Event) -> str:
    return max(policy.uncertainty_policy, event.mandate.uncertainty_policy, key=STRICTNESS.__getitem__)


def evaluate(event: Event, policy: PolicyDraft, state: MandateState,
             facts: list[PurchaseFacts] | None) -> Decision:
    auth_id = event.authorization.authorization_id
    handled = state.handled.get(auth_id)
    if handled is not None:
        return handled  # a repeated delivery of a purchase already decided

    start = time.perf_counter()
    raw_ctx = RuleContext(event, state, facts)
    ctx = RuleContext(event, state, _quarantine(facts))

    evidence: list[Check] = []
    findings: list[Finding] = []
    fails: list[str] = []
    uncertain: list[str] = []

    def add(check: Check, code: str | None, rule=None) -> None:
        evidence.append(check)
        findings.append(Finding(check, rule))
        if check.result == "fail":
            fails.append(code)
        elif check.result == "uncertain":
            uncertain.append(code)

    first = checks.mandate_active(raw_ctx)
    add(first.check, first.code)
    for rule in _rules(policy, event):
        check = evaluate_rule(rule, ctx)
        add(check, reason_code(rule, check), rule)
    for fn in checks.CHECKS:
        result = fn(raw_ctx if fn is checks.injected else ctx)
        if result is not None:  # a check another check already covers for this purchase
            add(result.check, result.code)

    policy_mode = _uncertainty(policy, event)
    if fails:
        outcome, codes = "decline", fails
    elif uncertain:
        outcome = {"ask": "step_up", "decline": "decline", "approve": "approve"}[policy_mode]
        codes = uncertain
    else:
        outcome, codes = "approve", ["within_policy"]
    codes = list(dict.fromkeys(codes))

    message, explanation = compose(outcome, findings, policy_mode, event)
    return Decision(
        authorization_id=auth_id,
        decision=outcome,
        reason_codes=codes,
        customer_message=message,
        evidence=evidence,
        explanation=explanation,
        engine_version=ENGINE_VERSION,
        mandate_version=policy.version,
        elapsed_ms=int((time.perf_counter() - start) * 1000),
        decided_at=datetime.now(timezone.utc),
    )

