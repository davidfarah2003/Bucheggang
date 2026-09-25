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
    app_origin = os.environ.get("LEASH_APP_ORIGIN")
    if not app_origin:
        raise RuntimeError("LEASH_APP_ORIGIN must be the Wallet API origin")
    app = create_app(DraftStore(Path(store_root)), mandates, StepUpBook(), app_origin=app_origin)
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("LEASH_PORT", "8000")), access_log=False)


if __name__ == "__main__":
    main()
