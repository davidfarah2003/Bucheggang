"""Versioned customer-wide policy rules, applied to future confirmations."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from leash.contracts import Rule

from .store import DraftStore, InvalidDraft, _validate_rule


def rules_hash(rules: list[dict]) -> str:
    canonical = json.dumps(
        rules, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _plain_english(rule: dict) -> str:
    labels = {
        "authorization.billing_amount_chf": "purchase amount",
        "authorization.items_subtotal": "items subtotal",
        "authorization.delivery_fee": "delivery fee",
        "authorization.currency": "currency",
        "authorization.channel": "channel",
        "authorization.fulfillment_method": "fulfillment method",
        "authorization.order_returnable": "returnability",
        "authorization.merchant.merchant_id": "merchant",
        "authorization.merchant.merchant_category": "merchant category",
        "authorization.merchant.merchant_mcc": "merchant category code",
        "authorization.merchant.merchant_country": "merchant country",
        "items.category": "item category",
        "items.count": "item count",
        "facts.product_type": "product type",
        "facts.size": "size",
        "facts.return_days": "return window in days",
        "facts.is_gift_card": "gift card status",
        "facts.is_subscription": "subscription status",
        "facts.is_protection_plan": "protection plan status",
        "facts.is_addon": "add-on status",
        "history.merchant_seen_on_card": "merchant history",
        "history.device_seen_on_card": "device history",
        "state.approvals_count": "purchase count",
    }
    operators = {
        "<": "is less than", "<=": "is at most", "=": "is", "!=": "is not",
        ">": "is greater than", ">=": "is at least", "in": "is one of",
        "not_in": "is not one of",
    }
    field_label = labels.get(rule.get("field"))
    operator_label = operators.get(rule.get("operator"))
    if field_label is None or operator_label is None:
        raise InvalidDraft("unsupported global rule field or operator")
    value = rule["value"]
    rendered = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
    if rule.get("currency") and isinstance(value, (int, float)):
        rendered = f"{rendered} {rule['currency']}"
    sentence = f"{field_label} {operator_label} {rendered}"
    if rule.get("scope") == "period":
        sentence += f" over {rule['period_days']} days"
    return sentence[0].upper() + sentence[1:] + "."


class GlobalPolicyConflict(RuntimeError):
    """A global policy version or hash is stale."""


class GlobalPolicyStore:
    def __init__(self, policy_store: DraftStore):
        self.root = policy_store.root.parent / "global"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _filename(customer: str) -> str:
        if not isinstance(customer, str) or not customer:
            raise ValueError("authenticated customer identity is required")
        return quote(customer, safe="") + ".json"

    def _path(self, customer: str) -> Path:
        return self.root / self._filename(customer)

    @contextmanager
    def locked(self, customer: str):
        path = self._path(customer)
        descriptor = os.open(path.with_suffix(".lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield path
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def read(self, customer: str) -> dict:
        path = self._path(customer)
        if not path.exists():
            rules: list[dict] = []
            return {
                "customer": customer,
                "version": 0,
                "hash": rules_hash(rules),
                "rules": rules,
                "updated_at": None,
            }
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or data.get("customer") != customer:
            raise RuntimeError(f"invalid global policy record for {customer!r}")
        if type(data.get("version")) is not int or data["version"] < 1:
            raise RuntimeError(f"invalid global policy version for {customer!r}")
        if not isinstance(data.get("rules"), list) or not isinstance(data.get("updated_at"), str):
            raise RuntimeError(f"invalid global policy contents for {customer!r}")
        try:
            canonical_rules = validate_rules(data["rules"])
        except (InvalidDraft, ValueError) as exc:
            raise RuntimeError(f"invalid saved global policy rules for {customer!r}: {exc}") from exc
        if canonical_rules != data["rules"]:
            raise RuntimeError(f"global policy rules are not canonical for {customer!r}")
        if data.get("hash") != rules_hash(data["rules"]):
            raise RuntimeError(f"global policy hash mismatch for {customer!r}")
        return data

    def replace(
        self, customer: str, expected_version: int, expected_hash: str, rules: list[dict]
    ) -> dict:
        with self.locked(customer) as path:
            previous = self.read(customer)
            if previous["version"] != expected_version or previous["hash"] != expected_hash:
                raise GlobalPolicyConflict("global policy version or hash changed; reload before saving")
            updated = {
                "customer": customer,
                "version": previous["version"] + 1,
                "hash": rules_hash(rules),
                "rules": rules,
                "updated_at": _now(),
            }
            temporary = self.root / f".{self._filename(customer)}.{uuid4().hex}.tmp"
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(updated, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            return updated


def validate_rules(rules: object) -> list[dict]:
    if not isinstance(rules, list):
        raise InvalidDraft("rules must be a list")
    clean = []
    identities = set()
    for raw in rules:
        if not isinstance(raw, dict):
            raise InvalidDraft("every global rule must be an object")
        rule = dict(raw)
        source = rule.get("source_text")
        if not isinstance(source, str) or not source.strip():
            raise InvalidDraft("each global rule needs a source_text label")
        generated = "plain_english" not in rule
        if generated:
            rule["plain_english"] = "pending generation"
        _validate_rule(rule, source)
        if generated:
            rule["plain_english"] = _plain_english(rule)
        if rule.get("scope") == "period" and rule["field"] not in {
            "authorization.billing_amount_chf", "state.approvals_count"
        }:
            raise InvalidDraft("period scope is supported only for billing_amount_chf and approvals_count")
        checked = Rule.model_validate(rule).model_dump(mode="json", exclude_none=True)
        identity = (
            checked["field"], checked["operator"], checked.get("scope"), checked.get("period_days")
        )
        if identity in identities:
            raise InvalidDraft("duplicate global policy control")
        identities.add(identity)
        clean.append(checked)
    return clean


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
