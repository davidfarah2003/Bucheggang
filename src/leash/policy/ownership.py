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
