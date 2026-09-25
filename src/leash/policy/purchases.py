"""Local purchases: a paired agent's cart judged by the Wallet under a confirmed mandate.

Contract: docs/contracts.md, "Purchase input and idempotency". The cart becomes the same
Event the engine judges for a simulator attempt, is evaluated by the configured evaluator
(pure engine, or the model evaluator when LEASH_ENABLE_MODELS=1), and is recorded through
leash.runner.records.recover_accepted with a local receipt in place of a simulator one.
A step_up goes into the StepUpBook with origin "local"; the Wallet answers it or the
book times it out. Nothing here calls the simulator.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from leash.contracts import Decision, Event, MandateState, PolicyDraft, PurchaseFacts, StepUp
from leash.engine import state as engine_state
from leash.policy.store import DraftStore, draft_hash
from leash.runner import records
from leash.runner.budget import DecisionBudget
from leash.runner.evaluation import ModelEvaluator, MODEL_RESERVE_S, load_evaluator
from leash.runner.loop import decide_with_guard
from leash.runner.stepups import StepUpBook, expires_at

PURCHASES_DIR = records.DATA_DIR / "purchases"
HISTORY_WINDOW_MINUTES = 1440
LOCAL_MODEL_CAP_S = 6.0


class InvalidPurchase(ValueError):
    """The purchase input, the mandate or the identity record is unusable."""


class PurchaseFailed(RuntimeError):
    """The Wallet could not produce a decision; nothing was recorded for this key."""


def _settings() -> tuple[float, float]:
    raw = os.environ.get("LEASH_PURCHASE_BUDGET_S")
    if not raw:
        raise InvalidPurchase("LEASH_PURCHASE_BUDGET_S is required for local purchases")
    budget = float(raw)
    if not budget > 0:
        raise InvalidPurchase("LEASH_PURCHASE_BUDGET_S must be positive")
    window = os.environ.get("LEASH_STEP_UP_WINDOW_S")
    if not window:
        raise InvalidPurchase("LEASH_STEP_UP_WINDOW_S is required for local purchases")
    return budget, float(window)


def _money(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidPurchase(f"{name} must be a number")
    if Decimal(str(value)).as_tuple().exponent < -2:
        raise InvalidPurchase(f"{name} has more than two decimals")
    return float(value)


def _mint_id() -> str:
    return "AGT" + base64.b32encode(secrets.token_bytes(8)).decode("ascii").rstrip("=")


def _identity(store: DraftStore, draft_id: str) -> dict[str, str]:
    path = store.root / draft_id / "identity.json"
    if not path.is_file():
        raise InvalidPurchase("mandate has no card on record")
    record = json.loads(path.read_text())
    for key in ("customer_id", "card_id", "profile_id"):
        if not isinstance(record.get(key), str) or not record[key]:
            raise InvalidPurchase(f"identity record lacks {key}")
    return {key: record[key] for key in ("customer_id", "card_id", "profile_id")}


def demo_identity() -> dict[str, str] | None:
    """The card a Wallet-confirmed mandate uses for local purchases, from LEASH_LOCAL_CARD_ID.

    The card and its customer come from the organizer's cards.csv and accounts.csv, so history
    checks and the classifier see the same rows as for a simulator attempt on that card.
    """
    import csv

    card_id = os.environ.get("LEASH_LOCAL_CARD_ID")
    if not card_id:
        return None
    root = Path(__file__).resolve().parents[3] / "viseca-2026" / "data"
    with (root / "cards.csv").open(newline="") as handle:
        cards = {row["card_id"]: row for row in csv.DictReader(handle)}
    with (root / "accounts.csv").open(newline="") as handle:
        accounts = {row["account_id"]: row for row in csv.DictReader(handle)}
    if card_id not in cards:
        raise InvalidPurchase(f"LEASH_LOCAL_CARD_ID {card_id} is not in cards.csv")
    customer_id = accounts[cards[card_id]["account_id"]]["customer_id"]
    return {"customer_id": customer_id, "card_id": card_id, "profile_id": f"local-profile-{customer_id}"}


def write_identity(store: DraftStore, draft_id: str, identity: dict[str, str], *, source: str) -> None:
    """Record the mandate's card identity.

    source is "simulator_event" (authoritative, from the first Event the runner accepts) or
    "demo_card" (provisional, from LEASH_LOCAL_CARD_ID at confirmation). A simulator identity
    replaces a provisional one; two simulator identities that differ raise; a provisional write
    never replaces anything.
    """
    if source not in ("simulator_event", "demo_card"):
        raise ValueError(f"unknown identity source {source!r}")
    path = store.root / draft_id / "identity.json"
    wanted = {key: identity[key] for key in ("customer_id", "card_id", "profile_id")}
    wanted["source"] = source
    if path.exists():
        current = json.loads(path.read_text())
        same = {key: current.get(key) for key in ("customer_id", "card_id", "profile_id")} == {k: wanted[k] for k in ("customer_id", "card_id", "profile_id")}
        if current.get("source") == "simulator_event":
            if source == "simulator_event" and not same:
                raise InvalidPurchase("mandate identity record differs from the delivered event")
            return
        if source == "demo_card":
            return
        records.write_atomic(path, wanted)
        return
    records.write_exclusive(path, wanted)


def _purchase_files(mandate_id: str) -> list[dict[str, Any]]:
    folder = PURCHASES_DIR / records._safe(mandate_id, "mandate_id")
    if not folder.is_dir():
        return []
    return [json.loads(path.read_text()) for path in sorted(folder.glob("*.json"))]


def _validate_input(purchase: dict[str, Any]) -> dict[str, Any]:
    allowed = {"mandate_id", "purchase_key", "cart", "merchant", "delivery_fee_chf", "total_chf", "facts"}
    unknown = set(purchase) - allowed
    if unknown:
        raise InvalidPurchase(f"unknown key {sorted(unknown)[0]}")
    missing = allowed - set(purchase)
    if missing:
        raise InvalidPurchase(f"missing key {sorted(missing)[0]}")
    key = purchase["purchase_key"]
    if not isinstance(key, str) or not 16 <= len(key) <= 64:
        raise InvalidPurchase("purchase_key must be 16 to 64 characters")
    cart = purchase["cart"]
    if not isinstance(cart, list) or not 1 <= len(cart) <= 50:
        raise InvalidPurchase("cart must hold 1 to 50 lines")
    lines = []
    subtotal = Decimal("0")
    for number, line in enumerate(cart, start=1):
        if not isinstance(line, dict):
            raise InvalidPurchase(f"cart line {number} is not an object")
        for name in ("item_id", "item_name", "item_category"):
            if not isinstance(line.get(name), str) or not line[name]:
                raise InvalidPurchase(f"cart line {number}: {name} is required")
        if not isinstance(line.get("item_details"), str):
            raise InvalidPurchase(f"cart line {number}: item_details must be a string")
        quantity = line.get("quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise InvalidPurchase(f"cart line {number}: quantity must be an integer of at least 1")
        price = _money(line.get("unit_price_chf"), f"cart line {number}: unit_price_chf")
        if price <= 0:
            raise InvalidPurchase(f"cart line {number}: unit_price_chf must be positive")
        subtotal += Decimal(str(price)) * quantity
        lines.append({"item_id": line["item_id"], "item_name": line["item_name"],
                      "item_category": line["item_category"], "item_details": line["item_details"],
                      "unit_price_chf": price, "quantity": quantity})
    merchant = purchase["merchant"]
    if not isinstance(merchant, dict):
        raise InvalidPurchase("merchant must be an object")
    for name in ("merchant_id", "merchant_name", "merchant_category", "merchant_city"):
        if not isinstance(merchant.get(name), str) or not merchant[name]:
            raise InvalidPurchase(f"merchant.{name} is required")
    mcc = merchant.get("merchant_mcc")
    if not isinstance(mcc, str) or len(mcc) != 4 or not mcc.isdigit():
        raise InvalidPurchase("merchant.merchant_mcc must be four digits")
    country = merchant.get("merchant_country")
    if not isinstance(country, str) or len(country) != 2 or not country.isalpha() or not country.isupper():
        raise InvalidPurchase("merchant.merchant_country must be an ISO 3166-1 alpha-2 code")
    extra = set(merchant) - {"merchant_id", "merchant_name", "merchant_category", "merchant_city", "merchant_mcc", "merchant_country"}
    if extra:
        raise InvalidPurchase(f"unknown merchant key {sorted(extra)[0]}")
    delivery = _money(purchase["delivery_fee_chf"], "delivery_fee_chf")
    if delivery < 0:
        raise InvalidPurchase("delivery_fee_chf must not be negative")
    total = _money(purchase["total_chf"], "total_chf")
    if total <= 0:
        raise InvalidPurchase("total_chf must be positive")
    if Decimal(str(total)) != subtotal + Decimal(str(delivery)):
        raise InvalidPurchase("total does not match the cart")
    facts_in = purchase["facts"]
    if not isinstance(facts_in, list) or len(facts_in) != len(lines):
        raise InvalidPurchase("facts must hold exactly one entry per cart line")
    facts = []
    for number, (line, raw) in enumerate(zip(lines, facts_in), start=1):
        try:
            fact = PurchaseFacts.model_validate(raw)
        except Exception as exc:
            raise InvalidPurchase(f"facts line {number}: {exc}") from exc
        if fact.item_id != line["item_id"]:
            raise InvalidPurchase(f"facts line {number}: item_id differs from the cart")
        if fact.conflicts:
            raise InvalidPurchase(f"facts line {number}: conflicts must be empty")
        if any(source != "agent_form" for source in fact.sources.values()):
            raise InvalidPurchase(f"facts line {number}: every source must be agent_form")
        facts.append(fact)
    return {
        "mandate_id": purchase["mandate_id"], "purchase_key": key, "cart": lines,
        "merchant": {name: merchant[name] for name in sorted(merchant)},
        "delivery_fee_chf": delivery, "total_chf": total,
        "items_subtotal": float(subtotal), "facts": facts,
    }


def _effective_policy(store: DraftStore, record: dict) -> PolicyDraft:
    from leash.api.mandates import MandateEdits, rules_hash
    from leash.contracts import Rule

    draft = store.get(record["draft_id"])
    global_rules = record.get("global_rules", [])
    if rules_hash(global_rules) != record.get("global_hash", rules_hash(global_rules)):
        raise PurchaseFailed("confirmation record global policy hash mismatch")
    edits = MandateEdits(store).read(record["mandate_id"])
    rules = [Rule.model_validate(rule).model_dump(mode="json") for rule in [*global_rules, *draft["rules"], *edits["rules"]]]
    policy = edits["uncertainty_policy"] or draft["uncertainty_policy"]
    effective = {
        **draft, "rules": rules, "uncertainty_policy": policy,
        "version": record["version"] + edits["revision"],
        "hash": draft_hash(draft["instruction"], rules, policy, hash_version=draft["hash_version"],
                           boundary_cases=draft.get("boundary_cases")),
    }
    return PolicyDraft.model_validate(effective)


def _build_event(validated: dict, *, device_id: str, identity: dict, policy: PolicyDraft,
                 mandate_status: str, now: datetime, budget_s: float, earlier: list[dict]) -> tuple[Event, str]:
    auth_id = _mint_id()
    ten_minutes = now - timedelta(minutes=10)
    day = now - timedelta(minutes=HISTORY_WINDOW_MINUTES)
    recent_count = 0
    recent = []
    for file in earlier:
        stamp = datetime.fromisoformat(file["timestamp"])
        if ten_minutes <= stamp < now:
            recent_count += 1
        decision = file.get("decision")
        if decision and day <= stamp < now:
            event = file["event"]
            status = {"approve": "approved", "decline": "declined", "step_up": "pending"}[decision]
            recent.append({
                "authorization_id": file["authorization_id"], "timestamp": stamp.isoformat(),
                "merchant_id": event["authorization"]["merchant"]["merchant_id"],
                "billing_amount_chf": event["authorization"]["billing_amount_chf"], "status": status,
            })
    items = [{
        "line_no": index, "item_id": line["item_id"], "item_name": line["item_name"],
        "item_category": line["item_category"], "quantity": line["quantity"],
        "unit_price": line["unit_price_chf"], "currency": "CHF", "item_details": line["item_details"],
    } for index, line in enumerate(validated["cart"], start=1)]
    data = {
        "type": "authorization.request",
        "request_id": "local-" + validated["file_name"],
        "deadline_at": (now + timedelta(seconds=budget_s)).isoformat(),
        "authorization": {
            "authorization_id": auth_id, "source_authorization_id": auth_id,
            "scenario_id": "SCEN0000", "replay_order": 1,
            "mandate_id": validated["mandate_id"], "profile_id": identity["profile_id"],
            "card_id": identity["card_id"], "initiator_type": "agent",
            "merchant": {**validated["merchant"], "availability": "online", "recurring_capable": "false"},
            "timestamp": now.isoformat(), "amount": validated["total_chf"], "currency": "CHF",
            "billing_amount_chf": validated["total_chf"], "items_subtotal": validated["items_subtotal"],
            "delivery_fee": validated["delivery_fee_chf"], "channel": "ecommerce",
            "customer_device_id": device_id, "authority_status": "active",
            "card_status_at_attempt": "active", "spend_in_period_before_chf": None,
            "recent_attempt_count_10m": recent_count, "fulfillment_method": "delivery",
            "delivery_by": None, "order_returnable": "unknown", "order_cancellable": "unknown",
            "related_authorization_id": None, "related_authorization_status": None,
            "purchase_description": policy.instruction, "items": items,
        },
        "mandate": {
            "mandate_id": validated["mandate_id"], "status": mandate_status,
            "customer_id": identity["customer_id"], "card_id": identity["card_id"],
            "instruction": policy.instruction,
            "hard_rules": [rule.simulator_rule() for rule in policy.rules],
            "uncertainty_policy": policy.uncertainty_policy, "profile_id": identity["profile_id"],
        },
        "context": {"approved_spend_in_period_chf": None, "recent_authorizations": recent},
        "runtime": {"received_at": now.isoformat(), "history_window_minutes": HISTORY_WINDOW_MINUTES,
                    "context_basis": "run_decisions_and_scenario_timestamps"},
    }
    return Event.model_validate(data), auth_id


class PurchaseDesk:
    """One per process. Loads the evaluator once; every buy runs under the mandate locks."""

    def __init__(self, store: DraftStore, book: StepUpBook | None = None):
        self.store = store
        self.book = book if book is not None else StepUpBook()
        self.evaluator = load_evaluator(cap_s=LOCAL_MODEL_CAP_S)

    @property
    def models_enabled(self) -> bool:
        return isinstance(self.evaluator, ModelEvaluator)

    def buy(self, agent: dict[str, Any], purchase: dict[str, Any]) -> dict[str, Any]:
        from leash.runner.coordinator import Coordinator
        from leash.runner.policy_context import PolicyContextError, confirmation

        budget_s, window_s = _settings()
        validated = _validate_input(purchase)
        mandate_id = validated["mandate_id"]
        agent_id = agent["agent_id"]
        digest = hashlib.sha256(f"{agent_id}:{mandate_id}:{validated['purchase_key']}".encode()).hexdigest()
        validated["file_name"] = digest
        canonical = {key: validated[key] for key in ("mandate_id", "cart", "merchant", "delivery_fee_chf", "total_chf")}
        canonical["facts"] = [fact.model_dump(mode="json") for fact in validated["facts"]]
        input_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        try:
            record, _ = confirmation(self.store, mandate_id)
        except PolicyContextError as exc:
            raise InvalidPurchase(f"mandate is not confirmed: {exc}") from exc
        if record["confirmed_by"] != agent["account_id"]:
            raise InvalidPurchase("mandate is not confirmed for this agent's account")
        identity = _identity(self.store, record["draft_id"])
        now = datetime.now(UTC)
        deadline = now + timedelta(seconds=budget_s)
        coordinator = Coordinator(self.store, self.book)
        with coordinator.locked(mandate_id, deadline_at=deadline) as mandate_ids:
            path = PURCHASES_DIR / records._safe(mandate_id, "mandate_id") / f"{digest}.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if saved["input_hash"] != input_hash:
                    raise InvalidPurchase("purchase_key was already used for a different purchase")
                if not saved.get("authorization_id"):
                    raise PurchaseFailed("this purchase_key failed earlier; use a new key")
                return self._status_of(saved["authorization_id"], mandate_id)
            policy = _effective_policy(self.store, record)
            from leash.runner import mandates as simulator_mandates

            remote = simulator_mandates.get(mandate_id, deadline_at=deadline)
            if not isinstance(remote, dict) or remote.get("mandate_id") != mandate_id:
                raise PurchaseFailed(f"{mandate_id}: simulator returned another mandate")
            if remote.get("status") != "active":
                raise InvalidPurchase(f"mandate is {remote.get('status')}")
            earlier = _purchase_files(mandate_id)
            # The agent is the device (contract: the paired agent_id, unique per pairing).
            device_id = agent_id
            event, auth_id = _build_event(validated, device_id=device_id, identity=identity, policy=policy,
                                          mandate_status="active", now=now, budget_s=budget_s, earlier=earlier)
            records.write_exclusive(path, {
                "purchase_key_file": digest, "agent_id": agent_id, "mandate_id": mandate_id,
                "input_hash": input_hash, "timestamp": now.isoformat(), "authorization_id": None,
                "decision": None, "event": event.model_dump(mode="json"),
            })
            state = engine_state.load(mandate_id, customer_mandates=mandate_ids)
            before = state.model_copy(update={"customer_approvals": []})
            budget = DecisionBudget.until(deadline)
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    decision = decide_with_guard(self.evaluator, event, policy, state, validated["facts"], pool, budget=budget)
            except Exception as exc:
                raise PurchaseFailed(f"{auth_id}: {type(exc).__name__}: {exc}") from exc
            accepted_at = datetime.now(UTC)
            records.recover_accepted(event, decision, accepted_at, {"origin": "local", "purchase_key_file": digest},
                                     resolution=False, state_before=before)
            if decision.decision == "step_up":
                step_up = StepUp(authorization_id=auth_id, decision=decision, event=event,
                                 expires_at=expires_at(accepted_at, window_s))
                records.write_atomic(self.book._path(mandate_id, auth_id), {
                    "step_up": step_up.model_dump(mode="json"), "status": "pending",
                    "resolution": None, "origin": "local",
                })
            saved = json.loads(path.read_text())
            saved["authorization_id"] = auth_id
            saved["decision"] = decision.decision
            records.write_atomic(path, saved)
            return self._status_of(auth_id, mandate_id)

    def _status_of(self, authorization_id: str, mandate_id: str) -> dict[str, Any]:
        detail = records.decision_detail(authorization_id)
        decision: Decision = detail["decision"]
        out = {
            "authorization_id": authorization_id, "mandate_id": mandate_id,
            "decision": decision.decision, "reason_codes": list(decision.reason_codes),
            "customer_message": decision.customer_message,
            "checks": [{"name": c.name, "result": c.result, "source": c.source, "note": c.note} for c in decision.evidence],
            "models_enabled": self.models_enabled,
        }
        if decision.decision == "step_up" or "customer_confirmation" in decision.reason_codes or "customer_declined" in decision.reason_codes or "step_up_timeout" in decision.reason_codes:
            path = self.book._path(mandate_id, authorization_id)
            saved = json.loads(path.read_text())
            out["step_up"] = {"status": saved["status"], "expires_at": saved["step_up"]["expires_at"]}
        return out

    def status(self, agent: dict[str, Any], authorization_id: str) -> dict[str, Any]:
        from leash.policy.ownership import owned_confirmations

        try:
            detail = records.decision_detail(authorization_id)
        except KeyError as exc:
            raise InvalidPurchase(f"unknown authorization_id: {authorization_id}") from exc
        mandate_id = detail["event"].mandate.mandate_id
        if mandate_id not in owned_confirmations(self.store, agent["account_id"]):
            raise InvalidPurchase(f"unknown authorization_id: {authorization_id}")
        return self._status_of(authorization_id, mandate_id)


def timeout_local_step_ups(store: DraftStore, book: StepUpBook) -> list[str]:
    """Decline every expired local step-up. Called by the Wallet API's sweeper."""
    done = []
    for path in book.root.glob("*/*.json"):
        saved = json.loads(path.read_text())
        if saved.get("origin") != "local" or saved.get("status") != "pending":
            continue
        step_up = StepUp.model_validate(saved["step_up"])
        if datetime.now(UTC) < step_up.expires_at:
            continue
        done.append(resolve_local(store, book, step_up, "decline", "You did not answer in time, so this purchase was declined.",
                                  reason="step_up_timeout"))
    return done


def resolve_local(store: DraftStore, book: StepUpBook, step_up: StepUp, outcome: str, message: str, *, reason: str) -> str:
    """Finish a local step-up with the customer's answer or a timeout. Caller may hold no locks."""
    from leash.runner.coordinator import Coordinator

    mandate_id = step_up.event.mandate.mandate_id
    auth_id = step_up.authorization_id
    coordinator = Coordinator(store, book)
    with coordinator.locked(mandate_id, deadline_at=datetime.now(UTC) + timedelta(seconds=30)) as mandate_ids:
        path = book._path(mandate_id, auth_id)
        saved = json.loads(path.read_text())
        if saved["status"] != "pending":
            return auth_id
        explanation = ("The customer approved this purchase in the Wallet." if outcome == "approve"
                       else "The customer declined this purchase in the Wallet." if reason == "customer_declined"
                       else f"No customer answer before {step_up.expires_at.isoformat()}; declined on timeout.")
        final = step_up.decision.model_copy(update={
            "decision": outcome, "reason_codes": [reason], "customer_message": message,
            "explanation": explanation, "decided_at": datetime.now(UTC),
        })
        before = engine_state.load(mandate_id, customer_mandates=mandate_ids).model_copy(update={"customer_approvals": []})
        accepted_at = datetime.now(UTC)
        accepted = {"origin": "local", "resolution": reason}
        records.recover_accepted(step_up.event, final, accepted_at, accepted, resolution=True, state_before=before)
        saved["status"] = "resolved"
        saved["resolution"] = {"decision": final.model_dump(mode="json"), "accepted": accepted, "accepted_at": accepted_at.isoformat()}
        records.write_atomic(path, saved)
    return auth_id
