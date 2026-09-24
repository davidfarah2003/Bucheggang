# Generate the evaluation report

Run from the repository checkout with Python 3.13 and `uv`:

```sh
uv run python scripts/report.py --output docs/eval/report-next.md
```

The default replay input is `docs/eval/replay-2026-09-25-all.csv`, a sequential run of all 45 public attempts. The script also discovers `docs/eval/live-*.csv` and runs the real deterministic extractor on `docs/samples/extract-corpus.jsonl`. It does not read `.env`, submit a simulator request, fit a model or resolve a customer question.

An existing output is refused. Choose a new filename, inspect the generated document, then update the checked-in report through the usual reviewed change. The committed `docs/eval/report.md` is one recorded result, not a file that changes when the application runs.

## Inputs

```sh
uv run python scripts/report.py \
  --replay docs/eval/replay-2026-09-25-all.csv \
  --live docs/eval/live-SCEN0135-2026-09-24.csv \
  --live docs/eval/live-SCEN0130-2026-09-24.csv \
  --live docs/eval/live-SCEN0106-2026-09-24.csv \
  --live docs/eval/live-SCEN0122-2026-09-24.csv \
  --output docs/eval/report-next.md
```

Each input must exist and have the required columns. Empty files, repeated authorization IDs, malformed rows, invalid outcomes and non-finite timings raise. A replay file must contain one mode, either sequential or independent. Separate reports keep those state assumptions separate. Negative extraction/evaluation durations are rejected; negative live submission headroom is retained because it would expose a late submission.

The report identifies its checkout revision and hashes the input CSVs, corpus, generator and extraction measurement source. Recorded replay timings belong to their input file. The extraction corpus is measured again when the report runs.

## Labels

With no `--labels`, the report says `Labels pending`. It does not search for another labels file or substitute observed engine decisions. Agreement, autonomous error and ordinary-purchase utility remain unavailable.

After a human reconciles the independent label files:

```sh
uv run python scripts/report.py \
  --labels docs/eval/labels.csv \
  --labels-mode sequential \
  --output docs/eval/report-labelled.md
```

Required columns are `authorization_id,expected,reason,notes`. Expected actions are `approve`, `decline` and `step_up`; every row needs a reason. Labels must cover exactly the replay IDs. Leading `#` documentation lines are accepted before the CSV header. The body must be valid CSV, with no trailing comment rows.

`--labels-mode` is the operator's explicit declaration of the labels' state assumptions. It must match the replay mode. The script cannot verify that the label authors followed those assumptions or that a human reconciled the file. Do not quote the provisional `labels-a.csv` or `labels-b.csv` comparisons as decision accuracy.

Autonomy is `(approve + decline) / attempts`. Autonomous error is action disagreement with the supplied labels divided by autonomous decisions. The report lists every action disagreement with the engine reasons, label reason and notes. A zero denominator is unavailable, not zero error.

## What the measurements cover

- The field table compares only annotated extraction fields. It does not establish product-name matching or provenance correctness.
- Injection outcomes cover public attempt IDs joined to cart lines annotated `contains_instructions=true`. They do not cover every attack type in the monitor scenario.
- Ordinary-purchase utility uses SCEN0000-SCEN0002 attempts labelled `approve`. It requires supplied labels.
- Replay latency measures local extraction and evaluation. It excludes startup, data loading, network calls and customer waiting.
- Live CSVs retain platform-only timeouts. Local timing percentiles include only the requests whose initial engine decision was recorded locally.
- Live submission headroom measures time remaining at submission. It is not end-to-end latency. A live end-to-end percentile remains unavailable until the runner records both ends of that interval.

The live reports include automated timeout resolutions that the simulator labels `human_confirmation`. Read their explanations before describing any of them as a customer answer. The complete Wallet journey and repeated live demo remain separate checks in [live-demo-checklist.md](live-demo-checklist.md).
