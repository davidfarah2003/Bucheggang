"""Mirror of viseca-2026/data/schemas/authorization_event.schema.json."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ._base import Contract, Day, NonEmpty, Timestamp

Currency = Literal["CHF", "EUR", "GBP", "USD"]
Operator = Literal["<", "<=", "=", "!=", ">", ">=", "in", "not_in"]
RuleValue = int | float | str | list[str]
TriState = Literal["true", "false", "unknown", "not_applicable"]


class Merchant(Contract):
    merchant_id: NonEmpty
    merchant_name: NonEmpty
    merchant_category: NonEmpty
    merchant_mcc: Annotated[str, Field(pattern=r"^[0-9]{4}$")]
    merchant_country: Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
    merchant_city: NonEmpty
    availability: Literal["online", "store", "store_and_online", "atm"]
    recurring_capable: Literal["true", "false"]


class Item(Contract):
    line_no: Annotated[int, Field(ge=1)]
    item_id: NonEmpty
    item_name: NonEmpty
    item_category: NonEmpty
    quantity: Annotated[int, Field(ge=1)]
    unit_price: Annotated[float, Field(gt=0)]
    currency: Currency
    item_details: str  # untrusted merchant text


class Authorization(Contract):
    authorization_id: NonEmpty
    source_authorization_id: NonEmpty
    scenario_id: Annotated[str, Field(pattern=r"^SCEN[0-9]{4}$")]
    replay_order: Annotated[int, Field(ge=1)]
    mandate_id: NonEmpty
    profile_id: NonEmpty
    card_id: NonEmpty
    initiator_type: Literal["agent"]
    merchant: Merchant
    timestamp: Timestamp
    amount: Annotated[float, Field(gt=0)]
    currency: Currency
    billing_amount_chf: Annotated[float, Field(gt=0)]
    items_subtotal: Annotated[float, Field(gt=0)]
    delivery_fee: Annotated[float, Field(ge=0)]
    channel: Literal["ecommerce", "in_store", "mobile_wallet", "recurring", "atm"]
    customer_device_id: str
    authority_status: Literal["active", "revoked", "expired"]
    card_status_at_attempt: Literal["active", "blocked"]
    spend_in_period_before_chf: Annotated[float, Field(ge=0)] | None
    recent_attempt_count_10m: Annotated[int, Field(ge=0)]
    fulfillment_method: NonEmpty
    delivery_by: Day | None
    order_returnable: TriState
    order_cancellable: TriState
    related_authorization_id: str | None
    related_authorization_status: Literal["pending", "approved", "declined", "cancelled"] | None
    purchase_description: NonEmpty
    items: Annotated[list[Item], Field(min_length=1)]


class MandateRule(Contract):
    """A rule as the simulator stores it."""

    field: NonEmpty
    operator: Operator
    value: RuleValue
    currency: Currency | None = None
    scope: Literal["purchase", "period"] | None = None
    period_days: Annotated[int, Field(ge=1)] | None = None


class EventMandate(Contract):
    mandate_id: NonEmpty
    status: Literal["active", "superseded", "revoked", "expired"]
    customer_id: NonEmpty
    card_id: NonEmpty
    instruction: NonEmpty
    hard_rules: list[MandateRule]
    uncertainty_policy: Literal["ask", "decline", "approve"]
    profile_id: NonEmpty


class RecentAuthorization(Contract):
    authorization_id: NonEmpty
    timestamp: Timestamp
    merchant_id: NonEmpty
    billing_amount_chf: Annotated[float, Field(ge=0)]
    status: Literal["approved", "declined", "pending", "cancelled"]


class EventContext(Contract):
    approved_spend_in_period_chf: Annotated[float, Field(ge=0)] | None
    recent_authorizations: list[RecentAuthorization]


class Runtime(Contract):
    received_at: Timestamp
    history_window_minutes: Annotated[int, Field(ge=1)]
    context_basis: Literal["run_decisions_and_scenario_timestamps"]


class Event(Contract):
    type: Literal["authorization.request"]
    request_id: NonEmpty
    deadline_at: Timestamp
    authorization: Authorization
    mandate: EventMandate
    context: EventContext
    runtime: Runtime
