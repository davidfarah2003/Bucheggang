"""Classifier M0 evidence: which Jev model ids OpenRouter System One serves.

Sends one small choice question per model id given on the command line to
POST https://openrouter.ai/api/v1/systemone and prints the HTTP status, the
wall-clock latency and the response body without its request id. The body
uses catalogue fields only (no merchant text, no customer history).

The key is OPENROUTER_API from the .env of the main checkout (the parent of
git's common dir, so every worktree reads the same file). The script never
prints it. A missing file or key raises.

    uv run python scripts/classifier_m0_jev_probe.py typesafe/jev-1.13-20260917

Each id costs one provider call (about 420 tokens at the observed price).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

URL = "https://openrouter.ai/api/v1/systemone"
BODY = {
    "state": {
        "requested_item": "27-inch monitor",
        "cart_line_item_name": "27-inch computer monitor",
        "cart_line_category": "electronics",
    },
    "questions": {
        "same_product": {
            "type": "choice",
            "instructions": "Is the cart line the product the customer requested?",
            "criteria": {
                "same": "The cart line is the requested product.",
                "different": "The cart line is a different product.",
                "unclear": "The fields do not settle it.",
            },
        }
    },
}


def read_key() -> str:
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=Path(__file__).resolve().parent, capture_output=True, text=True, check=True,
    ).stdout.strip()
    path = Path(common).parent / ".env"
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip().removeprefix("export ").strip()
        if "=" in line and not line.startswith("#"):
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip('"').strip("'")
    return values["OPENROUTER_API"]


def main(models: list[str]) -> None:
    key = read_key()
    for model in models:
        start = time.perf_counter()
        response = httpx.post(URL, json=BODY | {"model": model}, headers={"Authorization": f"Bearer {key}"}, timeout=10.0)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if response.headers.get("content-type", "").startswith("application/json"):
            body = response.json()
            if isinstance(body, dict):
                body.pop("id", None)
        else:
            body = response.text[:300]
        print(f"requested={model} http={response.status_code} latency_ms={elapsed_ms:.0f}")
        print(json.dumps(body, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: classifier_m0_jev_probe.py <model id> [<model id> ...]")
    main(sys.argv[1:])
