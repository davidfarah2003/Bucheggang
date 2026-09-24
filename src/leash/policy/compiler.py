"""Compile a trusted cardholder instruction into a reviewable draft proposal.

The caller chooses a deterministic or model-supplied proposal before execution.
The model returns data into this module. It cannot confirm a policy.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .store import FIELDS, DraftStore, InvalidDraft


_AMOUNT = re.compile(
    r"\b(?:(?:at or below|up to|no more than)\s+CHF\s*(\d+(?:\.\d{1,2})?)|"
    r"CHF\s*(\d+(?:\.\d{1,2})?)\s+or\s+less)\b",
    re.I,
)
_PERIOD = re.compile(
    r"\btotal\s+across\s+any\s+(seven|\d+)\s+days?\s+at\s+or\s+below\s+CHF\s*(\d+(?:\.\d{1,2})?)\b",
    re.I,
)
_SIZE = re.compile(r"\bsize\s+(\d{1,3}(?:\.\d)?)\b", re.I)
_RETURNS = re.compile(r"\breturned\s+within\s+(\d{1,3})\s+days?\s+or\s+more\b", re.I)
_FAMILIAR = re.compile(
    r"\b(?:shops?\s+I\s+(?:use\s+regularly|have\s+used\s+before)|"
    r"seller\s+I\s+have\s+bought\s+from\s+before)\b",
    re.I,
)
_SPECIALIST = re.compile(r"\bspecialist\s+sports\s+retailer\b", re.I)
_SHOES = re.compile(r"\broad[ -]running\s+shoes?\b", re.I)
_MONITOR = re.compile(r"\b(\d{2})[ -]inch\s+monitor\b", re.I)
_GROCERY = re.compile(r"\bgrocer(?:y|ies)\b", re.I)
_CLOTHING = re.compile(r"\bclothing\b", re.I)
_ONE_ITEM = re.compile(r"\bone\s+(?:ordinary\s+)?(?:grocery\s+)?item\b", re.I)
_REPLACE = re.compile(r"\breplace\s+my\s+[^.]+", re.I)
_CHOSEN_MONITOR = re.compile(r"\bbuy\s+the\s+\d{2}[ -]inch\s+monitor\s+I\s+chose\b", re.I)
_NO_ADDONS = re.compile(r"\bdo\s+not\s+add\s+anything\s+I\s+did\s+not\s+ask\s+for\b", re.I)
_ASK = re.compile(r"\bask\s+me\s+when\s+uncertain\b", re.I)


def extractor_prompt(instruction: str) -> str:
    """Instructions for the cardholder-side model; this package makes no model call."""
    if not isinstance(instruction, str) or not instruction.strip():
        raise InvalidDraft("instruction is required")
    vocabulary = ", ".join(sorted(FIELDS))
    return (
        "Read the cardholder's instruction as the only source of policy authority. "
        "Return one JSON object with exactly four keys: rules, examples, open_questions, "
        "uncertainty_policy. No markdown or extra keys. Each rule has field, operator, value, "
        "source_text and plain_english; currency, scope and period_days are optional. "
        "source_text must be an exact substring of the instruction. Use only these fields: "
        f"{vocabulary}. Rule values are a number, a string or a list of strings, never a boolean. "
        "Numeric fields are authorization.billing_amount_chf, authorization.items_subtotal, "
        "authorization.delivery_fee, items.count, facts.return_days, and state.approvals_count. "
        "Risk flags and history fields use the strings true and false. All other fields use strings. "
        "Use scope period and period_days only for a supported cumulative amount rule. "
        "Examples should include a clearly allowed purchase, a forbidden purchase, and an unknown-fact case. "
        "A broad merchant category does not establish that a retailer is a specialist. A screen size "
        "does not identify a selected model. Surface these as open questions and require an enforceable "
        "merchant or product identifier, or the cardholder's explicit consent to broader permissions. "
        "When a meaning is unclear, add an open question; do not invent permission. "
        "Each example has description, expected and why. Each open question has question, "
        "options and answer (null until the cardholder answers). "
        "uncertainty_policy is ask, decline or approve, and must follow the customer's wording.\n\n"
        f"Cardholder instruction: {json.dumps(instruction, ensure_ascii=False)}"
    )


def _rule(
    field: str,
    operator: str,
    value: int | float | str,
    source_text: str,
    plain_english: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "field": field,
        "operator": operator,
        "value": value,
        "source_text": source_text,
        "plain_english": plain_english,
        "scope": "purchase",
        **extra,
    }


def compile_instruction(instruction: str) -> dict[str, Any]:
    """Produce conservative rules for common phrases without scenario IDs.

    It returns an incomplete proposal where words need a human interpretation.
    The caller must display the result and obtain customer confirmation.
    """
    if not isinstance(instruction, str) or not instruction.strip():
        raise InvalidDraft("instruction is required")
    rules: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []

    def add(rule: dict[str, Any]) -> None:
        if not any(existing["field"] == rule["field"] and existing["scope"] == rule["scope"] for existing in rules):
            rules.append(rule)

    period_spans: list[tuple[int, int]] = []
    for match in _PERIOD.finditer(instruction):
        days = 7 if match.group(1).lower() == "seven" else int(match.group(1))
        amount = float(match.group(2)) if "." in match.group(2) else int(match.group(2))
        rules.append(
            _rule(
                "authorization.billing_amount_chf",
                "<=",
                amount,
                match.group(0),
                f"Approved spending in any trailing {days} days, including this order, must not exceed CHF {amount}.",
                currency="CHF",
                scope="period",
                period_days=days,
            )
        )
        period_spans.append(match.span())

    for match in _AMOUNT.finditer(instruction):
        if any(start <= match.start() < end for start, end in period_spans):
            continue
        amount_text = match.group(1) or match.group(2)
        amount = float(amount_text) if "." in amount_text else int(amount_text)
        add(
            _rule(
                "authorization.billing_amount_chf",
                "<=",
                amount,
                match.group(0),
                f"The total charge must be CHF {amount} or less.",
                currency="CHF",
            )
        )

    for pattern, field, value, explanation in (
        (_GROCERY, "items.category", "groceries", "Every cart line must be a grocery item."),
        (_CLOTHING, "items.category", "clothing", "Every cart line must be clothing."),
        (_SHOES, "facts.product_type", "road-running shoes", "The item must be road-running shoes."),
        (_SPECIALIST, "authorization.merchant.merchant_category", "sporting_goods", "The seller must be a sporting goods retailer."),
        (_FAMILIAR, "history.merchant_seen_on_card", "true", "The card must have approved purchases from this seller before."),
    ):
        match = pattern.search(instruction)
        if match:
            add(_rule(field, "=", value, match.group(0), explanation))

    monitor = _MONITOR.search(instruction)
    if monitor:
        add(
            _rule(
                "facts.product_type",
                "=",
                f"{monitor.group(1)}-inch monitor",
                monitor.group(0),
                f"The item must be the requested {monitor.group(1)}-inch monitor.",
            )
        )
        questions.append(
            {
                "question": "Which exact monitor did you choose? A screen size alone cannot identify it, and no purchase can be confirmed until a supported identifier is added to the rules.",
                "options": ["I will provide the exact model", "Ask me for each purchase"],
                "answer": None,
            }
        )

    size = _SIZE.search(instruction)
    if size:
        add(_rule("facts.size", "=", size.group(1), size.group(0), f"The item must be size {size.group(1)}."))

    returns = _RETURNS.search(instruction)
    if returns:
        days = int(returns.group(1))
        add(
            _rule(
                "facts.return_days",
                ">=",
                days,
                returns.group(0),
                f"The seller must state a return period of at least {days} days.",
            )
        )
        questions.append(
            {
                "question": "If a seller does not state its return period, should we ask you or decline?",
                "options": ["ask", "decline"],
                "answer": None,
            }
        )

    specialist = _SPECIALIST.search(instruction)
    if specialist:
        questions.append(
            {
                "question": "May any sporting goods retailer qualify, including general sellers, or must a supported merchant identifier be added before confirmation?",
                "options": ["Allow any sporting goods retailer", "I will provide a merchant", "Ask me for each purchase"],
                "answer": None,
            }
        )

    one_item = _ONE_ITEM.search(instruction)
    no_addons = _NO_ADDONS.search(instruction)
    if one_item or no_addons:
        source = one_item or no_addons
        add(_rule("items.count", "<=", 1, source.group(0), "The cart may contain only the requested item."))

    replacement = _REPLACE.search(instruction)
    chosen_monitor = _CHOSEN_MONITOR.search(instruction)
    if replacement or chosen_monitor:
        source = replacement or chosen_monitor
        add(_rule("state.approvals_count", "<", 1, source.group(0), "Only one successful purchase may fulfil this request."))

    if "someone other than me is driving the session" in instruction.lower():
        questions.append(
            {
                "question": "Which session changes should always pause a purchase?",
                "options": ["New device", "Unusual velocity", "Either signal"],
                "answer": None,
            }
        )

    if not rules:
        raise InvalidDraft("no supported restriction could be extracted; ask the customer to clarify")
    return {
        "rules": rules,
        "examples": [],
        "open_questions": questions,
        "uncertainty_policy": "ask" if _ASK.search(instruction) else "decline",
    }


def propose_task_policy(
    instruction: str,
    store: DraftStore,
    *,
    mode: str,
    model_json: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Use the selected method; missing or invalid model output raises."""
    if mode == "deterministic":
        if model_json is not None:
            raise InvalidDraft("model output is not accepted in deterministic mode")
        proposal = compile_instruction(instruction)
    elif mode == "model":
        if model_json is None:
            raise InvalidDraft("model output is required in model mode")
        try:
            proposal = json.loads(model_json) if isinstance(model_json, str) else model_json
        except json.JSONDecodeError as exc:
            raise InvalidDraft("model returned invalid JSON") from exc
        if not isinstance(proposal, dict) or set(proposal) != {
            "rules", "examples", "open_questions", "uncertainty_policy"
        }:
            raise InvalidDraft("model output must contain exactly the four agreed fields")
    else:
        raise InvalidDraft("mode must be deterministic or model")
    return store.create(instruction, **proposal)
