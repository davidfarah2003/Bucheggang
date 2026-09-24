"""Immutable local policy drafts and exact-version confirmation checks.

The customer app is the only caller permitted to record confirmation. This
module performs no authentication and never exposes that action to an agent.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


FIELDS = frozenset(
    {
        "authorization.billing_amount_chf",
        "authorization.items_subtotal",
        "authorization.delivery_fee",
        "authorization.currency",
        "authorization.channel",
        "authorization.fulfillment_method",
        "authorization.order_returnable",
        "authorization.merchant.merchant_id",
        "authorization.merchant.merchant_category",
        "authorization.merchant.merchant_mcc",
        "authorization.merchant.merchant_country",
        "items.category",
        "items.count",
        "facts.product_type",
        "facts.size",
        "facts.return_days",
        "facts.is_gift_card",
        "facts.is_subscription",
        "facts.is_protection_plan",
        "facts.is_addon",
        "history.merchant_seen_on_card",
        "history.device_seen_on_card",
        "state.approvals_count",
    }
)
OPERATORS = frozenset({"<", "<=", "=", "!=", ">", ">=", "in", "not_in"})
RULE_KEYS = frozenset(
    {"field", "operator", "value", "currency", "scope", "period_days", "source_text", "plain_english"}
)
SIMULATOR_RULE_KEYS = frozenset({"field", "operator", "value", "currency", "scope", "period_days"})
CURRENCIES = frozenset({"CHF", "EUR", "GBP", "USD"})
UNCERTAINTY_POLICIES = frozenset({"ask", "decline", "approve"})
EXAMPLE_ACTIONS = frozenset({"approve", "decline", "step_up"})


class InvalidDraft(ValueError):
    """The proposed policy does not fit the agreed contract."""


class DraftConflict(RuntimeError):
    """A customer is confirming an older or altered policy version."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(
        "utf-8"
    )


def draft_hash(instruction: str, rules: list[dict[str, Any]], uncertainty_policy: str) -> str:
    """Hash exactly the customer instruction and executable draft permissions."""
    return hashlib.sha256(
        _canonical({"instruction": instruction, "rules": rules, "uncertainty_policy": uncertainty_policy})
    ).hexdigest()


def _valid_value(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, str):
        return bool(value)
    return isinstance(value, list) and bool(value) and all(isinstance(v, str) and bool(v) for v in value)


def _validate_rule(rule: dict[str, Any], instruction: str) -> None:
    if set(rule) - RULE_KEYS:
        raise InvalidDraft(f"unknown rule fields: {sorted(set(rule) - RULE_KEYS)}")
    if rule.get("field") not in FIELDS:
        raise InvalidDraft(f"unsupported rule field: {rule.get('field')}")
    if rule.get("operator") not in OPERATORS:
        raise InvalidDraft("unsupported rule operator")
    if not _valid_value(rule.get("value")):
        raise InvalidDraft("rule value must be a finite number, nonempty string or nonempty string list")
    if "currency" in rule and rule["currency"] not in CURRENCIES:
        raise InvalidDraft("unsupported currency")
    if "scope" in rule and rule["scope"] not in {"purchase", "period"}:
        raise InvalidDraft("unsupported rule scope")
    if "period_days" in rule and (
        type(rule["period_days"]) is not int or rule["period_days"] < 1
    ):
        raise InvalidDraft("period_days must be a positive integer")
    if rule.get("scope") == "period" and "period_days" not in rule:
        raise InvalidDraft("period rules need period_days")
    source = rule.get("source_text")
    if not isinstance(source, str) or not source or source not in instruction:
        raise InvalidDraft("each rule must quote a phrase from the instruction")
    if not isinstance(rule.get("plain_english"), str) or not rule["plain_english"].strip():
        raise InvalidDraft("each rule needs a plain-English explanation")


def _validate_draft(
    instruction: str,
    rules: list[dict[str, Any]],
    uncertainty_policy: str,
    examples: list[dict[str, Any]],
    open_questions: list[dict[str, Any]],
) -> None:
    if not isinstance(instruction, str) or not instruction.strip():
        raise InvalidDraft("instruction is required")
    if not isinstance(rules, list) or not rules:
        raise InvalidDraft("at least one rule is required")
    for rule in rules:
        if not isinstance(rule, dict):
            raise InvalidDraft("every rule must be an object")
        _validate_rule(rule, instruction)
    if uncertainty_policy not in UNCERTAINTY_POLICIES:
        raise InvalidDraft("unsupported uncertainty policy")
    if not isinstance(examples, list):
        raise InvalidDraft("examples must be a list")
    for example in examples:
        if not isinstance(example, dict) or set(example) != {"description", "expected", "why"}:
            raise InvalidDraft("example shape is invalid")
        if example["expected"] not in EXAMPLE_ACTIONS:
            raise InvalidDraft("example action is invalid")
        if not all(isinstance(example[k], str) and example[k].strip() for k in ("description", "why")):
            raise InvalidDraft("example text is required")
    if not isinstance(open_questions, list):
        raise InvalidDraft("open_questions must be a list")
    for question in open_questions:
        if not isinstance(question, dict) or set(question) != {"question", "options", "answer"}:
            raise InvalidDraft("open question shape is invalid")
        if not isinstance(question["question"], str) or not question["question"].strip():
            raise InvalidDraft("question text is required")
        if not isinstance(question["options"], list) or not question["options"] or not all(
            isinstance(option, str) and option for option in question["options"]
        ):
            raise InvalidDraft("question options are required")
        if question["answer"] is not None and question["answer"] not in question["options"]:
            raise InvalidDraft("answer must be one of the options")


def simulator_payload(draft: dict[str, Any]) -> dict[str, Any]:
    """Return only fields accepted by the challenge mandate creation endpoint."""
    return {
        "instruction": draft["instruction"],
        "hard_rules": [
            {key: value for key, value in rule.items() if key in SIMULATOR_RULE_KEYS}
            for rule in draft["rules"]
        ],
        "uncertainty_policy": draft["uncertainty_policy"],
        "guidance": [],
        "open_questions": [],
    }


class DraftStore:
    """Single-host JSON store. Each version is an exclusive, immutable file."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _folder(self, draft_id: str) -> Path:
        try:
            canonical = str(UUID(draft_id))
        except (ValueError, TypeError) as exc:
            raise InvalidDraft("draft_id must be a UUID") from exc
        if canonical != draft_id:
            raise InvalidDraft("draft_id must use canonical UUID formatting")
        return self.root / draft_id

    @staticmethod
    def _write_exclusive(path: Path, value: dict[str, Any]) -> None:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def _audit(self, folder: Path, event: str, **details: Any) -> None:
        entry = {"event": event, "at": _now(), **details}
        descriptor = os.open(folder / "audit.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "ab") as stream:
            stream.write(_canonical(entry) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def create(
        self,
        instruction: str,
        rules: list[dict[str, Any]],
        *,
        uncertainty_policy: str = "ask",
        examples: list[dict[str, Any]] | None = None,
        open_questions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        examples = [] if examples is None else examples
        open_questions = [] if open_questions is None else open_questions
        _validate_draft(instruction, rules, uncertainty_policy, examples, open_questions)
        rules = json.loads(_canonical(rules))
        examples = json.loads(_canonical(examples))
        open_questions = json.loads(_canonical(open_questions))
        draft_id = str(uuid4())
        folder = self._folder(draft_id)
        folder.mkdir()
        draft = {
            "draft_id": draft_id,
            "version": 1,
            "hash": draft_hash(instruction, rules, uncertainty_policy),
            "instruction": instruction,
            "rules": rules,
            "examples": examples,
            "open_questions": open_questions,
            "uncertainty_policy": uncertainty_policy,
            "created_at": _now(),
        }
        self._write_exclusive(folder / "v1.json", draft)
        self._audit(folder, "draft_created", version=1, hash=draft["hash"])
        return draft

    def get(self, draft_id: str) -> dict[str, Any]:
        folder = self._folder(draft_id)
        versions = sorted((int(p.stem[1:]), p) for p in folder.glob("v[0-9]*.json"))
        if not versions:
            raise KeyError(draft_id)
        draft = json.loads(versions[-1][1].read_text())
        if draft["hash"] != draft_hash(draft["instruction"], draft["rules"], draft["uncertainty_policy"]):
            raise DraftConflict("stored draft hash does not match its contents")
        return draft

    def revise(
        self,
        draft_id: str,
        *,
        expected_version: int,
        expected_hash: str,
        rules: list[dict[str, Any]] | None = None,
        uncertainty_policy: str | None = None,
        examples: list[dict[str, Any]] | None = None,
        open_questions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        previous = self.assert_current(draft_id, expected_version, expected_hash)
        new_rules = rules if rules is not None else previous["rules"]
        new_policy = uncertainty_policy if uncertainty_policy is not None else previous["uncertainty_policy"]
        new_examples = examples if examples is not None else previous["examples"]
        new_questions = open_questions if open_questions is not None else previous["open_questions"]
        _validate_draft(previous["instruction"], new_rules, new_policy, new_examples, new_questions)
        revised = {
            **previous,
            "version": previous["version"] + 1,
            "hash": draft_hash(previous["instruction"], new_rules, new_policy),
            "rules": new_rules,
            "uncertainty_policy": new_policy,
            "examples": new_examples,
            "open_questions": new_questions,
            "created_at": _now(),
        }
        folder = self._folder(draft_id)
        try:
            self._write_exclusive(folder / f"v{revised['version']}.json", revised)
        except FileExistsError as exc:
            raise DraftConflict("another revision was saved first") from exc
        self._audit(folder, "draft_revised", version=revised["version"], hash=revised["hash"])
        return revised

    def assert_current(self, draft_id: str, version: int, hash_value: str) -> dict[str, Any]:
        draft = self.get(draft_id)
        if draft["version"] != version or draft["hash"] != hash_value:
            raise DraftConflict("draft version or hash changed; reload before confirming")
        folder = self._folder(draft_id)
        if (folder / "confirmation.json").exists():
            raise DraftConflict("draft was already confirmed")
        if (folder / "rejection.json").exists():
            raise DraftConflict("draft was rejected")
        return draft

    def record_confirmation(
        self,
        draft_id: str,
        *,
        version: int,
        hash_value: str,
        simulator_draft_id: str,
        mandate_id: str,
        confirmed_by: str,
    ) -> dict[str, Any]:
        draft = self.assert_current(draft_id, version, hash_value)
        if not simulator_draft_id or not mandate_id or not confirmed_by:
            raise InvalidDraft("simulator draft ID, mandate ID and confirmer are required")
        folder = self._folder(draft_id)
        record = {
            "draft_id": draft_id,
            "version": version,
            "hash": hash_value,
            "simulator_draft_id": simulator_draft_id,
            "mandate_id": mandate_id,
            "confirmed_by": confirmed_by,
            "confirmed_at": _now(),
        }
        try:
            self._write_exclusive(folder / "confirmation.json", record)
        except FileExistsError as exc:
            raise DraftConflict("draft was already confirmed") from exc
        self._audit(folder, "draft_confirmed", **record)
        return {"draft": draft, "confirmation": record}

    def get_confirmation(self, draft_id: str) -> dict[str, Any]:
        path = self._folder(draft_id) / "confirmation.json"
        if not path.exists():
            raise KeyError(draft_id)
        return json.loads(path.read_text())

    def reject(self, draft_id: str, *, version: int, hash_value: str, rejected_by: str, reason: str) -> None:
        self.assert_current(draft_id, version, hash_value)
        if not rejected_by:
            raise InvalidDraft("rejecter is required")
        folder = self._folder(draft_id)
        record = {
            "draft_id": draft_id,
            "version": version,
            "hash": hash_value,
            "rejected_by": rejected_by,
            "reason": reason,
        }
        try:
            self._write_exclusive(folder / "rejection.json", record)
        except FileExistsError as exc:
            raise DraftConflict("draft was already rejected") from exc
        self._audit(folder, "draft_rejected", **record)
