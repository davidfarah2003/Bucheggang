"""Rule evaluation over the field vocabulary in docs/contracts.md.

`evaluate_rule` is pure. A value that is unknown for this purchase makes the
rule `uncertain`, never `pass`. A rule the engine cannot interpret (a field
outside the vocabulary, an operator that does not fit the value) raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from leash.contracts import Check, Event, FactConflict, MandateState, PurchaseFacts, Rule
from leash.contracts.event import MandateRule

from .data import FX_TO_CHF, HISTORY, History

NUMERIC_OPS = frozenset({"<", "<=", ">", ">="})
MONEY_FIELDS = frozenset(
    {"authorization.billing_amount_chf", "authorization.items_subtotal", "authorization.delivery_fee"}
)
EVENT_FIELDS = {
    "authorization.billing_amount_chf": ("billing_amount_chf",),
    "authorization.items_subtotal": ("items_subtotal",),
    "authorization.delivery_fee": ("delivery_fee",),
    "authorization.currency": ("currency",),
    "authorization.channel": ("channel",),
    "authorization.fulfillment_method": ("fulfillment_method",),
    "authorization.order_returnable": ("order_returnable",),
    "authorization.merchant.merchant_id": ("merchant", "merchant_id"),
    "authorization.merchant.merchant_category": ("merchant", "merchant_category"),
    "authorization.merchant.merchant_mcc": ("merchant", "merchant_mcc"),
    "authorization.merchant.merchant_country": ("merchant", "merchant_country"),
}
FACT_FIELDS = frozenset(
    {"product_type", "size", "return_days", "is_gift_card", "is_subscription", "is_protection_plan", "is_addon"}
)
# Values the event uses to say "not supplied". They make a rule uncertain.
UNKNOWN_EVENT_VALUES = frozenset({"unknown"})

AnyRule = Rule | MandateRule


@dataclass(frozen=True)
class RuleContext:
    event: Event
    state: MandateState
    facts: list[PurchaseFacts] | None  # None: the extract lane did not answer
    history: History = HISTORY

    @property
    def no_card_history(self) -> bool:
        """The card has no history row before this purchase and no approval recorded on this mandate.

        Owner ruling (plan 02 Decisions): such a card gives no basis for device,
        merchant or country familiarity, so those are unknown, never unfamiliar.
        """
        auth = self.event.authorization
        return not self.state.approvals and self.history.card_rows(auth.card_id, auth.timestamp) == 0


@dataclass(frozen=True)
class Observed:
    """One value the rule is compared against. `value is None` means unknown.

    `conflict` marks an unknown that comes from two disagreeing observations of the
    same fact (`PurchaseFacts.conflicts`), which the contract keeps out of an approval.
    """

    value: Any
    source: str
    label: str = ""
    conflict: bool = False


def conflicting(fact: PurchaseFacts, name: str) -> FactConflict | None:
    """The recorded conflict on this fact field, if any."""
    for conflict in fact.conflicts:
        if conflict.field == name:
            return conflict
    return None


def _money_chf(ctx: RuleContext, field: str, raw: float) -> float:
    if field == "authorization.billing_amount_chf":
        return raw
    return raw * FX_TO_CHF[ctx.event.authorization.currency]


def _limit_chf(rule: AnyRule, field: str, ctx: RuleContext) -> float:
    if rule.currency is not None:
        return float(rule.value) * FX_TO_CHF[rule.currency]
    if field == "authorization.billing_amount_chf":
        return float(rule.value)
    return float(rule.value) * FX_TO_CHF[ctx.event.authorization.currency]


def _in_window(ctx: RuleContext, days: int) -> list:
    """Accepted approvals in the trailing `days` of simulated time, this purchase excluded.

    Counts this mandate's approvals and `state.customer_approvals`, the customer's
    accepted approvals on other mandates, so a period limit survives supersession.
    """
    now = ctx.event.authorization.timestamp
    start = now - timedelta(days=days)
    own = ctx.event.authorization.authorization_id
    return [a for a in [*ctx.state.approvals, *ctx.state.customer_approvals]
            if start < a.timestamp <= now and a.authorization_id != own]


def _prior_approvals(ctx: RuleContext) -> list:
    own = ctx.event.authorization.authorization_id
    return [a for a in ctx.state.approvals if a.authorization_id != own]


def check_source(fact_source: str) -> str:
    """A PurchaseFacts source as a Check source: a structured fact comes from the event."""
    return "event" if fact_source == "structured" else fact_source


def _bool_str(value: bool | None) -> str | None:
    return None if value is None else ("true" if value else "false")


def resolve(rule: AnyRule, ctx: RuleContext) -> list[Observed]:
    """Every value the rule must hold for. Cart-line fields give one per line."""
    field = rule.field
    auth = ctx.event.authorization
    period = rule.scope == "period"
    if period and rule.period_days is None:
        raise ValueError(f"period rule on {field!r} has no period_days")

    if field in EVENT_FIELDS:
        value: Any = auth
        for part in EVENT_FIELDS[field]:
            value = getattr(value, part)
        if field in MONEY_FIELDS:
            value = _money_chf(ctx, field, value)
            if period:
                if field != "authorization.billing_amount_chf":
                    raise ValueError(f"period scope is only defined for billing_amount_chf, not {field!r}")
                prior = _in_window(ctx, rule.period_days)
                spent = sum(a.amount_chf for a in prior)
                return [Observed(round(spent + value, 2), "state",
                                 f"CHF {spent:.2f} approved in {rule.period_days} days + CHF {value:.2f} now")]
            return [Observed(round(value, 2), "event")]
        if period:
            raise ValueError(f"period scope is not defined for {field!r}")
        if value in UNKNOWN_EVENT_VALUES:
            value = None
        return [Observed(value, "event")]

    if period and field != "state.approvals_count":
        raise ValueError(f"period scope is not defined for {field!r}")

    if field == "items.category":
        return [Observed(i.item_category, "event", f"line {i.line_no}") for i in auth.items]
    if field == "items.count":
        return [Observed(sum(i.quantity for i in auth.items), "event")]

    if field.startswith("facts."):
        name = field.removeprefix("facts.")
        if name not in FACT_FIELDS:
            raise ValueError(f"unknown facts field {field!r}")
        if ctx.facts is None:
            return [Observed(None, "merchant_text", f"line {i.line_no}, no facts") for i in auth.items]
        by_id = {f.item_id: f for f in ctx.facts}
        out = []
        for item in auth.items:
            fact = by_id.get(item.item_id)
            if fact is None:
                out.append(Observed(None, "merchant_text", f"line {item.line_no}, no facts"))
                continue
            raw = getattr(fact, name)
            value = _bool_str(raw) if isinstance(raw, bool) or name.startswith("is_") else raw
            if value is None:
                conflict = conflicting(fact, name)
                label = f"line {item.line_no}, {conflict.kind.replace('_', ' ')}" if conflict else f"line {item.line_no}"
                out.append(Observed(None, "merchant_text", label, conflict=conflict is not None))
                continue
            if name not in fact.sources:
                raise ValueError(f"facts for {item.item_id} give {name} without a source")
            out.append(Observed(value, check_source(fact.sources[name]), f"line {item.line_no}"))
        return out

    if field.startswith("history.") and ctx.no_card_history:
        return [Observed(None, "history", "no purchase history on this card")]
    if field == "history.merchant_seen_on_card":
        seen = ctx.history.merchant_count(auth.card_id, auth.merchant.merchant_id, auth.timestamp)
        seen += sum(
            1 for r in ctx.event.context.recent_authorizations
            if r.status == "approved" and r.merchant_id == auth.merchant.merchant_id and r.timestamp < auth.timestamp
        )
        return [Observed("true" if seen else "false", "history", f"{seen} earlier approved purchases")]
    if field == "history.device_seen_on_card":
        seen = ctx.history.device_count(auth.card_id, auth.customer_device_id, auth.timestamp)
        return [Observed("true" if seen else "false", "history", f"{seen} earlier approved purchases")]

    if field == "state.approvals_count":
        prior = _in_window(ctx, rule.period_days) if period else _prior_approvals(ctx)
        label = f"in the last {rule.period_days} days" if period else "on this mandate"
        return [Observed(len(prior), "state", f"{len(prior)} approved {label} before this purchase")]

    raise ValueError(f"rule field {field!r} is not in the contract vocabulary")


def _norm(field: str, value: Any) -> Any:
    """Text facts compare case- and space-insensitively; EU shoe sizes drop the prefix."""
    if not isinstance(value, str) or not field.startswith("facts."):
        return value
    text = " ".join(value.split()).lower()
    if field == "facts.size" and text.startswith("eu "):
        text = text[3:]
    return text


def compare(op: str, observed: Any, expected: Any) -> bool:
    if op in NUMERIC_OPS:
        if isinstance(observed, bool) or not isinstance(observed, (int, float)):
            raise ValueError(f"operator {op} needs a number, got {observed!r}")
        if isinstance(expected, bool) or not isinstance(expected, (int, float)):
            raise ValueError(f"operator {op} needs a numeric rule value, got {expected!r}")
        return {"<": observed < expected, "<=": observed <= expected,
                ">": observed > expected, ">=": observed >= expected}[op]
    if op in ("in", "not_in"):
        if not isinstance(expected, list):
            raise ValueError(f"operator {op} needs a list rule value, got {expected!r}")
        hit = observed in expected
        return hit if op == "in" else not hit
    if op in ("=", "!="):
        if isinstance(expected, list):
            raise ValueError(f"operator {op} needs a single rule value, got a list")
        if isinstance(observed, (int, float)) and isinstance(expected, (int, float)):
            equal = observed == expected
        else:
            equal = str(observed) == str(expected)
        return equal if op == "=" else not equal
    raise ValueError(f"unknown operator {op!r}")


def _expected(rule: AnyRule, ctx: RuleContext) -> Any:
    if rule.field in MONEY_FIELDS:
        return round(_limit_chf(rule, rule.field, ctx), 2)
    if isinstance(rule.value, list):
        return [_norm(rule.field, v) for v in rule.value]
    return _norm(rule.field, rule.value)


def rule_name(rule: AnyRule) -> str:
    scope = f" over {rule.period_days} days" if rule.scope == "period" else ""
    cur = f" {rule.currency}" if rule.currency else ""
    return f"rule {rule.field} {rule.operator} {rule.value}{cur}{scope}"


def evaluate_rule(rule: AnyRule, ctx: RuleContext) -> Check:
    """One rule against one purchase. Every cart line must satisfy a line rule."""
    observed = resolve(rule, ctx)
    expected = _expected(rule, ctx)
    failed, unknown = [], []
    for obs in observed:
        if obs.value is None:
            unknown.append(obs)
        elif not compare(rule.operator, _norm(rule.field, obs.value), expected):
            failed.append(obs)
    result = "fail" if failed else ("uncertain" if unknown else "pass")
    shown = failed or unknown or observed
    if result == "uncertain" and any(o.conflict for o in unknown):
        shown = [o for o in unknown if o.conflict] + [o for o in unknown if not o.conflict]
    values = [o.value for o in shown]
    value: Any = values[0] if len(values) == 1 else ", ".join("unknown" if v is None else str(v) for v in values)
    details = "; ".join(f"{o.label}: {'unknown' if o.value is None else o.value}" if o.label
                        else ('unknown' if o.value is None else str(o.value)) for o in shown)
    plain = getattr(rule, "plain_english", None)
    note = f"{plain} Observed {details}." if plain else f"Observed {details}."
    if result == "uncertain" and any(o.conflict for o in unknown):
        note += " The merchant's own statements disagree on this, so it counts as unknown by contradiction."
    return Check(name=rule_name(rule), result=result, value=value, source=shown[0].source, note=note)


def conflicted(rule: AnyRule, ctx: RuleContext) -> bool:
    """Whether this rule reads a fact field that some cart line marks as conflicting."""
    if not rule.field.startswith("facts.") or ctx.facts is None:
        return False
    name = rule.field.removeprefix("facts.")
    return any(conflicting(f, name) is not None for f in ctx.facts)


def evaluate_rules(rules: list[AnyRule], ctx: RuleContext) -> list[Check]:
    return [evaluate_rule(rule, ctx) for rule in rules]


REASON_BY_FIELD = {
    "authorization.billing_amount_chf": "amount_over_limit",
    "authorization.items_subtotal": "amount_over_limit",
    "authorization.delivery_fee": "amount_over_limit",
    "authorization.order_returnable": "return_terms_short",
    "authorization.merchant.merchant_id": "merchant_type_mismatch",
    "authorization.merchant.merchant_category": "merchant_type_mismatch",
    "authorization.merchant.merchant_mcc": "merchant_type_mismatch",
    "authorization.merchant.merchant_country": "country_blocked",
    "items.category": "item_mismatch",
    "items.count": "item_mismatch",
    "facts.product_type": "item_mismatch",
    "facts.size": "item_mismatch",
    "facts.return_days": "return_terms_short",
    "facts.is_gift_card": "gift_card",
    "facts.is_subscription": "subscription",
    "facts.is_protection_plan": "protection_plan",
    "facts.is_addon": "unrequested_item",
    "history.merchant_seen_on_card": "unfamiliar_merchant",
    "history.device_seen_on_card": "new_device",
    "state.approvals_count": "purchase_count_exceeded",
}


def reason_code(rule: AnyRule, check: Check) -> str | None:
    """The reason code a non-passing rule contributes, or None when it passed."""
    if check.result == "pass":
        return None
    if rule.scope == "period" and rule.field in MONEY_FIELDS:
        return "period_limit_exceeded"
    if check.result == "uncertain" and rule.field in ("facts.return_days", "authorization.order_returnable"):
        return "return_terms_missing"
    if check.result == "uncertain" and rule.field.startswith("history."):
        return "no_card_history"
    code = REASON_BY_FIELD.get(rule.field)
    if code is None:
        raise ValueError(f"no reason code for rule field {rule.field!r}")
    return code
