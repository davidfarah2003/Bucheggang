"""Policy drafts, rules and confirmed mandates."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ._base import Contract, NonEmpty, Timestamp
from .event import Currency, Operator, RuleValue

UncertaintyPolicy = Literal["ask", "decline", "approve"]

RULE_FIELDS = frozenset(
    {
        "authorization.billing_amount_chf",
        "authorization.items_subtotal",
        "authorization.delivery_fee",
        "authorization.currency",
        "authorization.channel",
        "authorization.fulfillment_method",
        "authorization.order_returnable",
        "authorization.merchant.merchant_id",
        "authorization.merchant.merchant_category",
        "authorization.merchant.merchant_mcc",
        "authorization.merchant.merchant_country",
        "items.category",
        "items.count",
        "facts.product_type",
        "facts.size",
        "facts.return_days",
        "facts.is_gift_card",
        "facts.is_subscription",
        "facts.is_protection_plan",
        "facts.is_addon",
        "history.merchant_seen_on_card",
        "history.device_seen_on_card",
        "state.approvals_count",
    }
)


class Rule(Contract):
    """The simulator rule plus `source_text` and `plain_english`, which stay ours."""

    field: NonEmpty
    operator: Operator
    value: RuleValue
    currency: Currency | None = None
    scope: Literal["purchase", "period"] | None = None
    period_days: Annotated[int, Field(ge=1)] | None = None
    source_text: NonEmpty
    plain_english: NonEmpty

    @model_validator(mode="after")
    def _known_field(self) -> "Rule":
        if self.field not in RULE_FIELDS:
            raise ValueError(f"rule field {self.field!r} is not in the contract vocabulary")
        if self.scope == "period" and self.period_days is None:
            raise ValueError(f"period rule on {self.field!r} has no period_days")
        return self

    def simulator_rule(self) -> dict:
        """The rule as POST /v1/mandates accepts it."""
        return self.model_dump(exclude={"source_text", "plain_english"}, exclude_none=True)


class Example(Contract):
    description: NonEmpty
    expected: Literal["approve", "decline", "step_up"]
    why: NonEmpty


class OpenQuestion(Contract):
    question: NonEmpty
    options: list[str]
    confirming_answers: list[str]
    answer: str | None = None

    @model_validator(mode="after")
    def _subset(self) -> "OpenQuestion":
        extra = set(self.confirming_answers) - set(self.options)
        if extra:
            raise ValueError(f"confirming_answers not in options: {sorted(extra)}")
        return self


class PolicyDraft(Contract):
    draft_id: NonEmpty
    version: Annotated[int, Field(ge=1)]
    hash: NonEmpty
    instruction: NonEmpty
    rules: list[Rule]
    examples: list[Example]
    open_questions: list[OpenQuestion]
    uncertainty_policy: UncertaintyPolicy
    created_at: Timestamp


class Mandate(Contract):
    mandate_id: NonEmpty
    draft_id: NonEmpty
    version: Annotated[int, Field(ge=1)]
    hash: NonEmpty
    status: Literal["active", "revoked", "expired"]
    confirmed_at: Timestamp
