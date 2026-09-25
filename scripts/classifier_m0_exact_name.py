"""Classifier M0 evidence: SCEN0004 through the merged extract and evaluate paths.

Builds one Event per SCEN0004 attempt from the public data pack, drafts the
scenario's three rules (amount <= CHF 400, facts.product_type = <name>,
history.merchant_seen_on_card = true) with uncertainty_policy ask, and runs
leash.extract.extract_event then leash.engine.evaluate on an empty mandate
state. Prints one line per attempt: decision, reason codes, and each line's
matches_request with its recorded source.

The product name is the only argument, so the run can compare the
instruction's own words with the catalogue name:

    uv run python scripts/classifier_m0_exact_name.py "27-inch monitor"
    uv run python scripts/classifier_m0_exact_name.py "27-inch computer monitor"

No simulator, provider or network call. Reads viseca-2026/data only.
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from leash.contracts import Event, MandateState, PolicyDraft, PurchaseFacts
from leash.engine import evaluate
from leash.extract import extract_event

DATA = Path(__file__).resolve().parent.parent / "viseca-2026/data"
SCENARIO = "SCEN0004"
MANDATE = "TM_M0"


def rows(name: str) -> list[dict]:
    with open(DATA / name, newline="") as stream:
        return list(csv.DictReader(stream))


def build_event(attempt: dict, lines: list[dict], merchant: dict, authority: dict, instruction: str) -> Event:
    at = datetime.fromisoformat(attempt["timestamp"].replace("Z", "+00:00"))
    number = lambda value: float(value) if value else None
    return Event.model_validate({
        "type": "authorization.request",
        "request_id": "m0",
        "deadline_at": (at + timedelta(seconds=8)).isoformat(),
        "authorization": {
            "authorization_id": attempt["authorization_id"],
            "source_authorization_id": attempt["authorization_id"],
            "scenario_id": attempt["scenario_id"],
            "replay_order": int(attempt["replay_order"]),
            "mandate_id": MANDATE,
            "profile_id": "P",
            "card_id": attempt["card_id"],
            "initiator_type": "agent",
            "merchant": dict(merchant),
            "timestamp": attempt["timestamp"],
            "amount": float(attempt["amount"]),
            "currency": attempt["currency"],
            "billing_amount_chf": float(attempt["billing_amount_chf"]),
            "items_subtotal": float(attempt["items_subtotal"]),
            "delivery_fee": float(attempt["delivery_fee"]),
            "channel": attempt["channel"],
            "customer_device_id": attempt["customer_device_id"],
            "authority_status": attempt["authority_status"],
            "card_status_at_attempt": attempt["card_status_at_attempt"],
            "spend_in_period_before_chf": number(attempt["spend_in_period_before_chf"]),
            "recent_attempt_count_10m": int(attempt["recent_attempt_count_10m"]),
            "fulfillment_method": attempt["fulfillment_method"],
            "delivery_by": attempt["delivery_by"] or None,
            "order_returnable": attempt["order_returnable"],
            "order_cancellable": attempt["order_cancellable"],
            "related_authorization_id": attempt["related_authorization_id"] or None,
            "related_authorization_status": attempt["related_authorization_status"] or None,
            "purchase_description": attempt["purchase_description"],
            "items": [
                {
                    "line_no": int(line["line_no"]),
                    "item_id": line["item_id"],
                    "item_name": line["item_name"],
                    "item_category": line["item_category"],
                    "quantity": int(line["quantity"]),
                    "unit_price": float(line["unit_price"]),
                    "currency": line["currency"],
                    "item_details": line["item_details"],
                }
                for line in lines
            ],
        },
        "mandate": {
            "mandate_id": MANDATE,
            "status": "active",
            "customer_id": authority["customer_id"],
            "card_id": authority["card_id"],
            "instruction": instruction,
            "hard_rules": [],
            "uncertainty_policy": "ask",
            "profile_id": "P",
        },
        "context": {"approved_spend_in_period_chf": None, "recent_authorizations": []},
        "runtime": {
            "received_at": attempt["timestamp"],
            "history_window_minutes": 10,
            "context_basis": "run_decisions_and_scenario_timestamps",
        },
    })


def draft(instruction: str, product: str) -> PolicyDraft:
    def rule(field: str, operator: str, value: object, text: str) -> dict:
        return {"field": field, "operator": operator, "value": value, "scope": "purchase",
                "source_text": text, "plain_english": text}

    return PolicyDraft.model_validate({
        "draft_id": "m0",
        "version": 1,
        "hash": "m0",
        "instruction": instruction,
        "rules": [
            rule("authorization.billing_amount_chf", "<=", 400, "for CHF 400 or less") | {"currency": "CHF"},
            rule("facts.product_type", "=", product, "the 27-inch monitor I chose"),
            rule("history.merchant_seen_on_card", "=", "true", "a seller I have bought from before"),
        ],
        "examples": [],
        "open_questions": [],
        "uncertainty_policy": "ask",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def main(product: str) -> None:
    attempts = [a for a in rows("purchase_attempts.csv") if a["scenario_id"] == SCENARIO]
    items = rows("purchase_attempt_items.csv")
    merchants = {m["merchant_id"]: m for m in rows("merchants.csv")}
    authorities = {a["authority_id"]: a for a in rows("scenario_authorities.csv")}
    catalogue = {i["item_id"]: i for i in rows("items.csv")}
    instruction = next(s for s in rows("scenario_catalogue.csv") if s["scenario_id"] == SCENARIO)["cardholder_instruction"]
    policy = draft(instruction, product)
    for attempt in sorted(attempts, key=lambda a: int(a["replay_order"])):
        lines = sorted((i for i in items if i["authorization_id"] == attempt["authorization_id"]),
                       key=lambda i: int(i["line_no"]))
        event = build_event(attempt, lines, merchants[attempt["merchant_id"]],
                            authorities[attempt["authority_id"]], instruction)
        raw = extract_event(event.model_dump(mode="json"), catalogue=catalogue, requested={"product_type": product})
        facts = [PurchaseFacts.model_validate(f) for f in raw]
        decision = evaluate(event, policy, MandateState(mandate_id=MANDATE), facts)
        matches = [(f.item_id, f.matches_request, f.sources.get("matches_request")) for f in facts]
        print(attempt["authorization_id"], decision.decision, ",".join(decision.reason_codes), "| matches_request", matches)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: classifier_m0_exact_name.py <requested product name>")
    main(sys.argv[1])
