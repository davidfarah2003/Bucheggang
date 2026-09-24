# Offline replay

Run from the repository root with Python 3.13 and `uv`. No simulator key or network call is needed. The script uses the real `leash.extract.extract_event`, `leash.engine.evaluate`, and pure `leash.engine.state.apply` functions. It does not use a smoke evaluator or write live mandate state.

## Running shoes

```sh
uv run python scripts/replay.py \
  --policy SCEN0002=docs/samples/scen0002_draft.json
```

This evaluates the 12 supplied running-shoes attempts in delivery order. The default output is `docs/eval/replay-<UTC-date>.csv`. Choose `--output` for a subsequent run: existing reports are refused, never overwritten.

To assess each attempt with empty decision state:

```sh
uv run python scripts/replay.py \
  --policy SCEN0002=docs/samples/scen0002_draft.json \
  --mode independent --output docs/eval/shoes-independent.csv
```

Independent mode resets projected approvals and pending decisions between attempts. It retains the supplied transaction facts, including the fixture velocity counter and related-authorization status. It is an isolated assessment, not a completed scenario run.

## All public attempts

```sh
uv run python scripts/replay.py --all \
  --policy SCEN0000=docs/eval/replay-policies/SCEN0000.json \
  --policy SCEN0001=docs/eval/replay-policies/SCEN0001.json \
  --policy SCEN0002=docs/samples/scen0002_draft.json \
  --policy SCEN0003=docs/eval/replay-policies/SCEN0003.json \
  --policy SCEN0004=docs/eval/replay-policies/SCEN0004.json \
  --output docs/eval/replay-all.csv
```

`--all` requires an explicit draft for every scenario. It fails if one is missing. Without it, only the named scenarios run. The script verifies the draft hash using the policy package and requires its instruction to match the scenario instruction exactly.

The four drafts in `docs/eval/replay-policies/` were authored from the organizer's instructions with `DraftStore.create`. They are unconfirmed evaluation inputs. Every open question remains unanswered. They are not expected-decision labels or evidence of customer consent.

Assumptions encoded in these drafts:

- SCEN0000 treats one prior approved purchase on the card as evidence of a regularly used shop. Its open question records that interpretation. It permits one grocery unit and one successful purchase.
- SCEN0001 requires grocery cart lines and delivery. Its limits use the billed amount, which already includes delivery, and a rolling seven-day sum of projected approvals.
- SCEN0003 checks prior merchant use on the same card. An unanswered question records the possible wider customer scope. Session checks come from the engine's existing device, country and velocity checks.
- SCEN0004 preserves the instruction's literal product phrase, `27-inch monitor`. The chosen catalogue model is an unanswered question. The current extractor returns `27-inch computer monitor`, so exact equality fails. The replay does not change the policy wording to force an approval. It also limits the request to one unit and one successful purchase. Since 2026-09-25 it carries no `facts.is_addon = false` rule: extraction reports `is_addon` unknown on a line with no add-on marker, so that rule made every clean monitor line a step_up under `ask`. The engine's built-in add-ons check covers detected add-on lines.

## Event and state semantics

The script joins `purchase_attempts.csv`, `purchase_attempt_items.csv`, `merchants.csv`, `scenario_authorities.csv`, and `scenario_catalogue.csv` from the same supplied pack the engine uses for history. Scenario IDs select inputs; authorization IDs join rows. Neither is an answer key.

Each constructed event is validated against the strict `Event` contract. Cart-line numbers and authorization IDs must be unique. Every selected scenario must have its declared event count, a single authority/card identity, contiguous delivery positions, and nondecreasing simulated timestamps.

Fixture timestamps govern spending windows and recent authorizations. Each event gets a fresh real-clock receipt time and deadline. `--deadline-seconds` defaults to 8 for offline measurement; it does not claim a fresh live bootstrap value. A missed deadline raises an error instead of producing a substitute business decision.

Sequential replay treats engine approvals as projected accepted approvals in memory. Declines add no spend. Step-ups remain pending and add no spend. The script continues evaluating later rows while a step-up is pending; the live simulator instead pauses delivery until resolution. No API acceptance or customer answer is claimed by an offline row.

Recent authorizations use the preceding ten minutes of simulated time and projected decisions. A linked authorization already evaluated in this replay takes its status from that decision. The period-spend context is computed when the policy has exactly one period window; otherwise that optional counter is unknown. The engine applies each period rule directly to the full projected approval state.

Generated mandate, profile and request identifiers are marked `offline`. Fixture authorization IDs are preserved within the in-memory run. No state is saved under `data/state`, `data/stepups`, or the live decision-history store.

## Reports

The terminal shows each authorization, decision, reason codes and function time. The CSV also records projected spending and pending counts, draft hash/version, engine version, messages, explanations, and evidence.

Extraction and evaluation timings exclude process startup, reference-data loading, network submission and customer waiting. They are local function measurements, not end-to-end live latency or an accuracy score.

Observed on 2026-09-24:

| Run | Attempts | Approve | Decline | Step up | Maximum extract + evaluate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Shoes, sequential | 12 | 1 | 11 | 0 | 0.412 ms |
| Shoes, independent | 12 | 2 | 8 | 2 | 0.399 ms |
| All supplied scenarios, sequential | 45 | 11 | 32 | 2 | 0.605 ms |

The sequential shoes run approved AU0012 for CHF 165. Later attempts saw the one-purchase limit already consumed. With independent state, AU0016 asked for missing return terms and AU0023 asked about an unfamiliar merchant. In the full sequential replay, AU0026 and AU0040 stayed pending; neither was resolved by this script.

Recorded outputs are `docs/eval/replay-2026-09-24.csv`, `docs/eval/replay-2026-09-24-independent.csv`, and `docs/eval/replay-2026-09-24-all.csv`.
