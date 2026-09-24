"""Facts in, checks and decisions out, mandate state, step-ups."""

from __future__ import annotations

from typing import Literal

from ._base import Contract, NonEmpty, Timestamp
from .event import Event

REASON_CODES = frozenset(
    {
        "within_policy", "amount_over_limit", "period_limit_exceeded", "purchase_count_exceeded",
        "mandate_expired", "mandate_revoked", "item_mismatch", "unrequested_item",
        "return_terms_missing", "return_terms_short", "merchant_type_mismatch",
        "unfamiliar_merchant", "lookalike_merchant", "gift_card", "subscription",
        "protection_plan", "duplicate_order", "requote_after_decline", "velocity", "new_device",
        "country_blocked", "injected_instructions", "customer_confirmation", "customer_declined",
        "step_up_timeout", "engine_timeout",
    }
)
ReasonCode = Literal[
    "within_policy", "amount_over_limit", "period_limit_exceeded", "purchase_count_exceeded",
    "mandate_expired", "mandate_revoked", "item_mismatch", "unrequested_item",
    "return_terms_missing", "return_terms_short", "merchant_type_mismatch",
    "unfamiliar_merchant", "lookalike_merchant", "gift_card", "subscription",
    "protection_plan", "duplicate_order", "requote_after_decline", "velocity", "new_device",
    "country_blocked", "injected_instructions", "customer_confirmation", "customer_declined",
    "step_up_timeout", "engine_timeout",
]
Outcome = Literal["approve", "decline", "step_up"]
FactSource = Literal["structured", "merchant_text", "model"]


class PurchaseFacts(Contract):
    """One cart line. `None` means unknown."""

    item_id: NonEmpty
    product_type: str | None
    size: str | None
    return_days: int | None
    is_addon: bool | None
    is_gift_card: bool | None
    is_subscription: bool | None
    is_protection_plan: bool | None
    matches_request: bool | None
    contains_instructions: bool
    excerpt: str | None
    sources: dict[str, FactSource]


class Check(Contract):
    name: NonEmpty
    result: Literal["pass", "fail", "uncertain"]
    value: str | int | float | None
    source: Literal["event", "history", "merchant_text", "model", "state"]
    note: str


class Decision(Contract):
    authorization_id: NonEmpty
    decision: Outcome
    reason_codes: list[ReasonCode]
    customer_message: NonEmpty
    evidence: list[Check]
    explanation: NonEmpty
    engine_version: NonEmpty
    mandate_version: int
    elapsed_ms: int
    decided_at: Timestamp


class Approval(Contract):
    authorization_id: NonEmpty
    amount_chf: float
    timestamp: Timestamp  # simulated time of the purchase


class MandateState(Contract):
    mandate_id: NonEmpty
    approvals: list[Approval] = []
    handled: dict[str, Decision] = {}
    pending_step_ups: list[str] = []
    declined: list[str] = []


class StepUp(Contract):
    authorization_id: NonEmpty
    decision: Decision
    event: Event
    expires_at: Timestamp


class StepUpAnswer(Contract):
    authorization_id: NonEmpty
    decision: Literal["approve", "decline"]
    customer_message: str
    answered_at: Timestamp
