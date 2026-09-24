"""Freeze customer and time partitions for the additional-history classifier comparison.

    PYTHONPATH=src python scripts/classifier_split.py

The manifest is written once with exclusive creation. It contains grouping IDs for
reproducibility, never model predictors. It reads no July outcomes for selection.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADDITIONAL = ROOT / "viseca-2026" / "additional-data-history"
BASE = ROOT / "viseca-2026" / "data"
OUTPUT = ROOT / "docs" / "eval" / "classifier" / "split-manifest.json"
SEED = 20260924
RESERVED_FRACTION = 0.20
WINDOWS = {
    "fit": ("2025-09-01", "2026-05-01"),
    "select": ("2026-05-01", "2026-06-01"),
    "calibrate": ("2026-06-01", "2026-06-16"),
    "threshold": ("2026-06-16", "2026-07-01"),
    "evaluate": ("2026-07-01", "2026-08-01"),
}


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"{path}: missing or repeated CSV column")
        rows = list(reader)
    for line, row in enumerate(rows, 2):
        if None in row or None in row.values():
            raise ValueError(f"{path}:{line}: malformed CSV row")
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build() -> dict:
    additional_accounts = _csv(ADDITIONAL / "accounts.csv")
    base_accounts = _csv(BASE / "accounts.csv")
    customers = sorted({row["customer_id"] for row in additional_accounts})
    base_customers = {row["customer_id"] for row in base_accounts}
    if not customers or base_customers.intersection(customers):
        raise ValueError("additional and base customers must be nonempty and disjoint")
    reserve_size = int(len(customers) * RESERVED_FRACTION)
    if reserve_size <= 0 or reserve_size >= len(customers):
        raise ValueError("customer reserve has no fitting or evaluation population")
    reserved = set(random.Random(SEED).sample(customers, reserve_size))
    fitting = set(customers) - reserved

    rows = _csv(ADDITIONAL / "authorization_history.csv")
    seen_ids: set[str] = set()
    purchases = []
    for row in rows:
        auth_id = row["authorization_id"]
        if not auth_id or auth_id in seen_ids:
            raise ValueError(f"duplicate or empty authorization id: {auth_id!r}")
        seen_ids.add(auth_id)
        if row["customer_id"] not in fitting | reserved:
            raise ValueError(f"{auth_id}: customer missing from account index")
        when = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        if when.tzinfo is None:
            raise ValueError(f"{auth_id}: timestamp lacks timezone")
        if row["transaction_type"] == "purchase":
            if row["status"] not in {"approved", "declined"}:
                raise ValueError(f"{auth_id}: unexpected purchase status")
            purchases.append((when, auth_id, row))
    purchases.sort(key=lambda entry: (entry[0], entry[1]))

    counts: dict[str, Counter] = {name: Counter() for name in WINDOWS}
    prior_approved: Counter = Counter()
    zero_history: dict[str, Counter] = {name: Counter() for name in WINDOWS}
    for when, auth_id, row in purchases:
        day = when.date().isoformat()
        window = next((name for name, (start, end) in WINDOWS.items() if start <= day < end), None)
        if window is None:
            raise ValueError(f"{auth_id}: purchase falls outside the frozen windows")
        population = "reserved" if row["customer_id"] in reserved else "seen"
        counts[window][population] += 1
        if prior_approved[row["customer_id"]] == 0:
            zero_history[window][population] += 1
        if row["status"] == "approved":
            prior_approved[row["customer_id"]] += 1

    sources = [
        ADDITIONAL / name for name in (
            "authorization_history.csv", "accounts.csv", "cards.csv", "metadata.json"
        )
    ] + [BASE / name for name in ("accounts.csv", "cards.csv")]
    sources += [ROOT / "docs" / "eval" / "classifier" / "feature-schema.md",
                ROOT / "docs" / "plans" / "02-classifier-design.md"]
    manifest = {
        "schema_version": "split-1",
        "seed": SEED,
        "additional_customer_count": len(customers),
        "reserved_customer_fraction": RESERVED_FRACTION,
        "reserved_customers": sorted(reserved),
        "fitting_customers": sorted(fitting),
        "base_customer_count": len(base_customers),
        "base_customers_excluded_from_all_fitting": True,
        "windows_utc_half_open": {name: [start, end] for name, (start, end) in WINDOWS.items()},
        "protocol": {
            "selection": "fit on seen customers before May; choose configuration on May",
            "refit": "refit selected configuration on seen customers through May",
            "calibration": "fit calibrator on seen customers June 1-15 only",
            "threshold": "propose threshold from seen customers June 16-30 only; owner approval required",
            "evaluation": "July reserved-customer metrics lead; seen-customer metrics are selection-informed",
            "g1_disposition": "variant 3: label seen-customer July as selection-informed; reserved July is primary",
        },
        "purchase_counts": {name: dict(counts[name]) for name in WINDOWS},
        "zero_prior_approved_customer_purchase_counts": {
            name: dict(zero_history[name]) for name in WINDOWS
        },
        "input_sha256": {str(path.relative_to(ROOT)): _sha256(path) for path in sources},
        "feature_schema_version": "hist-1",
    }
    if len(manifest["reserved_customers"]) != 100 or len(manifest["fitting_customers"]) != 400:
        raise ValueError("unexpected customer split size for supplied pack")
    return manifest


def main() -> None:
    manifest = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"split seed {SEED}: {len(manifest['fitting_customers'])} fitting, "
          f"{len(manifest['reserved_customers'])} reserved customers")
    for name in WINDOWS:
        print(name, manifest["purchase_counts"][name],
              "zero-prior-approved", manifest["zero_prior_approved_customer_purchase_counts"][name])
    print(f"manifest sha256 {_sha256(OUTPUT)}")


if __name__ == "__main__":
    main()
