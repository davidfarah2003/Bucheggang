"""Facts in, checks and decisions out, mandate state, step-ups."""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from ._base import Contract, NonEmpty, Timestamp
from .event import Event

FACT_FIELDS = frozenset(
    {"product_type", "size", "return_days", "is_addon", "is_gift_card", "is_subscription",
     "is_protection_plan", "matches_request"}
)

REASON_CODES = frozenset(
    {
        "within_policy", "amount_over_limit", "period_limit_exceeded", "purchase_count_exceeded",
        "mandate_expired", "mandate_revoked", "item_mismatch", "unrequested_item",
        "return_terms_missing", "return_terms_short", "merchant_type_mismatch",
        "unfamiliar_merchant", "lookalike_merchant", "gift_card", "subscription",
        "protection_plan", "duplicate_order", "requote_after_decline", "velocity", "new_device",
        "country_blocked", "country_unfamiliar", "no_card_history", "injected_instructions", "customer_confirmation", "customer_declined",
        "step_up_timeout", "engine_timeout", "model_history_uncertain", "fact_conflict",
    }
)
ReasonCode = Literal[
    "within_policy", "amount_over_limit", "period_limit_exceeded", "purchase_count_exceeded",
    "mandate_expired", "mandate_revoked", "item_mismatch", "unrequested_item",
    "return_terms_missing", "return_terms_short", "merchant_type_mismatch",
    "unfamiliar_merchant", "lookalike_merchant", "gift_card", "subscription",
    "protection_plan", "duplicate_order", "requote_after_decline", "velocity", "new_device",
    "country_blocked", "country_unfamiliar", "no_card_history", "injected_instructions", "customer_confirmation", "customer_declined",
    "step_up_timeout", "engine_timeout", "model_history_uncertain", "fact_conflict",
]
Outcome = Literal["approve", "decline", "step_up"]
FactSource = Literal["agent_form", "structured", "merchant_text"]
ConflictKind = Literal["merchant_text_contradiction", "catalogue_event_mismatch"]


class FactConflict(Contract):
    """Two observations of one fact on one line disagree.

    `merchant_text_contradiction`: the merchant copy states the fact twice with different values
    ("No returns. Returns accepted within 30 days.", two sizes). `catalogue_event_mismatch`: the
    local catalogue and the event's structured item fields disagree on name or category. The
    extractor leaves the field unknown and records the conflict here instead of picking a side.
    """

    field: NonEmpty
    kind: ConflictKind


class PurchaseFacts(Contract):
    """One cart line. `None` means unknown. A field named in `conflicts` is unknown by contradiction."""

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
    conflicts: list[FactConflict] = []

    @model_validator(mode="after")
    def _conflicts_are_unknown(self) -> "PurchaseFacts":
        seen: set[str] = set()
        for conflict in self.conflicts:
            if conflict.field in seen:
                raise ValueError(f"line {self.item_id}: field {conflict.field!r} is marked conflicting twice")
            seen.add(conflict.field)
            if conflict.field not in FACT_FIELDS:
                raise ValueError(f"line {self.item_id}: conflict names {conflict.field!r}, not a fact field")
            if getattr(self, conflict.field) is not None:
                raise ValueError(f"line {self.item_id}: field {conflict.field!r} is marked conflicting but has a value")
            if conflict.field in self.sources:
                raise ValueError(f"line {self.item_id}: field {conflict.field!r} is marked conflicting and has a source")
        return self


class Check(Contract):
    name: NonEmpty
    result: Literal["pass", "fail", "uncertain"]
    value: str | int | float | None
    source: Literal["event", "history", "agent_form", "merchant_text", "state", "model"]
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
    merchant_id: NonEmpty
    amount_chf: float
    timestamp: Timestamp  # simulated time of the purchase
    device_id: str | None = None  # customer_device_id of the approved purchase; absent on older records


class CustomerApproval(Contract):
    """An accepted approval on another mandate of the same customer, for cross-mandate period rules."""

    authorization_id: NonEmpty
    mandate_id: NonEmpty
    amount_chf: float
    timestamp: Timestamp  # simulated time of the purchase


class MandateState(Contract):
    mandate_id: NonEmpty
    approvals: list[Approval] = []
    handled: dict[str, Decision] = {}
    pending_step_ups: list[str] = []
    declined: list[str] = []
    customer_approvals: list[CustomerApproval] = []  # filled by state.load, never by record


class HistoryAuthorization(Contract):
    """One row of authorization_history.csv, the columns the engine reads and nothing else.

    `timestamp` is the simulated time. Only rows with `status: approved` and
    `transaction_type: purchase` count as familiarity; every row counts toward card history.
    """

    authorization_id: NonEmpty
    card_id: NonEmpty
    timestamp: Timestamp
    transaction_type: NonEmpty
    status: NonEmpty
    merchant_id: NonEmpty
    merchant_name: str
    merchant_country: NonEmpty
    customer_device_id: str | None


class History(Contract):
    """An explicit, frozen history slice for `evaluate(..., history=)`; replaces the packaged CSVs."""

    authorizations: list[HistoryAuthorization]

    @model_validator(mode="after")
    def _unique_ids(self) -> "History":
        ids = [a.authorization_id for a in self.authorizations]
        if len(ids) != len(set(ids)):
            dup = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"history lists authorization {dup} more than once")
        return self


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
