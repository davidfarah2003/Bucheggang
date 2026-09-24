"""Deterministic first pass over the simulator's cart lines."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_RETURN_PATTERNS = (
    re.compile(r"\breturns?\s+accepted\s+within\s+(\d{1,3})\s+days?\b", re.I),
    re.compile(r"\b(\d{1,3})[ -]day\s+returns?\b", re.I),
    re.compile(r"\breturns?\s+(?:within|for)\s+(\d{1,3})\s+days?\b", re.I),
)
_NO_RETURNS = re.compile(r"\b(?:no returns?|non[ -]returnable|final sale)\b", re.I)
_SIZE = re.compile(r"\bsize\s+(?:EU\s*)?([A-Z]{1,3}|\d{1,3}(?:\.\d)?)\b", re.I)
_EU_SIZE = re.compile(r"\bEU\s*(\d{2}(?:\.\d)?)\b", re.I)
_UK_SIZE = re.compile(r"\bUK\s*(\d{1,2}(?:\.\d)?)\b", re.I)
_INSTRUCTIONS = re.compile(
    r"\b(?:ignore (?:any |all |the |previous )*instructions?|"
    r"approve (?:this|the|without)|"
    r"(?:customer|cardholder) (?:has |already )?(?:agreed|confirmed|pre[ -]?authori[sz]ed)|"
    r"(?:spending|per[ -]order) limits? (?:do not|don't|does not)|"
    r"(?:note for|attention) (?:automated|ai) (?:purchasing )?agents?|"
    r"(?:system|developer|assistant)\s*:|"
    r"as authori[sz]ed by)(?:\b|(?<=:))",
    re.I,
)
_GIFT = re.compile(r"\b(?:gift\s*(?:card|voucher)|store credit voucher)\b", re.I)
_PLAN = re.compile(
    r"\b(?:protection plan|extended (?:cover|warranty)|warranty extension|"
    r"(?:extending|extended|extra) cover beyond|coverage (?:extending |lasting )?beyond)\b",
    re.I,
)
_SUBSCRIPTION = re.compile(r"\b(?:subscription|billed (?:monthly|annually)|monthly fee)\b", re.I)
_ADDON = re.compile(r"\b(?:add[ -]?on|optional (?:service|cover|plan))\b", re.I)


def _product_type(name: str) -> str | None:
    """Map a named item to a concise type without inferring from shop prose."""
    value = name.strip().lower()
    if not value:
        return None
    if "road-running shoe" in value:
        return "road-running shoes"
    if "trail-running shoe" in value:
        return "trail-running shoes"
    if "monitor" in value:
        match = re.search(r"\b(\d{2})[ -]inch\b", value)
        return f"{match.group(1)}-inch monitor" if match else "monitor"
    return value


def _return_days(copy: str) -> int | None:
    values = {int(m.group(1)) for pattern in _RETURN_PATTERNS for m in pattern.finditer(copy)}
    if _NO_RETURNS.search(copy):
        values.add(0)
    return next(iter(values)) if len(values) == 1 else None


def _size(copy: str) -> str | None:
    values = {m.group(1).upper() for m in _SIZE.finditer(copy)}
    if not values:
        values.update(f"EU {m.group(1)}" for m in _EU_SIZE.finditer(copy))
    if not values:
        values.update(f"UK {m.group(1)}" for m in _UK_SIZE.finditer(copy))
    return next(iter(values)) if len(values) == 1 else None


def extract_item(
    item: Mapping[str, Any],
    *,
    catalogue: Mapping[str, Mapping[str, Any]] | None = None,
    requested: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Extract one cart line; `catalogue` is trusted local reference data.

    `requested` is a short structured target, never a raw policy instruction.
    A missing or conflicting claim remains unknown. This function performs no
    network access and makes no purchase recommendation.
    """
    item_id = str(item.get("item_id", ""))
    reference = catalogue.get(item_id) if catalogue else None
    name = str(reference.get("item_name", "")) if reference else str(item.get("item_name", ""))
    category = str(reference.get("item_category", "")) if reference else str(item.get("item_category", ""))
    copy = str(item.get("item_details", ""))
    title = str(item.get("item_name", ""))
    text = f"{title}. {copy}"
    sources: dict[str, str] = {}

    product_type = _product_type(name)
    if product_type is not None:
        sources["product_type"] = "structured" if reference else "merchant_text"

    size = _size(copy)
    if size is not None:
        sources["size"] = "merchant_text"

    return_days = _return_days(copy)
    if return_days is not None:
        sources["return_days"] = "merchant_text"

    # Positive flags may come from the trusted catalogue category or text.
    # An absent phrase alone cannot prove a negative.
    is_gift_card = True if category == "gift_card" or _GIFT.search(text) else None
    is_subscription = True if category == "subscriptions" or _SUBSCRIPTION.search(text) else None
    is_protection_plan = True if _PLAN.search(text) else None
    is_addon = True if _ADDON.search(text) or is_protection_plan else None
    for field, value, structured in (
        ("is_gift_card", is_gift_card, category == "gift_card"),
        ("is_subscription", is_subscription, category == "subscriptions"),
        ("is_protection_plan", is_protection_plan, False),
        ("is_addon", is_addon, False),
    ):
        if value is not None:
            sources[field] = "structured" if structured else "merchant_text"

    match = _INSTRUCTIONS.search(text)
    excerpt = None
    if match:
        excerpt = text[max(0, match.start() - 35) : min(len(text), match.end() + 90)].strip()

    matches_request = None
    if requested and product_type is not None:
        target = _product_type(str(requested.get("product_type", "")))
        if target:
            matches_request = product_type == target
            requested_size = requested.get("size")
            if matches_request and requested_size is not None:
                matches_request = None if size is None else size == str(requested_size).upper()
            sources["matches_request"] = sources["product_type"]

    return {
        "item_id": item_id,
        "product_type": product_type,
        "size": size,
        "return_days": return_days,
        "is_addon": is_addon,
        "is_gift_card": is_gift_card,
        "is_subscription": is_subscription,
        "is_protection_plan": is_protection_plan,
        "matches_request": matches_request,
        "contains_instructions": bool(match),
        "excerpt": excerpt,
        "sources": sources,
    }


def extract_event(
    event: Mapping[str, Any],
    *,
    catalogue: Mapping[str, Mapping[str, Any]] | None = None,
    requested: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Extract each line of an authorization event in cart order."""
    authorization = event.get("authorization", {})
    return [
        extract_item(item, catalogue=catalogue, requested=requested)
        for item in authorization.get("items", [])
    ]
