"""Measure merchant-text extraction on docs/samples/extract-corpus.jsonl.

Prints one table for the deterministic pass (leash.extract.extract_item):
per-field accuracy over the annotated fields, instruction detection recall on
the adversarial lines, and per-line latency p50 and p99.

    PYTHONPATH=src python3 scripts/measure_extract.py
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from leash.extract import extract_item

CORPUS = Path(__file__).resolve().parent.parent / "docs/samples/extract-corpus.jsonl"


def load() -> list[dict]:
    return [json.loads(line) for line in CORPUS.read_text().splitlines() if line.strip()]


def run(records: list[dict]) -> tuple[list[dict], list[float]]:
    results, latencies = [], []
    for record in records:
        start = time.perf_counter()
        results.append(extract_item(record["item"]))
        latencies.append(time.perf_counter() - start)
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
    results, latencies = run(records)
    scores = field_scores(records, results)

    rows = [(f"accuracy {field}", ratio(*scores[field])) for field in sorted(scores)]
    rows.append(
        ("accuracy all fields", ratio(sum(h for h, _ in scores.values()), sum(t for _, t in scores.values())))
    )
    rows.append(("instruction recall (adversarial)", ratio(*recall(records, results))))
    for q in (50, 99):
        rows.append((f"latency p{q} per line", f"{1000 * percentile(latencies, q):.3f} ms"))

    width = max(len(label) for label, _ in rows)
    print(f"corpus {CORPUS.name}: {len(records)} lines")
    print(f"{'metric':<{width}} | deterministic")
    print(f"{'-' * width}-|-{'-' * max(len(v) for _, v in rows)}")
    for label, value in rows:
        print(f"{label:<{width}} | {value}")


if __name__ == "__main__":
    main()
