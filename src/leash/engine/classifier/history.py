"""Pre-event purchase-history features at card and authorized-customer scope."""

from __future__ import annotations

import csv
import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Iterator

from leash.contracts import Event

from .types import FEATURE_SCHEMA_VERSION, HistoryFeatures

ROOT = Path(__file__).resolve().parents[4]
PACKS = {
    "base": ROOT / "viseca-2026" / "data",
    "additional": ROOT / "viseca-2026" / "additional-data-history",
}


@dataclass(frozen=True)
class _Record:
    pack: str
    row: dict[str, str]
    when: datetime

    @property
    def key(self) -> tuple[datetime, str]:
        return self.when, self.row["authorization_id"]


@dataclass(frozen=True)
class _Purchase:
    customer_id: str
    card_id: str
    authorization_id: str
    when: datetime
    merchant_id: str
    device_id: str
    country: str
    channel: str
    category: str
    amount_chf: float
    per_transaction_limit_chf: float
    monthly_limit_chf: float
    initiator_type: str
    card_status: str

    @property
    def key(self) -> tuple[datetime, str]:
        return self.when, self.authorization_id


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"{path}: missing or duplicate CSV columns")
        rows = list(reader)
    for line, row in enumerate(rows, 2):
        if None in row or None in row.values():
            raise ValueError(f"{path}:{line}: wrong number of CSV fields")
    return rows


def _amount(value: str, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label}: non-finite amount")
    return number


def _timestamp(value: str) -> datetime:
    when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise ValueError(f"history timestamp lacks timezone: {value!r}")
    return when


class HistoryIndex:
    """Load both organizer packs and reject identity or source inconsistencies."""

    def __init__(self, packs: dict[str, Path] | None = None):
        paths = PACKS if packs is None else packs
        if not paths:
            raise ValueError("history requires at least one explicit pack")
        self._owners: dict[str, str] = {}
        self._accounts: dict[str, str] = {}
        self._limits: dict[str, tuple[float, float]] = {}
        self._card_pack: dict[str, str] = {}
        self._customer_pack: dict[str, str] = {}
        self._rows_by_pack: dict[str, list[_Record]] = {}
        self._by_card: dict[str, list[_Record]] = {}
        self._by_customer: dict[str, list[_Record]] = {}
        self._card_keys: dict[str, list[tuple[datetime, str]]] = {}
        self._customer_keys: dict[str, list[tuple[datetime, str]]] = {}
        seen_authorizations: set[str] = set()

        for pack, path in paths.items():
            account_rows = _csv(path / "accounts.csv")
            accounts = {row["account_id"]: row for row in account_rows}
            if not accounts or len(accounts) != len(account_rows):
                raise ValueError(f"{path}: missing or duplicate accounts")
            for card in _csv(path / "cards.csv"):
                card_id = card["card_id"]
                if card_id in self._owners:
                    raise ValueError(f"duplicate card across history packs: {card_id}")
                account = accounts[card["account_id"]]
                customer_id = account["customer_id"]
                other_pack = self._customer_pack.get(customer_id)
                if other_pack is not None and other_pack != pack:
                    raise ValueError(f"customer {customer_id} occurs in both {other_pack} and {pack}")
                self._customer_pack[customer_id] = pack
                self._owners[card_id] = customer_id
                self._accounts[card_id] = card["account_id"]
                self._card_pack[card_id] = pack
                limits = (
                    _amount(account["per_transaction_limit_chf"], f"{card_id} transaction limit"),
                    _amount(account["monthly_limit_chf"], f"{card_id} monthly limit"),
                )
                if min(limits) <= 0:
                    raise ValueError(f"{card_id}: nonpositive account limit")
                self._limits[card_id] = limits

            records = []
            for row in _csv(path / "authorization_history.csv"):
                auth_id = row["authorization_id"]
                if not auth_id or auth_id in seen_authorizations:
                    raise ValueError(f"duplicate or empty authorization id: {auth_id!r}")
                seen_authorizations.add(auth_id)
                card_id = row["card_id"]
                if (self._card_pack.get(card_id) != pack
                        or self._owners[card_id] != row["customer_id"]
                        or self._accounts[card_id] != row["account_id"]):
                    raise ValueError(f"{auth_id}: card, account and customer ownership disagree")
                if row["transaction_type"] == "purchase":
                    if row["status"] not in {"approved", "declined"}:
                        raise ValueError(f"{auth_id}: unknown purchase status")
                    if not all(row[field] for field in (
                        "merchant_id", "merchant_category", "merchant_country", "channel"
                    )):
                        raise ValueError(f"{auth_id}: missing purchase category or merchant context")
                    if _amount(row["billing_amount_chf"], auth_id) <= 0:
                        raise ValueError(f"{auth_id}: nonpositive purchase amount")
                record = _Record(pack, row, _timestamp(row["timestamp"]))
                records.append(record)
                self._by_card.setdefault(card_id, []).append(record)
                self._by_customer.setdefault(row["customer_id"], []).append(record)
            records.sort(key=lambda record: record.key)
            self._rows_by_pack[pack] = records

        for card_id, records in self._by_card.items():
            records.sort(key=lambda record: record.key)
            self._card_keys[card_id] = [record.key for record in records]
        for customer_id, records in self._by_customer.items():
            records.sort(key=lambda record: record.key)
            self._customer_keys[customer_id] = [record.key for record in records]

    def _prior(self, purchase: _Purchase, scope: str) -> list[_Record]:
        if scope == "card":
            rows = self._by_card.get(purchase.card_id, [])
            keys = self._card_keys.get(purchase.card_id, [])
        else:
            rows = self._by_customer.get(purchase.customer_id, [])
            keys = self._customer_keys.get(purchase.customer_id, [])
        return rows[:bisect_left(keys, purchase.key)]

    def _features(self, purchase: _Purchase) -> HistoryFeatures:
        if purchase.card_status not in {"active", "blocked", "expired"}:
            raise ValueError(f"{purchase.authorization_id}: unknown card status")
        if purchase.initiator_type not in {"agent", "human"}:
            raise ValueError(f"{purchase.authorization_id}: unknown initiator type")
        if purchase.when.tzinfo is None:
            raise ValueError(f"{purchase.authorization_id}: timestamp lacks timezone")
        values: dict[str, float | None] = {}
        missing: dict[str, str] = {}
        support: dict[str, int] = {}

        def put(name: str, value: float | None, rows: int, reason: str = "") -> None:
            values[name] = value
            support[name] = rows
            if value is None:
                missing[name] = reason

        for scope in ("card", "customer"):
            prior = self._prior(purchase, scope)
            attempts = [row for row in prior if row.row["transaction_type"] == "purchase"]
            approved = [row for row in attempts if row.row["status"] == "approved"]
            put(f"{scope}_approved_purchase_count", float(len(approved)), len(approved))
            put(f"{scope}_prior_attempt_count", float(len(attempts)), len(attempts))

            for field, current in (
                ("merchant", purchase.merchant_id),
                ("device", purchase.device_id),
                ("country", purchase.country),
                ("channel", purchase.channel),
                ("category", purchase.category),
            ):
                name = f"{scope}_{field}"
                if field == "device" and not current:
                    put(f"{name}_approved_count", None, 0, "no_device")
                    put(f"{name}_last_approved_days", None, 0, "no_device")
                    continue
                column = {
                    "merchant": "merchant_id", "device": "customer_device_id",
                    "country": "merchant_country", "channel": "channel",
                    "category": "merchant_category",
                }[field]
                matches = [row for row in approved if row.row[column] == current]
                put(f"{name}_approved_count", float(len(matches)), len(approved))
                reason = "empty_history" if not approved else f"no_prior_in_{field}"
                days = (purchase.when - matches[-1].when).total_seconds() / 86400 if matches else None
                put(f"{name}_last_approved_days", days, len(matches), reason)

            category = [
                row for row in approved if row.row["merchant_category"] == purchase.category
            ]
            amounts = sorted(
                _amount(row.row["billing_amount_chf"], row.row["authorization_id"])
                for row in category
            )
            reason = "empty_history" if not approved else "no_prior_in_category"
            put(f"{scope}_category_amount_median_chf", float(median(amounts)) if amounts else None,
                len(amounts), reason)
            put(f"{scope}_category_amount_percentile",
                float(bisect_left(amounts, purchase.amount_chf) / len(amounts)) if amounts else None,
                len(amounts), reason)

            for window, duration in (("10m", timedelta(minutes=10)),
                                     ("1h", timedelta(hours=1)),
                                     ("24h", timedelta(hours=24))):
                recent = [row for row in attempts if row.when >= purchase.when - duration]
                put(f"{scope}_attempt_count_{window}", float(len(recent)), len(attempts))
                put(f"{scope}_declined_attempt_count_{window}",
                    float(sum(row.row["status"] == "declined" for row in recent)), len(attempts))

            days = (purchase.when - approved[-1].when).total_seconds() / 86400 if approved else None
            put(f"{scope}_last_approved_purchase_days", days, len(approved), "empty_history")
            put(f"{scope}_agent_attempt_count",
                float(sum(row.row["initiator_type"] == "agent" for row in attempts)), len(attempts))
            put(f"{scope}_agent_approved_count",
                float(sum(row.row["initiator_type"] == "agent" for row in approved)), len(approved))

        put("amount_to_per_transaction_limit", purchase.amount_chf / purchase.per_transaction_limit_chf, 1)
        put("amount_to_monthly_limit", purchase.amount_chf / purchase.monthly_limit_chf, 1)
        put("initiator_is_agent", float(purchase.initiator_type == "agent"), 1)
        put("card_active_at_attempt", float(purchase.card_status == "active"), 1)
        return HistoryFeatures(
            schema_version=FEATURE_SCHEMA_VERSION, customer_id=purchase.customer_id,
            card_id=purchase.card_id, as_of=purchase.when, values=values,
            missing=missing, support=support,
        )

    def for_event(self, event: Event) -> HistoryFeatures:
        """Use mandate identity, rejecting an authorization with a different card."""
        mandate, auth = event.mandate, event.authorization
        card_id, customer_id = mandate.card_id, mandate.customer_id
        if auth.card_id != card_id or auth.mandate_id != mandate.mandate_id:
            raise ValueError(f"{auth.authorization_id}: authorization and mandate identity differ")
        if self._owners.get(card_id) != customer_id:
            raise ValueError(f"{auth.authorization_id}: mandate card does not belong to customer")
        per_limit, monthly_limit = self._limits[card_id]
        purchase = _Purchase(
            customer_id=customer_id, card_id=card_id,
            authorization_id=auth.authorization_id, when=auth.timestamp,
            merchant_id=auth.merchant.merchant_id, device_id=auth.customer_device_id,
            country=auth.merchant.merchant_country, channel=auth.channel,
            category=auth.merchant.merchant_category, amount_chf=auth.billing_amount_chf,
            per_transaction_limit_chf=per_limit, monthly_limit_chf=monthly_limit,
            initiator_type=auth.initiator_type, card_status=auth.card_status_at_attempt,
        )
        return self._features(purchase)

    def historical_purchases(self, pack: str = "additional") -> Iterator[tuple[dict[str, str], HistoryFeatures]]:
        """Yield source rows and strictly pre-event features; callers exclude IDs from predictors."""
        for record in self._rows_by_pack[pack]:
            row = record.row
            if row["transaction_type"] != "purchase":
                continue
            per_limit = _amount(row["per_transaction_limit_chf"], row["authorization_id"])
            monthly_limit = _amount(row["monthly_limit_chf"], row["authorization_id"])
            if min(per_limit, monthly_limit) <= 0:
                raise ValueError(f"{row['authorization_id']}: nonpositive historical limit")
            purchase = _Purchase(
                customer_id=row["customer_id"], card_id=row["card_id"],
                authorization_id=row["authorization_id"], when=record.when,
                merchant_id=row["merchant_id"], device_id=row["customer_device_id"],
                country=row["merchant_country"], channel=row["channel"],
                category=row["merchant_category"],
                amount_chf=_amount(row["billing_amount_chf"], row["authorization_id"]),
                per_transaction_limit_chf=per_limit, monthly_limit_chf=monthly_limit,
                initiator_type=row["initiator_type"], card_status=row["card_status"],
            )
            yield row, self._features(purchase)
