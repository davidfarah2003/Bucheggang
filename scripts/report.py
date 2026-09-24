"""Report observed replay outcomes, optional reconciled labels, and real-run timings.

    uv run python scripts/report.py
    uv run python scripts/report.py --labels docs/eval/labels.csv --labels-mode sequential --output docs/eval/report-labelled.md

No expected outcome is inferred from an engine decision. Without --labels,
agreement, autonomous error and ordinary-purchase utility remain unavailable.
An explicitly supplied missing or incomplete labels file raises.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import os
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from itertools import dropwhile
from pathlib import Path

from measure_extract import field_scores, load as load_corpus, recall, run as run_extract

ROOT = Path(__file__).resolve().parent.parent
OUTCOMES = {"approve", "decline", "step_up"}


def read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(dropwhile(lambda line: line.startswith("#") or not line.strip(), handle))
        header = reader.fieldnames
        if not header or len(header) != len(set(header)) or not required <= set(header):
            raise ValueError(f"{path}: missing or repeated columns; required: {sorted(required)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path}: no data rows")
    if any(None in row or None in row.values() for row in rows):
        raise ValueError(f"{path}: wrong number of CSV fields")
    return rows


def unique(rows: list[dict], field: str, path: Path) -> dict[str, dict]:
    result = {}
    for row in rows:
        identity = row[field]
        if not identity or identity in result:
            raise ValueError(f"{path}: empty or repeated {field}: {identity!r}")
        result[identity] = row
    return result


def number(value: str, path: Path, field: str, *, nonnegative: bool = True) -> float:
    result = float(value)
    if not math.isfinite(result) or (nonnegative and result < 0):
        raise ValueError(f"{path}: invalid {field}: {value!r}")
    return result


def percentile(values: list[float], percent: int) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percent / 100) - 1)]


def rate(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator} ({100 * numerator / denominator:.1f}%)" if denominator else "N/A (zero denominator)"


def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def source(path: Path, report: Path) -> str:
    relative = os.path.relpath(path.resolve(), report.parent.resolve())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"[{path.name}]({relative}), SHA-256 `{digest}`"


def make_report(replay_path: Path, labels_path: Path | None, live_paths: list[Path], output: Path,
                labels_mode: str | None) -> str:
    required = {"scenario_id", "authorization_id", "mode", "decision", "reason_codes",
                "extract_ms", "evaluate_ms", "total_ms", "engine_version", "draft_hash"}
    rows = read_csv(replay_path, required)
    by_id = unique(rows, "authorization_id", replay_path)
    modes = {row["mode"] for row in rows}
    if len(modes) != 1 or not modes <= {"sequential", "independent"}:
        raise ValueError(f"{replay_path}: one supported replay mode is required")
    if any(row["decision"] not in OUTCOMES for row in rows):
        raise ValueError(f"{replay_path}: invalid decision")
    mode = next(iter(modes))
    timing = {field: [number(row[field], replay_path, field) for row in rows]
              for field in ("extract_ms", "evaluate_ms", "total_ms")}
    labels = None
    if labels_path is not None:
        if labels_mode != mode:
            raise ValueError(f"{labels_path}: declared label mode {labels_mode!r} differs from replay mode {mode!r}")
        labels = unique(read_csv(labels_path, {"authorization_id", "expected", "reason", "notes"}),
                        "authorization_id", labels_path)
        if set(labels) != set(by_id):
            raise ValueError(f"{labels_path}: labels must cover the replay exactly; "
                             f"missing={sorted(set(by_id) - set(labels))}, extra={sorted(set(labels) - set(by_id))}")
        if any(row["expected"] not in OUTCOMES or not row["reason"].strip() for row in labels.values()):
            raise ValueError(f"{labels_path}: every label needs a valid expected outcome and a reason")
    groups = defaultdict(list)
    for row in rows:
        groups[row["scenario_id"]].append(row)
    revision = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    lines = ["# Evaluation report", "", f"Generated {datetime.now(UTC).isoformat()}.", "",
             f"Checkout revision at generation: `{revision}`. Code hashes below identify the files used, including any uncommitted edits.",
             f"Generator: {source(Path(__file__), output)}.",
             f"Replay input: {source(replay_path, output)}.",
             f"Mode: `{mode}`. Engine versions in the recorded rows: {', '.join(sorted({row['engine_version'] for row in rows}))}.",
             "", "These are observed decisions under the recorded evaluation policies. Historical authorization status is not a fraud label, and an engine outcome is not an expected-decision label.", ""]
    if labels is None:
        lines += ["Labels pending. No reconciled label file was supplied. Agreement, autonomous-decision error rate and ordinary-purchase utility are unavailable.", ""]
    else:
        lines += [f"Labels supplied explicitly: {source(labels_path, output)}.",
                  "These are team-authored expectations, not an organizer answer key. Supplying a file does not establish human reconciliation. The operator declared that its state assumptions match the replay mode above.", ""]
    lines += ["## Decisions by scenario", "",
              "| Scenario | Attempts | Approve | Decline | Step up | Autonomy | Label agreement | Autonomous error |",
              "| --- | ---: | ---: | ---: | ---: | --- | --- | --- |"]
    for scenario, items in [*sorted(groups.items()), ("Total", rows)]:
        counts = Counter(row["decision"] for row in items)
        autonomous = [row for row in items if row["decision"] != "step_up"]
        agreement = rate(sum(row["decision"] == labels[row["authorization_id"]]["expected"] for row in items), len(items)) if labels is not None else "labels pending"
        error = rate(sum(row["decision"] != labels[row["authorization_id"]]["expected"] for row in autonomous), len(autonomous)) if labels is not None else "labels pending"
        lines.append(f"| {scenario} | {len(items)} | {counts['approve']} | {counts['decline']} | {counts['step_up']} | "
                     f"{rate(len(autonomous), len(items))} | {agreement} | {error} |")
    lines += ["", "Autonomy is the share initially approved or declined without a step-up. Autonomous error is disagreement with the supplied expected action among those autonomous decisions. A high autonomy rate alone says nothing about correctness.",
              "", "## Disagreements", ""]
    if labels is None:
        lines.append("Unavailable until reconciled labels are supplied.")
    else:
        differences = [row for row in rows if row["decision"] != labels[row["authorization_id"]]["expected"]]
        if not differences:
            lines.append("No action disagreements with the supplied labels.")
        else:
            lines += ["| Authorization | Observed | Expected | Engine reasons | Label reason | Label notes |",
                      "| --- | --- | --- | --- | --- | --- |"]
            for row in differences:
                label = labels[row["authorization_id"]]
                lines.append("| " + " | ".join(cell(value) for value in [row["authorization_id"], row["decision"], label["expected"], row["reason_codes"], label["reason"], label["notes"]]) + " |")
    corpus = load_corpus()
    facts, latencies = run_extract(corpus)
    scores = field_scores(corpus, facts)
    positive_ids = {row["id"].rsplit("-", 1)[0] for row in corpus
                    if row.get("expected", {}).get("contains_instructions") is True}
    attacked = [row for row in rows if row["authorization_id"] in positive_ids]
    attack_counts = Counter(row["decision"] for row in attacked)
    lines += ["", "## Injection handling and ordinary-purchase utility", "",
              f"{len(attacked)} replay attempts have a cart line annotated `contains_instructions=true` in the supplied extraction corpus: "
              f"{attack_counts['decline']} declined, {attack_counts['step_up']} escalated, {attack_counts['approve']} approved.",
              "This covers the annotated merchant-instruction subset only. It does not label every manipulated, duplicate or lookalike purchase in SCEN0004."]
    if attacked:
        lines += ["", "| Annotated instruction attempt | Initial decision | Reasons |", "| --- | --- | --- |"]
        for row in attacked:
            lines.append("| " + " | ".join(cell(row[field]) for field in ("authorization_id", "decision", "reason_codes")) + " |")
        lines.append("")
    if labels is None:
        lines.append("Ordinary-purchase approval without a question is unavailable: the observed approvals cannot define which purchases should have been approved.")
    else:
        ordinary = [row for row in rows if row["scenario_id"] in {"SCEN0000", "SCEN0001", "SCEN0002"}
                    and labels[row["authorization_id"]]["expected"] == "approve"]
        lines.append("Among SCEN0000-SCEN0002 attempts labelled approve, approval without a question was "
                     + rate(sum(row["decision"] == "approve" for row in ordinary), len(ordinary)) + ".")
    lines += ["", "## Deterministic extraction corpus", "",
              f"Measured now on {len(corpus)} corpus lines: {source(ROOT / 'docs/samples/extract-corpus.jsonl', output)}.",
              f"Measurement code: {source(ROOT / 'scripts/measure_extract.py', output)}.",
              f"Extractor: {source(ROOT / 'src/leash/extract/facts.py', output)}.",
              "", "| Field | Agreement with annotated fields |", "| --- | --- |"]
    for field, (hit, count) in sorted(scores.items()):
        lines.append(f"| {field} | {rate(hit, count)} |")
    lines.append(f"| All annotated fields | {rate(sum(hit for hit, _ in scores.values()), sum(count for _, count in scores.values()))} |")
    hit, count = recall(corpus, facts)
    lines += [f"| Instruction recall on authored adversarial lines | {rate(hit, count)} |",
              "", "Only annotated fields contribute to these denominators. Product-name matching and composite provenance are not established by this corpus score.",
              "", "## Local timing", "",
              "Nearest-rank percentiles, in milliseconds. Recorded replay timings exclude process startup, reference-data loading, network submission and human waiting.",
              "", "| Measurement | N | p50 ms | p99 ms | Maximum ms |", "| --- | ---: | ---: | ---: | ---: |"]
    for field, values in timing.items():
        lines.append(f"| Recorded replay {field} | {len(values)} | {percentile(values, 50):.3f} | {percentile(values, 99):.3f} | {max(values):.3f} |")
    extract_ms = [value * 1000 for value in latencies]
    lines.append(f"| Current corpus extraction per line | {len(extract_ms)} | {percentile(extract_ms, 50):.3f} | {percentile(extract_ms, 99):.3f} | {max(extract_ms):.3f} |")
    lines += ["", "## Live simulator evidence", ""]
    if not live_paths:
        lines.append("No machine-readable live CSVs were found or supplied. Markdown-only live reports are not parsed into invented timing measurements.")
    else:
        all_live = []
        live_ids = set()
        lines += ["| Source | Requests | Recorded locally | Platform-only | Final statuses |",
                  "| --- | ---: | ---: | ---: | --- |"]
        for path in sorted(live_paths):
            live = read_csv(path, {"authorization_id", "initial_engine_decision", "final_platform_status", "local_final_decision", "finalized_at", "extract_ms", "evaluate_ms", "ms_to_deadline_at_submit"})
            indexed = unique(live, "authorization_id", path)
            if live_ids & set(indexed):
                raise ValueError(f"{path}: live authorization appears in more than one input file")
            live_ids.update(indexed)
            handled = sum(row["local_final_decision"] in OUTCOMES for row in live)
            lines.append(f"| [{path.name}]({os.path.relpath(path.resolve(), output.parent.resolve())}) | {len(live)} | {handled} | {len(live) - handled} | {cell(dict(Counter(row['final_platform_status'] for row in live)))} |")
            for row in live:
                if row["final_platform_status"] not in {"approved", "declined", "timeout"}:
                    raise ValueError(f"{path}: unknown final platform status")
                finalized = datetime.fromisoformat(row["finalized_at"])
                if finalized.tzinfo is None:
                    raise ValueError(f"{path}: finalized_at needs a timezone")
                if row["local_final_decision"] not in OUTCOMES | {"not handled"}:
                    raise ValueError(f"{path}: unknown local final decision")
                if row["initial_engine_decision"] not in OUTCOMES | {"not delivered locally"}:
                    raise ValueError(f"{path}: unknown initial decision")
                if row["initial_engine_decision"] in OUTCOMES:
                    all_live.append({field: number(row[field], path, field, nonnegative=field != "ms_to_deadline_at_submit")
                                     for field in ("extract_ms", "evaluate_ms", "ms_to_deadline_at_submit")})
        lines += ["", "| Live logged measurement | N | Minimum ms | p50 ms | p99 ms |", "| --- | ---: | ---: | ---: | ---: |"]
        for field in ("extract_ms", "evaluate_ms", "ms_to_deadline_at_submit"):
            values = [row[field] for row in all_live]
            if values:
                lines.append(f"| {field} | {len(values)} | {min(values):.3f} | {percentile(values, 50):.3f} | {percentile(values, 99):.3f} |")
        lines += ["", "Live extract/evaluate logs have integer-millisecond precision. Submission headroom is time remaining before the deadline, not request latency. These CSVs do not record a complete wall-clock end-to-end duration, so no live end-to-end percentile is claimed.",
                  "The simulator labels runner timeout `/resolve` calls as human confirmation. The live run reports identify those automated declines; that platform label does not prove a human answered."]
        lines += ["", "Live input hashes:", ""] + [f"- {source(path, output)}" for path in sorted(live_paths)]
    lines += ["", "## Verification still required", "",
              "- Reconcile independently drafted labels with a human before quoting agreement or error rates.",
              "- Exercise a real customer answer in the Wallet and verify the same authorization's final simulator outcome.",
              "- Verify queued-request behavior after revocation and changes to the effective policy.",
              "- Run the complete live demo twice. Preserve the actual outcomes, including any failures.",
              "- Validate the model-enabled classifier separately. This deterministic replay is not Jev or trained-model evidence.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--replay", type=Path, default=ROOT / "docs/eval/replay-2026-09-25-all.csv")
    parser.add_argument("--labels", type=Path, help="explicit reconciled labels matching the replay mode and IDs")
    parser.add_argument("--labels-mode", choices=["sequential", "independent"], help="required with --labels; declare their state assumptions")
    parser.add_argument("--live", type=Path, action="append", help="live outcome CSV; repeat for more runs")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/eval/report.md")
    args = parser.parse_args()
    if (args.labels is None) != (args.labels_mode is None):
        parser.error("--labels and --labels-mode must be supplied together")
    if args.output.exists():
        parser.error(f"report exists: {args.output}; choose a new --output path")
    live = args.live if args.live is not None else sorted((ROOT / "docs/eval").glob("live-*.csv"))
    content = make_report(args.replay, args.labels, live, args.output, args.labels_mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(content)
    print(f"Report: {args.output}")
    print("Labels: pending" if args.labels is None else f"Labels: {args.labels}")
    print(f"Live CSV inputs: {len(live)}")


if __name__ == "__main__":
    main()
