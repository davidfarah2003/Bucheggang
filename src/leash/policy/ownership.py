"""Customer ownership comes from persisted app confirmations."""

from .store import DraftStore


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
    """Return drafts with an explicit confirmation, rejection or in-flight owner."""
    if not customer:
        raise ValueError("authenticated customer identity is required")
    confirmations = owned_confirmations(store, customer)
    confirmed_by_draft = {record["draft_id"]: record for record in confirmations.values()}
    owned = []
    for folder in sorted(store.root.iterdir(), key=lambda path: path.name):
        if not folder.is_dir():
            continue
        draft_id = folder.name
        draft = store.get(draft_id)
        state = store.decision_state(draft_id)
        mandate_id = None
        if state == "confirmed":
            record = confirmed_by_draft.get(draft_id)
            if record is None:
                continue
            mandate_id = record["mandate_id"]
            item_state = "confirmed"
        elif state == "rejected":
            rejection = store.get_rejection(draft_id)
            rejected_by = rejection.get("rejected_by")
            if not isinstance(rejected_by, str) or not rejected_by:
                raise RuntimeError(f"invalid rejected_by in rejection {draft_id}")
            if rejected_by != customer:
                continue
            item_state = "rejected"
        else:
            try:
                pending = store.get_pending_confirmation(draft_id)
            except KeyError:
                continue
            confirmed_by = pending.get("confirmed_by")
            if not isinstance(confirmed_by, str) or not confirmed_by:
                raise RuntimeError(f"invalid confirmed_by in pending confirmation {draft_id}")
            if confirmed_by != customer:
                continue
            item_state = "confirming"
        owned.append({"draft": draft, "state": item_state, "mandate_id": mandate_id})
    return owned
