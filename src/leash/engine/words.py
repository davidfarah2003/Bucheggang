"""Customer message and judge-panel explanation, in the customer's own terms.

Each non-passing rule is phrased against the words the customer used
(`source_text`) and the value observed on this purchase. Built-in checks
already carry a readable note.
"""

from __future__ import annotations

from dataclasses import dataclass

from leash.contracts import Check, Event, Rule

MONEY = frozenset({"authorization.billing_amount_chf", "authorization.items_subtotal", "authorization.delivery_fee"})


@dataclass(frozen=True)
class Finding:
    check: Check
    rule: object | None  # Rule or MandateRule for rule checks, None for built-in checks


def _chf(x) -> str:
    return f"CHF {float(x):,.2f}".replace(",", "'")


def _limit(rule) -> str:
    unit = rule.currency or "CHF"
    value = rule.value
    return f"{unit} {value:g}" if isinstance(value, (int, float)) else str(value)


def _said(rule) -> str:
    text = getattr(rule, "source_text", None)
    return f'You said "{text}"' if text else f"Your rule is {rule.field} {rule.operator} {rule.value}"


def _observed(rule, check: Check, event: Event) -> str:
    """What this purchase shows for the rule's field, as a clause."""
    auth = event.authorization
    field, value, unknown = rule.field, check.value, check.result == "uncertain"
    if field in MONEY:
        if rule.scope == "period":
            return (f"this {_chf(auth.billing_amount_chf)} order would bring your spending over the last "
                    f"{rule.period_days} days to {_chf(value)}, over your {_limit(rule)} limit")
        what = {"authorization.billing_amount_chf": "this order is",
                "authorization.items_subtotal": "the items come to",
                "authorization.delivery_fee": "delivery is"}[field]
        if check.result != "fail":
            return f"{what} {_chf(value)}"
        side = "over" if rule.operator in ("<", "<=") else "under"
        return f"{what} {_chf(value)}, {side} your {_limit(rule)} limit"
    if field == "state.approvals_count":
        n = int(value)
        return f"you already have {n} approved purchase{'s' if n != 1 else ''} under this instruction"
    if field.startswith("history.") and unknown:
        return "this card has no purchase history yet, so we cannot tell"
    if field == "history.merchant_seen_on_card":
        return f"you have never bought from {auth.merchant.merchant_name} with this card"
    if field == "history.device_seen_on_card":
        return f"the purchase comes from a device ({auth.customer_device_id}) this card has not used before"
    if field == "authorization.merchant.merchant_category":
        return f"{auth.merchant.merchant_name} is listed as {str(value).replace('_', ' ')}"
    if field == "authorization.merchant.merchant_country":
        return f"{auth.merchant.merchant_name} is in {value}"
    if field in ("authorization.merchant.merchant_id", "authorization.merchant.merchant_mcc"):
        return f"the shop is {auth.merchant.merchant_name}"
    if field == "authorization.order_returnable":
        return "the shop does not say whether the order can be returned" if unknown else f"returnable is {value}"
    if field == "facts.return_days":
        if unknown:
            return "the seller does not state a return window"
        return "the seller does not accept returns" if value == 0 else f"the seller only accepts returns for {value} days"
    if field == "facts.size":
        return "the size is not stated" if unknown else f"the item is size {value}"
    if field == "facts.product_type":
        return "we could not tell what the item is" if unknown else f"the cart holds {value}"
    if field == "items.category":
        return f"the cart holds {str(value).replace('_', ' ')}"
    if field == "items.count":
        return f"the cart holds {value} items"
    if field.startswith("facts.is_"):
        kind = field.removeprefix("facts.is_").replace("_", " ")
        return f"we could not tell whether a line is a {kind}" if unknown else f"a line is a {kind}"
    return "this value is unknown" if unknown else f"this purchase shows {value}"


def phrase(finding: Finding, event: Event) -> str:
    check, rule = finding.check, finding.rule
    if rule is None:
        return check.note
    return f"{_said(rule)}, and {_observed(rule, check, event)}."


def compose(outcome: str, findings: list[Finding], policy_mode: str, event: Event,
            global_note: str = "") -> tuple[str, str]:
    """(customer_message, explanation)."""
    auth = event.authorization
    where = f"{_chf(auth.billing_amount_chf)} at {auth.merchant.merchant_name}"
    fails = [f for f in findings if f.check.result == "fail"]
    unsure = [f for f in findings if f.check.result == "uncertain"]
    passed = sum(1 for f in findings if f.check.result == "pass")
    rules = [f for f in findings if f.rule is not None]

    if outcome == "decline" and fails:
        head = f"Declined {where}. {phrase(fails[0], event)}"
        more = f" {len(fails) - 1} other condition{'s' if len(fails) > 2 else ''} also failed." if len(fails) > 1 else ""
        message = head + more
    elif outcome == "decline":
        message = (f"Declined {where}, because something could not be checked and you asked us to decline "
                   f"when unsure. {phrase(unsure[0], event)}")
    elif outcome == "step_up":
        message = f"Please confirm {where}. {phrase(unsure[0], event)}"
    elif unsure:
        message = (f"Approved {where}. One point could not be checked, and you asked us to approve when unsure: "
                   f"{phrase(unsure[0], event)}")
    else:
        message = f"Approved {where}: it meets everything you asked for."

    parts = [f"Decision: {outcome}. The agent asked to pay {where} "
             f"({', '.join(i.item_name for i in auth.items)})."]
    if fails:
        parts.append("Failed: " + " ".join(phrase(f, event) for f in fails))
    if unsure:
        parts.append("Could not be checked: " + " ".join(phrase(f, event) for f in unsure))
        if not fails:
            parts.append(f"The mandate's uncertainty setting is '{policy_mode}', so uncertain checks lead to "
                         f"{ {'ask': 'asking the customer', 'decline': 'a decline', 'approve': 'an approval'}[policy_mode]}.")
    parts.append(f"{passed} of {len(findings)} checks passed, including "
                 f"{sum(1 for f in rules if f.check.result == 'pass')} of {len(rules)} customer rules.")
    if global_note:
        parts.append(global_note)
    return message, " ".join(parts)
