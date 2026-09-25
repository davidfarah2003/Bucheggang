"""evaluate(event, policy, state, facts, assessments=None, history=None). Pure: no I/O or model calls."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from leash.contracts import AssessmentBundle, Check, Decision, Event, History, MandateState, PolicyDraft, PurchaseFacts
from leash.contracts.event import MandateRule

from . import checks
from .data import HISTORY
from .data import History as HistoryIndex
from .model_checks import model_checks, validate_assessments
from .rules import RuleContext, conflicted, evaluate_rule, reason_code
from .words import Finding, compose

ENGINE_VERSION = "leash-engine 0.6"
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


def _history_index(history: History | None) -> HistoryIndex:
    """The packaged CSVs, or an explicit frozen slice that replaces them entirely for this call."""
    if history is None:
        return HISTORY
    rows = [
        {
            "authorization_id": a.authorization_id,
            "card_id": a.card_id,
            "timestamp": a.timestamp.isoformat().replace("+00:00", "Z"),
            "transaction_type": a.transaction_type,
            "status": a.status,
            "merchant_id": a.merchant_id,
            "merchant_name": a.merchant_name,
            "merchant_country": a.merchant_country,
            "customer_device_id": a.customer_device_id or "",
        }
        for a in history.authorizations
    ]
    return HistoryIndex.from_rows(rows)


def evaluate(event: Event, policy: PolicyDraft, state: MandateState,
             facts: list[PurchaseFacts] | None, assessments: AssessmentBundle | None = None,
             history: History | None = None) -> Decision:
    start = time.perf_counter()
    if assessments is not None:
        assessments = validate_assessments(event, policy, state, assessments)
    auth_id = event.authorization.authorization_id
    handled = state.handled.get(auth_id)
    if handled is not None:
        return handled  # a repeated delivery of a purchase already decided

    index = _history_index(history)
    raw_ctx = RuleContext(event, state, facts, index)
    ctx = RuleContext(event, state, _quarantine(facts), index)

    evidence: list[Check] = []
    findings: list[Finding] = []
    fails: list[str] = []
    uncertain: list[str] = []
    conflict_hit = False

    def add(check: Check, code: str | None, rule=None, conflict: bool = False) -> None:
        nonlocal conflict_hit
        evidence.append(check)
        findings.append(Finding(check, rule))
        if check.result == "fail":
            fails.append(code)
        elif check.result == "uncertain":
            uncertain.append(code)
            if conflict:
                uncertain.append("fact_conflict")
                conflict_hit = True

    first = checks.mandate_active(raw_ctx)
    add(first.check, first.code)
    for rule in _rules(policy, event):
        check = evaluate_rule(rule, ctx)
        add(check, reason_code(rule, check), rule, conflict=check.result == "uncertain" and conflicted(rule, ctx))
    for fn in checks.CHECKS:
        result = fn(raw_ctx if fn is checks.injected else ctx)
        if result is not None:  # a check another check already covers for this purchase
            add(result.check, result.code)

    if assessments is not None:
        for check in model_checks(assessments):
            add(check, "model_history_uncertain" if check.result == "uncertain" else None)

    policy_mode = _uncertainty(policy, event)
    if fails:
        outcome, codes = "decline", fails
    elif uncertain:
        outcome = {"ask": "step_up", "decline": "decline", "approve": "approve"}[policy_mode]
        if outcome == "approve" and conflict_hit:
            outcome = "step_up"  # contract: a conflict-affected uncertain check never resolves to approve
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

