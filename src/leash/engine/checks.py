"""Built-in checks beyond the customer's rules, one small function each.

Every function is pure and returns one Check plus the reason code it
contributes when it does not pass. The order in CHECKS is plan 02 step 4.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import timedelta

from leash.contracts import Check, PurchaseFacts

from .rules import RuleContext, check_source

VELOCITY_LIMIT = 2  # attempts in the previous 10 minutes that make a session uncertain
LOOKALIKE_RATIO = 0.85
DUPLICATE_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class Result:
    check: Check
    code: str | None  # reason code when the check did not pass


def _ok(name: str, value, source: str, note: str) -> Result:
    return Result(Check(name=name, result="pass", value=value, source=source, note=note), None)


def _bad(name: str, result: str, value, source: str, note: str, code: str) -> Result:
    return Result(Check(name=name, result=result, value=value, source=source, note=note), code)


def _facts_by_line(ctx: RuleContext) -> list[tuple[int, str, PurchaseFacts | None]]:
    by_id = {} if ctx.facts is None else {f.item_id: f for f in ctx.facts}
    return [(i.line_no, i.item_name, by_id.get(i.item_id)) for i in ctx.event.authorization.items]


def mandate_active(ctx: RuleContext) -> Result:
    auth, mandate = ctx.event.authorization, ctx.event.mandate
    status = mandate.status if mandate.status != "active" else auth.authority_status
    if status == "active":
        return _ok("mandate active", status, "event", "The mandate and the agent's authority are active.")
    code = "mandate_expired" if status == "expired" else "mandate_revoked"
    return _bad("mandate active", "fail", status, "event", f"The mandate is {status}.", code)


def cart_lines(ctx: RuleContext) -> Result:
    """Each line matches the requested item, and no line is outside the basket's purpose."""
    auth = ctx.event.authorization
    for line_no, name, fact in _facts_by_line(ctx):
        if fact is not None and fact.matches_request is False:
            return _bad("cart lines", "fail", name, check_source(fact.sources["matches_request"]),
                        f"Line {line_no} ({name}) is not the requested item.", "item_mismatch")
    categories = [i.item_category for i in auth.items]
    main = auth.merchant.merchant_category
    if main not in categories:
        main = max(auth.items, key=lambda i: i.unit_price * i.quantity).item_category
    off = [i for i in auth.items if i.item_category != main]
    if off:
        names = ", ".join(f"line {i.line_no} {i.item_name} ({i.item_category})" for i in off)
        return _bad("cart lines", "fail", names, "event",
                    f"The basket is {main}, but it also holds {names}.", "unrequested_item")
    return _ok("cart lines", main, "event", f"Every line is {main}.")


def addons(ctx: RuleContext) -> Result:
    for line_no, name, fact in _facts_by_line(ctx):
        if fact is not None and fact.is_addon:
            return _bad("add-ons", "fail", name, check_source(fact.sources["is_addon"]),
                        f"Line {line_no} ({name}) is an add-on the customer did not ask for.", "unrequested_item")
    return _ok("add-ons", None, "merchant_text", "No add-on line was detected.")


def return_terms(ctx: RuleContext) -> Result:
    """Reported for the evidence. A return requirement is enforced by the customer's rules."""
    auth = ctx.event.authorization
    days = [f.return_days for _, _, f in _facts_by_line(ctx) if f is not None]
    shown = ", ".join("unknown" if d is None else f"{d} days" for d in days) or "no facts"
    return _ok("return terms", auth.order_returnable, "event",
               f"Order returnable: {auth.order_returnable}; stated return window: {shown}.")


def merchant_type(ctx: RuleContext) -> Result:
    auth = ctx.event.authorization
    category = auth.merchant.merchant_category
    if any(i.item_category == category for i in auth.items):
        return _ok("merchant type", category, "event", f"The shop is {category} and sells this basket.")
    cats = ", ".join(sorted({i.item_category for i in auth.items}))
    return _bad("merchant type", "uncertain", category, "event",
                f"The shop is {category}, but the basket is {cats}.", "merchant_type_mismatch")


def _merchant_seen(ctx: RuleContext) -> int:
    auth = ctx.event.authorization
    mid = auth.merchant.merchant_id
    seen = ctx.history.merchant_count(auth.card_id, mid, auth.timestamp)
    seen += sum(1 for a in ctx.state.approvals if a.merchant_id == mid and a.timestamp < auth.timestamp)
    return seen


def familiarity(ctx: RuleContext) -> Result:
    """Device and merchant familiarity from the card's history.

    Owner ruling (plan 02 Decisions): an unseen merchant fails only through a
    customer rule that requires prior use (history.merchant_seen_on_card). This
    check never fails; an unseen device or merchant makes it uncertain.
    """
    auth = ctx.event.authorization
    devices = ctx.history.device_count(auth.card_id, auth.customer_device_id, auth.timestamp)
    if devices == 0:
        return _bad("familiarity", "uncertain", auth.customer_device_id, "history",
                    f"Device {auth.customer_device_id} has never made an approved purchase on this card.",
                    "new_device")
    merchants = _merchant_seen(ctx)
    if merchants == 0:
        return _bad("familiarity", "uncertain", auth.merchant.merchant_name, "history",
                    f"This card has never bought from {auth.merchant.merchant_name}.", "unfamiliar_merchant")
    return _ok("familiarity", merchants, "history",
               f"{auth.merchant.merchant_name} has {merchants} earlier approved purchases on this card; "
               f"the device is known ({devices} purchases).")


def velocity(ctx: RuleContext) -> Result:
    count = ctx.event.authorization.recent_attempt_count_10m
    if count >= VELOCITY_LIMIT:
        return _bad("velocity", "uncertain", count, "event",
                    f"{count} other attempts in the last 10 minutes.", "velocity")
    return _ok("velocity", count, "event", f"{count} other attempts in the last 10 minutes.")


def country(ctx: RuleContext) -> Result:
    auth = ctx.event.authorization
    code = auth.merchant.merchant_country
    seen = ctx.history.country_count(auth.card_id, code, auth.timestamp)
    if seen == 0:
        return _bad("country", "uncertain", code, "history",
                    f"This card has never bought from a shop in {code}.", "country_blocked")
    return _ok("country", code, "history", f"{seen} earlier approved purchases in {code}.")


def duplicate(ctx: RuleContext) -> Result:
    auth = ctx.event.authorization
    mid, amount, now = auth.merchant.merchant_id, auth.billing_amount_chf, auth.timestamp
    earlier = [(a.authorization_id, "approved") for a in ctx.state.approvals
               if a.merchant_id == mid and a.amount_chf == amount and now - DUPLICATE_WINDOW <= a.timestamp < now]
    earlier += [(r.authorization_id, r.status) for r in ctx.event.context.recent_authorizations
                if r.merchant_id == mid and r.billing_amount_chf == amount and r.status in ("approved", "pending")
                and r.authorization_id != auth.authorization_id and r.timestamp < now]
    if earlier:
        other, status = earlier[0]
        return _bad("duplicate and re-quote", "fail", other, "state",
                    f"The same CHF {amount:.2f} order at {auth.merchant.merchant_name} is already {status} ({other}).",
                    "duplicate_order")
    related, status = auth.related_authorization_id, auth.related_authorization_status
    if related is not None and status == "declined":
        prior = next((r for r in ctx.event.context.recent_authorizations if r.authorization_id == related), None)
        if prior is not None and prior.billing_amount_chf == amount and prior.merchant_id == mid:
            return _bad("duplicate and re-quote", "fail", related, "event",
                        f"This repeats the declined order {related} unchanged.", "requote_after_decline")
        return _ok("duplicate and re-quote", related, "event",
                   f"A new quote after {related} was declined; judged on its own facts.")
    return _ok("duplicate and re-quote", None, "state", "No matching earlier order.")


def _flag(ctx: RuleContext, name: str, attr: str, categories: set[str], code: str, label: str) -> Result:
    for item in ctx.event.authorization.items:
        if item.item_category in categories:
            return _bad(name, "fail", item.item_name, "event",
                        f"Line {item.line_no} ({item.item_name}) is a {label}.", code)
    for line_no, item_name, fact in _facts_by_line(ctx):
        if fact is not None and getattr(fact, attr):
            return _bad(name, "fail", item_name, check_source(fact.sources[attr]),
                        f"Line {line_no} ({item_name}) is a {label}.", code)
    return _ok(name, None, "merchant_text", f"No {label} detected.")


def gift_card(ctx: RuleContext) -> Result:
    return _flag(ctx, "gift card", "is_gift_card", {"gift_card"}, "gift_card", "gift card or voucher")


def subscription(ctx: RuleContext) -> Result:
    return _flag(ctx, "subscription", "is_subscription", {"subscriptions"}, "subscription", "subscription")


def protection_plan(ctx: RuleContext) -> Result:
    return _flag(ctx, "protection plan", "is_protection_plan", set(), "protection_plan", "protection plan")


def _normal(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def lookalike(ctx: RuleContext) -> Result:
    auth = ctx.event.authorization
    here = _normal(auth.merchant.merchant_name)
    known = ctx.history.known_merchants(auth.card_id, auth.timestamp)
    for mid, name in known.items():
        if mid == auth.merchant.merchant_id:
            continue
        ratio = difflib.SequenceMatcher(None, here, _normal(name)).ratio()
        if ratio >= LOOKALIKE_RATIO:
            return _bad("lookalike merchant", "fail", auth.merchant.merchant_name, "history",
                        f"{auth.merchant.merchant_name} ({auth.merchant.merchant_id}) imitates {name} ({mid}), "
                        f"a shop this card has used.", "lookalike_merchant")
    return _ok("lookalike merchant", auth.merchant.merchant_name, "history",
               "The shop's name does not imitate a shop this card has used.")


def injected(ctx: RuleContext) -> Result:
    for line_no, item_name, fact in _facts_by_line(ctx):
        if fact is not None and fact.contains_instructions:
            return _bad("injected instructions", "uncertain", fact.excerpt, "merchant_text",
                        f"Line {line_no} ({item_name}) carries text addressed to the agent; it was ignored and "
                        f"that line's facts count as unknown.", "injected_instructions")
    return _ok("injected instructions", None, "merchant_text", "No instructions found in merchant text.")


CHECKS = (
    cart_lines, addons, return_terms, merchant_type, familiarity, velocity, country,
    duplicate, gift_card, subscription, protection_plan, lookalike, injected,
)
