"""Resolve the confirmed owner and current permissions for runner decisions."""

from __future__ import annotations

from datetime import datetime

from leash.contracts import Event, PolicyDraft
from leash.policy.ownership import owned_confirmations
from leash.policy.store import DraftStore, draft_hash

from . import api


class PolicyContextError(RuntimeError):
    """The stored confirmation or effective permissions cannot be established."""


def confirmation_record(store: DraftStore, mandate_id: str) -> dict:
    matches = []
    for folder in store.root.iterdir():
        if folder.is_dir() and (folder / "confirmation.json").is_file():
            record = store.get_confirmation(folder.name)
            if record["mandate_id"] == mandate_id:
                matches.append(record)
    if len(matches) != 1:
        raise PolicyContextError(f"{mandate_id}: expected one stored customer confirmation, found {len(matches)}")
    record = matches[0]
    if not isinstance(record.get("confirmed_by"), str) or not record["confirmed_by"]:
        raise PolicyContextError(f"{mandate_id}: confirmation lacks its customer identity")
    return record


def confirmation(store: DraftStore, mandate_id: str) -> tuple[dict, list[str]]:
    record = confirmation_record(store, mandate_id)
    owned = owned_confirmations(store, record["confirmed_by"])
    if mandate_id not in owned:
        raise PolicyContextError(f"{mandate_id}: confirmation owner does not own the mandate")
    draft = store.get(record["draft_id"])
    if draft["version"] != record["version"] or draft["hash"] != record["hash"]:
        raise PolicyContextError(f"{mandate_id}: confirmed draft version or hash changed")
    return record, sorted(owned)


def refresh(
    store: DraftStore, event: Event, *, deadline_at: datetime,
) -> tuple[Event, PolicyDraft]:
    """Read the effective policy under the caller's owned-mandate locks.

    The raw delivered event is kept by the caller for the accepted-result log.
    This copy supplies the current mandate restrictions to pure evaluation.
    """
    from leash.api.mandates import MandateEdits, _effective

    mandate_id = event.mandate.mandate_id
    record, _ = confirmation(store, mandate_id)
    draft = store.get(record["draft_id"])
    remote = api.call("GET", f"/v1/mandates/{mandate_id}", deadline_at=deadline_at)
    if (not isinstance(remote, dict) or remote.get("mandate_id") != mandate_id
            or remote.get("draft_id") != record["simulator_draft_id"]
            or remote.get("instruction") != draft["instruction"]):
        raise PolicyContextError(f"{mandate_id}: simulator mandate differs from its confirmation")
    edits = MandateEdits(store).read(mandate_id)
    effective = _effective(remote, draft, edits, record)
    effective_draft = {
        **draft,
        "rules": effective["rules"],
        "uncertainty_policy": effective["uncertainty_policy"],
        "version": record["version"] + edits["revision"],
        "hash": draft_hash(
            draft["instruction"], effective["rules"], effective["uncertainty_policy"],
            hash_version=draft["hash_version"], boundary_cases=draft.get("boundary_cases"),
        ),
    }
    policy = PolicyDraft.model_validate(effective_draft)
    data = event.model_dump(mode="python")
    data["mandate"] = {
        **data["mandate"], "status": remote["status"],
        "hard_rules": [rule.simulator_rule() for rule in policy.rules],
        "uncertainty_policy": policy.uncertainty_policy,
    }
    return Event.model_validate(data), policy
