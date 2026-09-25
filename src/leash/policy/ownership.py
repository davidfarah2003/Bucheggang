"""Customer ownership comes from immutable draft authorship and confirmations."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from .store import DraftStore, InvalidDraft


class ConfirmationSetChanged(RuntimeError):
    """The owned mandate set changed while its locks were acquired."""


@contextmanager
def customer_mandate_locks(store: DraftStore, customer: str) -> Iterator[dict[str, dict]]:
    """Lock a customer's owned set in the runner's customer-first order."""
    from leash.runner.records import customer_lock, mandate_locks

    with customer_lock(customer):
        confirmations = owned_confirmations(store, customer)
        mandate_ids = sorted(confirmations)
        deadline_at = datetime.now(UTC) + timedelta(seconds=30)
        with mandate_locks(mandate_ids, deadline_at=deadline_at):
            if owned_confirmations(store, customer) != confirmations:
                raise ConfirmationSetChanged("customer owned mandate set changed while acquiring locks")
            yield confirmations


def owned_confirmations(store: DraftStore, customer: str) -> dict[str, dict]:
    """Return this customer's confirmations keyed by mandate, rejecting duplicates."""
    if not customer:
        raise ValueError("authenticated customer identity is required")
    owned = {}
    seen = set()
    for folder in store.root.iterdir():
        if folder.is_dir() and (folder / "confirmation.json").is_file():
            record = store.get_confirmation(folder.name)
            mandate_id = record["mandate_id"]
            if not isinstance(mandate_id, str) or not mandate_id:
                raise RuntimeError(f"invalid mandate_id in confirmation {folder.name}")
            if not isinstance(record["confirmed_by"], str) or not record["confirmed_by"]:
                raise RuntimeError(f"invalid confirmed_by in confirmation {folder.name}")
            if mandate_id in seen:
                raise RuntimeError(f"multiple confirmations refer to mandate {mandate_id}")
            seen.add(mandate_id)
            if record["confirmed_by"] == customer:
                owned[mandate_id] = record
    return owned


def owned_drafts(store: DraftStore, customer: str) -> list[dict]:
    """Return drafts authored for this customer with their current lifecycle state."""
    if not customer:
        raise ValueError("authenticated customer identity is required")
    confirmations = owned_confirmations(store, customer)
    confirmed_by_draft = {record["draft_id"]: record for record in confirmations.values()}
    owned = []
    for folder in sorted(store.root.iterdir(), key=lambda path: path.name):
        if not folder.is_dir():
            continue
        draft_id = folder.name
        try:
            store._folder(draft_id)
        except InvalidDraft:
            continue
        draft = store.get(draft_id)
        owner = draft.get("created_for")
        if not isinstance(owner, str) or not owner or owner != customer:
            continue
        state = store.decision_state(draft_id)
        mandate_id = None
        if state == "confirmed":
            record = confirmed_by_draft.get(draft_id)
            if record is None or record.get("confirmed_by") != owner:
                raise RuntimeError(f"confirmation owner does not match draft {draft_id}")
            mandate_id = record["mandate_id"]
            item_state = "confirmed"
        elif state == "rejected":
            rejection = store.get_rejection(draft_id)
            if rejection.get("rejected_by") != owner:
                raise RuntimeError(f"rejection owner does not match draft {draft_id}")
            item_state = "rejected"
        else:
            try:
                pending = store.get_pending_confirmation(draft_id)
            except KeyError:
                item_state = "proposed"
            else:
                if pending.get("confirmed_by") != owner:
                    raise RuntimeError(f"pending confirmation owner does not match draft {draft_id}")
                item_state = "confirming"
        owned.append({"draft": draft, "state": item_state, "mandate_id": mandate_id})
    return owned
