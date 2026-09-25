"""Read-only preparation check for the model-off Wallet dry run.

    uv run python -m leash.runner.readiness --mandate-id TM...

Use the checkout, LEASH_POLICY_STORE and LEASH_APP_ORIGIN intended for the API,
MCP server and worker. LEASH_ENABLE_MODELS must be unset. Each completed check
prints PASS; the first failure prints FAIL and exits 1. No simulator request,
confirmation, customer answer or state write is made. A pass checks the local
confirmation record and matching Wallet HTML, not remote mandate status, the
server's private store configuration or the presence of a human at the Wallet.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import httpx

from leash.api.main import _validate_origin
from leash.policy.store import DraftStore

from . import policy_context, settings


class ReadinessError(RuntimeError):
    """A named local prerequisite was not satisfied."""


async def check_wallet(origin: str) -> None:
    expected = (Path(__file__).resolve().parents[3] / "app" / "index.html").read_bytes()
    async with asyncio.timeout(5):
        async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as client:
            async with client.stream("GET", f"{origin}/app/") as response:
                if response.status_code != 200:
                    raise ReadinessError(f"Wallet /app/ returned HTTP {response.status_code}, expected 200")
                if response.headers.get("content-type", "").split(";", 1)[0] != "text/html":
                    raise ReadinessError("Wallet /app/ did not return HTML")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > len(expected):
                        raise ReadinessError("Wallet /app/ differs from this checkout's index.html")
                if body != expected:
                    raise ReadinessError("Wallet /app/ differs from this checkout's index.html")


def check(mandate_id: str) -> None:
    stage = "LEASH_ENABLE_MODELS is unset"
    try:
        if "LEASH_ENABLE_MODELS" in os.environ:
            raise ReadinessError("unset LEASH_ENABLE_MODELS for the dry run, including an explicit 0")
        print(f"PASS {stage}", flush=True)

        stage = ".env simulator settings are present"
        settings.load()
        print(f"PASS {stage} (no simulator request)", flush=True)

        stage = "LEASH_APP_ORIGIN is an exact Wallet origin"
        origin, _ = _validate_origin(os.environ.get("LEASH_APP_ORIGIN"))
        print(f"PASS {stage}", flush=True)

        stage = "LEASH_POLICY_STORE resolves to an existing directory"
        configured_store = os.environ.get("LEASH_POLICY_STORE")
        if not configured_store:
            raise ReadinessError("LEASH_POLICY_STORE is required")
        root = Path(configured_store).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ReadinessError("LEASH_POLICY_STORE is not a directory")
        print(f"PASS {stage}", flush=True)

        stage = "Wallet /app/ matches this checkout"
        asyncio.run(check_wallet(origin))
        print(f"PASS {stage}", flush=True)

        stage = "selected mandate has a current owned local confirmation"
        policy_context.confirmation(DraftStore(root), mandate_id)
        print(f"PASS {stage}", flush=True)
    except Exception as exc:
        if isinstance(exc, (ReadinessError, settings.SettingsError, policy_context.PolicyContextError)):
            detail = str(exc)
        else:
            detail = type(exc).__name__
        raise ReadinessError(f"FAIL {stage}: {detail}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mandate-id", required=True, help="the actual demo mandate to check")
    args = parser.parse_args()
    try:
        check(args.mandate_id)
    except ReadinessError as exc:
        print(str(exc), flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
