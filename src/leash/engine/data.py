"""Read-only reference data from the organizer pack, loaded once at import.

Loading happens here so that `rules` and `evaluate` stay free of I/O.
"""

from __future__ import annotations

import csv
from bisect import bisect_left
from datetime import datetime
from pathlib import Path

PACK = Path(__file__).resolve().parents[3] / "viseca-2026" / "data"


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
    """Approved purchases per card from authorization_history.csv, by timestamp."""

    def __init__(self, path: Path):
        merchants: dict[tuple[str, str], list[datetime]] = {}
        devices: dict[tuple[str, str], list[datetime]] = {}
        with open(path, newline="") as handle:
            for row in csv.DictReader(handle):
                if row["status"] != "approved" or row["transaction_type"] != "purchase":
                    continue
                when = _ts(row["timestamp"])
                merchants.setdefault((row["card_id"], row["merchant_id"]), []).append(when)
                if row["customer_device_id"]:
                    devices.setdefault((row["card_id"], row["customer_device_id"]), []).append(when)
        for series in (*merchants.values(), *devices.values()):
            series.sort()
        self._merchants = merchants
        self._devices = devices

    @staticmethod
    def _count_before(series: list[datetime] | None, before: datetime) -> int:
        return 0 if not series else bisect_left(series, before)

    def merchant_count(self, card_id: str, merchant_id: str, before: datetime) -> int:
        return self._count_before(self._merchants.get((card_id, merchant_id)), before)

    def device_count(self, card_id: str, device_id: str, before: datetime) -> int:
        return self._count_before(self._devices.get((card_id, device_id)), before)


HISTORY = History(PACK / "authorization_history.csv")
