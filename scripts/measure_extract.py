"""Measure merchant-text extraction on docs/samples/extract-corpus.jsonl.

Prints one table: per-field accuracy over the annotated fields, instruction
detection recall on the adversarial lines, and per-line latency p50 and p99.

Pass 1 (leash.extract.extract_item) always runs. The pass 1 plus 2 column
(leash.extract.extract_event_with_model with Swisscom Apertus) runs only when
APERTUS_API_KEY is set; otherwise the table says it was skipped. A model error
or timeout raises and stops the run.

    PYTHONPATH=src python3 scripts/measure_extract.py
    APERTUS_API_KEY=... PYTHONPATH=src python3 scripts/measure_extract.py
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from leash.extract import SwisscomFactClient, extract_event_with_model, extract_item

CORPUS = Path(__file__).resolve().parent.parent / "docs/samples/extract-corpus.jsonl"
DEADLINE_S = 8.0  # the challenge's default decision deadline from queueing


def load() -> list[dict]:
    return [json.loads(line) for line in CORPUS.read_text().splitlines() if line.strip()]


def run_pass1(records: list[dict]) -> tuple[list[dict], list[float]]:
    results, latencies = [], []
    for record in records:
        start = time.perf_counter()
        results.append(extract_item(record["item"]))
        latencies.append(time.perf_counter() - start)
    return results, latencies


def run_pass12(records: list[dict], client: SwisscomFactClient) -> tuple[list[dict], list[float]]:
    results, latencies = [], []
    for record in records:
        event = {"authorization": {"items": [record["item"]]}}
        deadline = datetime.now(timezone.utc) + timedelta(seconds=DEADLINE_S)
        start = time.perf_counter()
        (result,) = extract_event_with_model(event, model=client, deadline_at=deadline)
        latencies.append(time.perf_counter() - start)
        results.append(result)
    return results, latencies


def field_scores(records: list[dict], results: list[dict]) -> dict[str, tuple[int, int]]:
    scores: dict[str, tuple[int, int]] = {}
    for record, result in zip(records, results, strict=True):
        for field, expected in record["expected"].items():
            hit, total = scores.get(field, (0, 0))
            scores[field] = (hit + (result[field] == expected), total + 1)
    return scores


def recall(records: list[dict], results: list[dict]) -> tuple[int, int]:
    positives = [
        result["contains_instructions"]
        for record, result in zip(records, results, strict=True)
        if record["id"].startswith("adversarial-") and record["expected"].get("contains_instructions") is True
    ]
    return sum(positives), len(positives)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q / 100 * len(ordered)) - 1)]


def ratio(hit: int, total: int) -> str:
    return f"{hit}/{total} ({100 * hit / total:.1f}%)"


def main() -> None:
    records = load()
    columns: dict[str, tuple[list[dict], list[float]]] = {"pass 1": run_pass1(records)}
    key = os.environ.get("APERTUS_API_KEY")
    if key:
        columns["pass 1+2"] = run_pass12(records, SwisscomFactClient(key))

    fields = sorted({field for record in records for field in record["expected"]})
    rows: list[tuple[str, list[str]]] = []
    scored = {name: field_scores(records, results) for name, (results, _) in columns.items()}
    for field in fields:
        rows.append((f"accuracy {field}", [ratio(*scored[name][field]) for name in columns]))
    rows.append(
        (
            "accuracy all fields",
            [ratio(sum(h for h, _ in s.values()), sum(t for _, t in s.values())) for s in scored.values()],
        )
    )
    rows.append(("instruction recall (adversarial)", [ratio(*recall(records, r)) for r, _ in columns.values()]))
    for q in (50, 99):
        rows.append((f"latency p{q} per line", [f"{1000 * percentile(l, q):.3f} ms" for _, l in columns.values()]))

    headers = list(columns)
    if not key:
        headers.append("pass 1+2")
        rows = [(label, cells + ["skipped"]) for label, cells in rows]

    width = max(len(label) for label, _ in rows)
    cell = max(len(c) for _, cells in rows for c in cells + headers)
    print(f"corpus {CORPUS.name}: {len(records)} lines")
    print(f"{'metric':<{width}} | " + " | ".join(f"{h:<{cell}}" for h in headers))
    print(f"{'-' * width}-|-" + "-|-".join("-" * cell for _ in headers))
    for label, cells in rows:
        print(f"{label:<{width}} | " + " | ".join(f"{c:<{cell}}" for c in cells))
    if not key:
        print("pass 1+2 skipped: APERTUS_API_KEY is not set")


if __name__ == "__main__":
    main()
