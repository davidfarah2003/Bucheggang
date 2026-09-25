"""Deterministic extraction over the simulator's cart lines."""

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
_RETURNS_UNSTATED = re.compile(r"\breturn policy not stated\b", re.I)
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
_SUBSCRIPTION = re.compile(
    r"\b(?:subscription|billed (?:weekly|monthly|annually|yearly|every)|(?:weekly|monthly|annual) fee|"
    r"renews? automatically|auto[ -]?renew(?:s|al|ing)?|"
    r"recurring (?:(?:weekly|monthly|annual|yearly) )?(?:charge|payment|billing)|"
    r"until cancell?ed|standing (?:\w+ )?order)\b",
    re.I,
)
_ADDON = re.compile(r"\b(?:add[ -]?on|optional (?:service|cover|plan))\b", re.I)


def _product_type(name: str) -> str | None:
    """Normalize a structured item name the same way for every category.

    No category gets its own vocabulary, and nothing is inferred from shop
    prose. A request matches only on an equal normalized name.
    """
    value = " ".join(name.split()).lower()
    return value or None


def _return_days(copy: str) -> tuple[int | None, bool, bool]:
    values = {int(m.group(1)) for pattern in _RETURN_PATTERNS for m in pattern.finditer(copy)}
    if _NO_RETURNS.search(copy):
        values.add(0)
    observed = bool(values) or bool(_RETURNS_UNSTATED.search(copy))
    return (next(iter(values)) if len(values) == 1 else None), observed, len(values) > 1


def _size(copy: str) -> tuple[str | None, bool]:
    values = {m.group(1).upper() for m in _SIZE.finditer(copy)} - {"EU", "UK"}
    # Keep the existing EU spelling while checking every recognized claim.
    eu_prefix = "" if values else "EU "
    values.update(f"{eu_prefix}{m.group(1)}" for m in _EU_SIZE.finditer(copy))
    values.update(f"UK {m.group(1)}" for m in _UK_SIZE.finditer(copy))
    return (next(iter(values)) if len(values) == 1 else None), len(values) > 1


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
    conflicts: list[dict[str, str]] = []

    # A catalogue entry and an authorization line are separate structured
    # observations. Disagreement makes product identity unknown, including a
    # category disagreement when the names happen to match.
    category_conflict = reference is not None and (
        str(reference.get("item_category", "")).strip().lower()
        != str(item.get("item_category", "")).strip().lower()
    )
    identity_conflict = reference is not None and (
        _product_type(str(reference.get("item_name", ""))) != _product_type(title)
        or category_conflict
    )

    product_type = None if identity_conflict else _product_type(name)
    if identity_conflict:
        conflicts.append({"field": "product_type", "kind": "catalogue_event_mismatch"})
    if product_type is not None:
        sources["product_type"] = "structured" if reference else "merchant_text"

    size, size_conflict = _size(copy)
    if size_conflict:
        conflicts.append({"field": "size", "kind": "merchant_text_contradiction"})
    elif size is not None or any(pattern.search(copy) for pattern in (_SIZE, _EU_SIZE, _UK_SIZE)):
        sources["size"] = "merchant_text"

    return_days, return_claim_seen, return_conflict = _return_days(copy)
    if return_conflict:
        conflicts.append({"field": "return_days", "kind": "merchant_text_contradiction"})
    elif return_claim_seen:
        sources["return_days"] = "merchant_text"

    # Positive flags may come from the trusted catalogue category or text.
    # An absent phrase alone cannot prove a negative.
    is_gift_card = True if category == "gift_card" or _GIFT.search(text) else None
    is_subscription = True if category == "subscriptions" or _SUBSCRIPTION.search(text) else None
    if category_conflict:
        categories = {category, str(item.get("item_category", ""))}
        if "gift_card" in categories:
            is_gift_card = None
            conflicts.append({"field": "is_gift_card", "kind": "catalogue_event_mismatch"})
        if "subscriptions" in categories:
            is_subscription = None
            conflicts.append({"field": "is_subscription", "kind": "catalogue_event_mismatch"})
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
            # Exact compare of normalized names. Unknown only when a side is missing.
            matches_request = product_type == target
            match_source = sources["product_type"]
            requested_size = requested.get("size")
            if matches_request and requested_size is not None:
                if size is None:
                    matches_request = None
                else:
                    # The size is read from merchant copy, so the result
                    # inherits that provenance whenever the size decided it.
                    matches_request = size == str(requested_size).upper()
                    match_source = sources["size"]
            if matches_request is not None:
                sources["matches_request"] = match_source

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
        "conflicts": conflicts,
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
