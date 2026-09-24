"""Read-only reference data from the organizer pack, loaded once at import.

Loading happens here so that `rules` and `evaluate` stay free of I/O.
"""

from __future__ import annotations

import csv
from bisect import bisect_left
from datetime import datetime
from pathlib import Path

PACK = Path(__file__).resolve().parents[3] / "viseca-2026" / "data"
ADDITIONAL_HISTORY = Path(__file__).resolve().parents[3] / "viseca-2026" / "additional-data-history"


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_fx() -> dict[str, float]:
    with open(PACK / "fx_rates.csv", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rates = {row["from_currency"]: float(row["rate"]) for row in rows if row["to_currency"] == "CHF"}
    if set(rates) != {"CHF", "EUR", "GBP", "USD"}:
        raise RuntimeError(f"fx_rates.csv has rates for {sorted(rates)}, expected CHF EUR GBP USD")
    return rates


FX_TO_CHF = _load_fx()


class History:
    """Approved purchases per card from every authorization_history.csv given, by timestamp.

    The organizer ships two packs with disjoint cards: `data/` holds the public scenario
    cards and `additional-data-history/` holds the rest, including the live team cards.
    Both are read so a live card is not reported as having no history.
    """

    def __init__(self, *paths: Path):
        merchants: dict[tuple[str, str], list[datetime]] = {}
        devices: dict[tuple[str, str], list[datetime]] = {}
        countries: dict[tuple[str, str], list[datetime]] = {}
        names: dict[str, dict[str, str]] = {}
        cards: dict[str, list[datetime]] = {}
        seen: set[str] = set()
        for path in paths:
            if not path.is_file():
                raise RuntimeError(f"history file is missing: {path}")
            with open(path, newline="") as handle:
                for row in csv.DictReader(handle):
                    if row["authorization_id"] in seen:
                        raise RuntimeError(f"{path}: authorization {row['authorization_id']} appears in two history files")
                    seen.add(row["authorization_id"])
                    self._add(row, merchants, devices, countries, names, cards)
        for series in (*merchants.values(), *devices.values(), *countries.values(), *cards.values()):
            series.sort()
        self._merchants = merchants
        self._devices = devices
        self._countries = countries
        self._names = names
        self._cards = cards

    @staticmethod
    def _add(row, merchants, devices, countries, names, cards) -> None:
        cards.setdefault(row["card_id"], []).append(_ts(row["timestamp"]))
        if row["status"] != "approved" or row["transaction_type"] != "purchase":
            return
        when = _ts(row["timestamp"])
        merchants.setdefault((row["card_id"], row["merchant_id"]), []).append(when)
        countries.setdefault((row["card_id"], row["merchant_country"]), []).append(when)
        names.setdefault(row["card_id"], {})[row["merchant_id"]] = row["merchant_name"]
        if row["customer_device_id"]:
            devices.setdefault((row["card_id"], row["customer_device_id"]), []).append(when)

    @staticmethod
    def _count_before(series: list[datetime] | None, before: datetime) -> int:
        return 0 if not series else bisect_left(series, before)

    def card_rows(self, card_id: str, before: datetime) -> int:
        """Rows of any status and type for this card before `before`."""
        return self._count_before(self._cards.get(card_id), before)

    def merchant_count(self, card_id: str, merchant_id: str, before: datetime) -> int:
        return self._count_before(self._merchants.get((card_id, merchant_id)), before)

    def device_count(self, card_id: str, device_id: str, before: datetime) -> int:
        return self._count_before(self._devices.get((card_id, device_id)), before)

    def country_count(self, card_id: str, country: str, before: datetime) -> int:
        return self._count_before(self._countries.get((card_id, country)), before)

    def known_merchants(self, card_id: str, before: datetime) -> dict[str, str]:
        """merchant_id -> merchant_name for merchants with an approved purchase before `before`."""
        return {
            mid: name for mid, name in self._names.get(card_id, {}).items()
            if self.merchant_count(card_id, mid, before) > 0
        }


HISTORY = History(PACK / "authorization_history.csv", ADDITIONAL_HISTORY / "authorization_history.csv")
