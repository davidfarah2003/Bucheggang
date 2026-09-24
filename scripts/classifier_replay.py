"""Offline replay through pre-event history, extraction and the real evaluator.

    PYTHONPATH=src python scripts/classifier_replay.py \
      --policy SCEN0002=docs/samples/scen0002_draft.json \
      --output docs/eval/classifier/m1-scen0002.csv

The startup configuration here has no model effect. No customer answer is invented,
no simulator request is sent, and pending step-ups remain pending.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import replay as base
from leash.contracts import MandateState, PolicyDraft, PurchaseFacts
from leash.engine import evaluate
from leash.engine.classifier.assess import history_bundle, validate_bundle
from leash.engine.classifier.history import HistoryIndex
from leash.engine.state import apply
from leash.extract import extract_event
from leash.policy.store import draft_hash

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", action="append", required=True, metavar="SCENARIO=PATH")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")

    pack = base.load_pack()
    scenarios, authorities, merchants, attempts, items = pack
    policies = {}
    for entry in args.policy:
        scenario_id, separator, filename = entry.partition("=")
        if not separator or scenario_id not in scenarios or scenario_id in policies:
            parser.error(f"invalid or repeated scenario policy: {entry!r}")
        raw = json.loads(Path(filename).read_text(encoding="utf-8"))
        policy = PolicyDraft.model_validate(raw)
        if policy.hash != draft_hash(raw["instruction"], raw["rules"], raw["uncertainty_policy"]):
            parser.error(f"{filename}: policy hash does not match its rules")
        if policy.instruction != scenarios[scenario_id]["cardholder_instruction"]:
            parser.error(f"{filename}: instruction differs from {scenario_id}")
        policies[scenario_id] = policy

    history = HistoryIndex()
    results = []
    for scenario_id, policy in sorted(policies.items()):
        scenario_rows = sorted((row for row in attempts.values() if row["scenario_id"] == scenario_id),
                               key=lambda row: int(row["replay_order"]))
        if len(scenario_rows) != int(scenarios[scenario_id]["event_count"]):
            raise ValueError(f"{scenario_id}: attempt count differs from scenario catalogue")
        if [int(row["replay_order"]) for row in scenario_rows] != list(range(1, len(scenario_rows) + 1)):
            raise ValueError(f"{scenario_id}: replay order has missing or duplicate positions")
        identity = {(row["authority_id"], row["card_id"]) for row in scenario_rows}
        if len(identity) != 1:
            raise ValueError(f"{scenario_id}: authority or card changes during the scenario")
        authority_id, card_id = next(iter(identity))
        if authorities[authority_id]["card_id"] != card_id:
            raise ValueError(f"{scenario_id}: attempt card differs from its authority")
        state = MandateState(mandate_id=f"offline-mandate-{uuid4().hex}")
        prior_events = {}
        previous_key = None
        for row in scenario_rows:
            auth_id = row["authorization_id"]
            authority = authorities[row["authority_id"]]
            event = base.build_event(row, authority, merchants[row["merchant_id"]], items[auth_id],
                                     policy, state, prior_events, 8.0)
            current_key = (event.authorization.timestamp, auth_id)
            if previous_key is not None and current_key <= previous_key:
                raise ValueError(f"{scenario_id}/{auth_id}: scenario event-time key did not advance")
            previous_key = current_key
            started = perf_counter()
            bundle = history_bundle(event, policy, history)
            facts = [PurchaseFacts.model_validate(fact) for fact in
                     extract_event(event.model_dump(mode="json"),
                                   requested=base.requested_item(policy))]
            validate_bundle(event, policy, bundle)
            decision = evaluate(event, policy, state, facts)
            elapsed_ms = (perf_counter() - started) * 1000
            if datetime.now(UTC) >= event.deadline_at:
                raise TimeoutError(f"{scenario_id}/{auth_id}: offline replay exceeded deadline")
            next_state = apply(state, event, decision)
            features = bundle.features
            results.append({
                "scenario_id": scenario_id,
                "authorization_id": auth_id,
                "decision": decision.decision,
                "reason_codes": "|".join(decision.reason_codes),
                "card_merchant_approved_count": features.values["card_merchant_approved_count"],
                "customer_merchant_approved_count": features.values["customer_merchant_approved_count"],
                "card_approved_purchase_count": features.values["card_approved_purchase_count"],
                "customer_approved_purchase_count": features.values["customer_approved_purchase_count"],
                "missing_feature_count": len(features.missing),
                "history_schema": features.schema_version,
                "elapsed_ms": f"{elapsed_ms:.3f}",
            })
            state = next_state
            prior_events[auth_id] = event

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    print(f"classifier history replay: {len(results)} attempts, model effect off")
    for row in results:
        print(row["scenario_id"], row["authorization_id"], row["decision"],
              row["reason_codes"], "merchant card/customer",
              row["card_merchant_approved_count"], row["customer_merchant_approved_count"])
    print(f"CSV: {args.output}")


if __name__ == "__main__":
    main()
