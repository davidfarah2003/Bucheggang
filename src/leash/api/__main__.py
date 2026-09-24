"""Run the same-origin Wallet API locally with ``python -m leash.api``."""

import os
from pathlib import Path

import uvicorn

from leash.policy.store import DraftStore
from leash.runner import mandates
from leash.runner.stepups import StepUpBook

from .main import create_app


def main() -> None:
    store_root = os.environ.get("LEASH_POLICY_STORE")
    if not store_root:
        raise RuntimeError("LEASH_POLICY_STORE must point to the policy MCP server's shared draft directory")
    app = create_app(DraftStore(Path(store_root)), mandates, StepUpBook())
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("LEASH_PORT", "8000")))


if __name__ == "__main__":
    main()
