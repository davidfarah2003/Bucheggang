"""Replay supplied public attempts through the real extraction and decision engine.

    uv run python scripts/replay.py \
        --policy SCEN0002=docs/samples/scen0002_draft.json

Repeat --policy for additional scenarios; --all requires a draft for every public
scenario. Drafts are evaluation inputs, not customer confirmations. Sequential
replay projects approvals into memory and leaves step-ups pending. It continues
through the input rows without reproducing the live platform's step-up pause.
No simulator calls, customer answers, or persistent mandate-state writes occur.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from uuid import uuid4

from leash.contracts import Event, MandateState, PolicyDraft, PurchaseFacts
from leash.contracts.event import Item, Merchant
from leash.engine import evaluate
from leash.engine.data import PACK
from leash.engine.state import apply
from leash.extract import extract_event
from leash.policy.store import draft_hash
from leash.runner.loop import requested_item

ROOT = Path(__file__).resolve().parent.parent
STATUS = {"approve": "approved", "decline": "declined", "step_up": "pending"}
HISTORY_MINUTES = 10


def read_csv(name: str) -> list[dict[str, str]]:
    path = PACK / name
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"{path}: missing or repeated column names")
        rows = list(reader)
    for number, row in enumerate(rows, 2):
        if None in row or None in row.values():
            raise ValueError(f"{path}:{number}: wrong number of CSV fields")
    return rows


def index_rows(rows: list[dict], key: str, name: str) -> dict[str, dict]:
    indexed = {}
    for row in rows:
        identity = row[key]
        if not identity or identity in indexed:
            raise ValueError(f"{name}: empty or duplicate {key}: {identity!r}")
        indexed[identity] = row
    return indexed


def number(value: str) -> float:
    parsed = Decimal(value)
    if not parsed.is_finite():
        raise ValueError(f"non-finite monetary value: {value!r}")
    result = float(parsed)
    if not math.isfinite(result):
        raise ValueError(f"monetary value exceeds the event number range: {value!r}")
    return result


def total(approvals: list) -> float:
    amount = sum((Decimal(str(item.amount_chf)) for item in approvals), Decimal("0"))
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))


def load_pack() -> tuple[dict, dict, dict, dict, dict]:
    scenarios = index_rows(read_csv("scenario_catalogue.csv"), "scenario_id", "scenario catalogue")
    authorities = index_rows(read_csv("scenario_authorities.csv"), "authority_id", "authorities")
    merchant_rows = index_rows(read_csv("merchants.csv"), "merchant_id", "merchants")
    merchants = {key: Merchant.model_validate(row) for key, row in merchant_rows.items()}
    attempts = index_rows(read_csv("purchase_attempts.csv"), "authorization_id", "attempts")
    items = defaultdict(list)
    for raw in read_csv("purchase_attempt_items.csv"):
        row = dict(raw)
        auth_id = row.pop("authorization_id")
        if auth_id not in attempts:
            raise ValueError(f"cart line references missing authorization {auth_id}")
        row["line_no"] = int(row["line_no"])
        row["quantity"] = int(row["quantity"])
        row["unit_price"] = number(row["unit_price"])
        items[auth_id].append(Item.model_validate(row))
    for auth_id, lines in items.items():
        lines.sort(key=lambda item: item.line_no)
        if len({item.line_no for item in lines}) != len(lines):
            raise ValueError(f"{auth_id}: repeated cart line number")
    return scenarios, authorities, merchants, attempts, items


def build_event(row: dict, authority: dict, merchant: Merchant, items: list[Item],
                policy: PolicyDraft, state: MandateState, prior_events: dict[str, Event],
                deadline_seconds: float) -> Event:
    auth = dict(row)
    auth.pop("authority_id")
    auth.pop("merchant_id")
    auth["replay_order"] = int(auth["replay_order"])
    auth["recent_attempt_count_10m"] = int(auth["recent_attempt_count_10m"])
    for field in ("amount", "billing_amount_chf", "items_subtotal", "delivery_fee"):
        auth[field] = number(auth[field])
    value = auth["spend_in_period_before_chf"]
    auth["spend_in_period_before_chf"] = number(value) if value else None
    for field in ("delivery_by", "related_authorization_id", "related_authorization_status"):
        auth[field] = auth[field] or None
    related = auth["related_authorization_id"]
    if related in state.handled:
        auth["related_authorization_status"] = STATUS[state.handled[related].decision]
    now = datetime.fromisoformat(auth["timestamp"].replace("Z", "+00:00"))
    if now.tzinfo is None:
        raise ValueError(f"{auth['authorization_id']}: scenario timestamp lacks a timezone")
    profile_id = f"offline-profile-{authority['customer_id']}"
    auth.update(source_authorization_id=auth["authorization_id"], mandate_id=state.mandate_id,
                profile_id=profile_id, initiator_type="agent", merchant=merchant, items=items)
    recent = []
    for auth_id, earlier in prior_events.items():
        purchase = earlier.authorization
        if now - timedelta(minutes=HISTORY_MINUTES) <= purchase.timestamp < now:
            recent.append({"authorization_id": auth_id, "timestamp": purchase.timestamp,
                           "merchant_id": purchase.merchant.merchant_id,
                           "billing_amount_chf": purchase.billing_amount_chf,
                           "status": STATUS[state.handled[auth_id].decision]})
    periods = {rule.period_days for rule in policy.rules if rule.scope == "period"}
    period_spend = None
    if len(periods) == 1:
        start = now - timedelta(days=next(iter(periods)))
        period_spend = total([item for item in state.approvals if start < item.timestamp <= now])
    received = datetime.now(UTC)
    return Event.model_validate({
        "type": "authorization.request", "request_id": f"offline-request-{uuid4().hex}",
        "deadline_at": received + timedelta(seconds=deadline_seconds), "authorization": auth,
        "mandate": {"mandate_id": state.mandate_id, "status": "active",
                    "customer_id": authority["customer_id"], "card_id": authority["card_id"],
                    "profile_id": profile_id, "instruction": policy.instruction,
                    "hard_rules": [rule.simulator_rule() for rule in policy.rules],
                    "uncertainty_policy": policy.uncertainty_policy},
        "context": {"approved_spend_in_period_chf": period_spend, "recent_authorizations": recent},
        "runtime": {"received_at": received, "history_window_minutes": HISTORY_MINUTES,
                    "context_basis": "run_decisions_and_scenario_timestamps"},
    })


def replay(policies: dict[str, PolicyDraft], pack: tuple, mode: str, deadline_seconds: float) -> list[dict]:
    scenarios, authorities, merchants, attempts, items = pack
    results = []
    for scenario_id, policy in sorted(policies.items()):
        scenario = scenarios[scenario_id]
        if policy.instruction != scenario["cardholder_instruction"]:
            raise ValueError(f"{scenario_id}: draft instruction differs from the supplied scenario")
        rows = sorted((row for row in attempts.values() if row["scenario_id"] == scenario_id),
                      key=lambda row: int(row["replay_order"]))
        if not rows or len(rows) != int(scenario["event_count"]):
            raise ValueError(f"{scenario_id}: attempt count differs from the scenario catalogue")
        if [int(row["replay_order"]) for row in rows] != list(range(1, len(rows) + 1)):
            raise ValueError(f"{scenario_id}: replay_order must contain each position exactly once")
        identity = {(row["authority_id"], row["card_id"]) for row in rows}
        if len(identity) != 1:
            raise ValueError(f"{scenario_id}: authority or card changes during the scenario")
        authority = authorities[rows[0]["authority_id"]]
        if authority["card_id"] != rows[0]["card_id"]:
            raise ValueError(f"{scenario_id}: attempt card differs from its authority")
        state = MandateState(mandate_id=f"offline-mandate-{uuid4().hex}")
        prior_events = {}
        previous_time = None
        for row in rows:
            if mode == "independent":
                state = MandateState(mandate_id=state.mandate_id)
                prior_events = {}
            auth_id = row["authorization_id"]
            event = build_event(row, authority, merchants[row["merchant_id"]], items[auth_id],
                                policy, state, prior_events, deadline_seconds)
            if previous_time is not None and event.authorization.timestamp < previous_time:
                raise ValueError(f"{scenario_id}/{auth_id}: scenario time moved backwards")
            previous_time = event.authorization.timestamp
            started = time.perf_counter()
            facts = [PurchaseFacts.model_validate(fact) for fact in
                     extract_event(event.model_dump(mode="json"), requested=requested_item(policy))]
            extracted = time.perf_counter()
            decision = evaluate(event, policy, state, facts)
            evaluated = time.perf_counter()
            remaining_ms = (event.deadline_at - datetime.now(UTC)).total_seconds() * 1000
            if remaining_ms <= 0:
                raise TimeoutError(f"{scenario_id}/{auth_id}: evaluation exceeded its real-clock deadline")
            after = apply(state, event, decision)
            results.append({
                "scenario_id": scenario_id, "authorization_id": auth_id,
                "replay_order": event.authorization.replay_order, "mode": mode,
                "scenario_timestamp": event.authorization.timestamp.isoformat(),
                "decision": decision.decision, "reason_codes": "|".join(decision.reason_codes),
                "billing_amount_chf": f"{event.authorization.billing_amount_chf:.2f}",
                "approved_spend_before_chf": f"{total(state.approvals):.2f}",
                "approved_spend_after_chf": f"{total(after.approvals):.2f}",
                "pending_before": len(state.pending_step_ups), "pending_after": len(after.pending_step_ups),
                "extract_ms": f"{(extracted - started) * 1000:.3f}",
                "evaluate_ms": f"{(evaluated - extracted) * 1000:.3f}",
                "total_ms": f"{(evaluated - started) * 1000:.3f}",
                "deadline_remaining_ms": f"{remaining_ms:.3f}",
                "draft_id": policy.draft_id, "draft_hash": policy.hash, "mandate_version": policy.version,
                "engine_version": decision.engine_version, "decided_at": decision.decided_at.isoformat(),
                "customer_message": decision.customer_message, "explanation": decision.explanation,
                "evidence_json": json.dumps([check.model_dump(mode="json") for check in decision.evidence]),
            })
            state = after
            prior_events[auth_id] = event
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--policy", action="append", required=True, metavar="SCENARIO=PATH",
                        help="supplied PolicyDraft JSON; repeat once per scenario")
    parser.add_argument("--all", action="store_true", help="require a policy for every public scenario")
    parser.add_argument("--mode", choices=("sequential", "independent"), default="sequential")
    parser.add_argument("--deadline-seconds", type=float, default=8.0,
                        help="fresh offline decision window, not a live bootstrap value (default: 8)")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs" / "eval" / f"replay-{datetime.now(UTC).date()}.csv",
                        help="new CSV file; an existing report is never overwritten")
    args = parser.parse_args()
    if not math.isfinite(args.deadline_seconds) or args.deadline_seconds <= 0:
        parser.error("--deadline-seconds must be finite and positive")
    if args.output.exists():
        parser.error(f"report exists: {args.output}; choose a new --output path")
    pack = load_pack()
    policies = {}
    for specification in args.policy:
        scenario_id, separator, filename = specification.partition("=")
        if not separator or not filename:
            parser.error("--policy must be SCENARIO=PATH")
        if scenario_id not in pack[0] or scenario_id in policies:
            parser.error(f"unknown or repeated scenario: {scenario_id}")
        raw = json.loads(Path(filename).read_text(encoding="utf-8"))
        policy = PolicyDraft.model_validate(raw)
        if policy.hash != draft_hash(raw["instruction"], raw["rules"], raw["uncertainty_policy"]):
            parser.error(f"{filename}: draft hash does not match its instruction and rules")
        policies[scenario_id] = policy
    if args.all and set(policies) != set(pack[0]):
        parser.error(f"--all needs explicit policies for: {', '.join(sorted(set(pack[0]) - set(policies)))}")
    rows = replay(policies, pack, args.mode, args.deadline_seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Offline {args.mode} replay: {len(rows)} attempts. No API submission or customer resolution.")
    print("scenario | authorization | decision | reasons | total ms")
    for row in rows:
        print(f"{row['scenario_id']} | {row['authorization_id']} | {row['decision']} | "
              f"{row['reason_codes']} | {row['total_ms']}")
    for field in ("extract_ms", "evaluate_ms", "total_ms"):
        values = sorted(float(row[field]) for row in rows)
        p50, p99 = (values[math.ceil(len(values) * percentile) - 1] for percentile in (0.50, 0.99))
        print(f"{field}: p50={p50:.3f}, p99={p99:.3f}, max={values[-1]:.3f}")
    print(f"CSV: {args.output}")


if __name__ == "__main__":
    main()
