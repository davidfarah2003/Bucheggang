# Classifier M1a r1 review

Verdict: APPROVE

This approves only the history and model-off replay cut at exact head `1f5a45da0d0b12d53ec4268de1f683052ce65fba`. It does not approve full M1, the engine-owned P1/P2 `evaluate(..., assessments=...)` integration, a live runner hookup, M2 fitting, or M3 Jev decision composition.

| Item | Value |
| --- | --- |
| Head | `1f5a45da0d0b12d53ec4268de1f683052ce65fba` |
| Parent | `d25b744fcb2adc82ecf0bfdc23a9fadf83d4a038` |
| Base | `6cd4340316c0ebc546a2c0f8ff6b147ef1688db8` (ancestor of head) |
| Design SHA-256 | `4d8ea6601aa2a23927a895b03ccd8e90ec8ae275da818dbc377d01e258409eb9` |
| Manifest | `docs/reviews/classifier/M1a/r1/MANIFEST.sha256`, 13 files OK before and after |
| Working tree | clean detached checkout `/private/tmp/classifier-m1a-r1-grok` |
| Reviewer | `classifier_review_grok_m1a` |
| Model pin | `grok-4.7`, from `cotal_orientation` and the session record |
| Requested effort | `high` (`reasoning_effort=high` on session `session_microbe_1790288292836_2a8739c2c5640a34`) |
| Accepted effort | Request accepted by the Jcode session. Provider usage does not expose a served reasoning tier, so this is not a claim about upstream token behaviour. |
| Provider catalog default | `JCODE_OPENROUTER_MODEL=gpt-5.6-sol` is the process default and was not the model used. |

Head and manifest were checked before inspection and again immediately before this report. No source, git state, or grading-tree file was edited.

## Findings

No blocker.

N1, low. `validate_bundle` binds authorization id, purchase digest, policy hash, event time, and mandate customer/card (`src/leash/engine/classifier/assess.py:37-48`). It does not bind `features.schema_version`, `values`, `missing`, or `support`. A bundle whose merchant count was set to 0 and schema set to `hist-0` was accepted. Failure scenario: a caller mutates the profile after `history_bundle()` and still passes validation. This does not change the model-off decision, because `scripts/classifier_replay.py:88` calls `evaluate(event, policy, state, facts)` and `src/leash/engine/evaluate.py:42-43` has no assessment argument. The purchase digest (`assess.py:14-23`) also hashes the full authorization, including untrusted `item_details` and `purchase_description`. That hash stays local. `jev.py:133-138` sends only numeric values, missing reasons, and support.

N2, low. `history.py:266` raises `KeyError` for a known card whose account limit is missing (`'CA0011'` after the limit entry was removed). Other source failures raise `ValueError` or `FileNotFoundError` with a path or authorization id. The missing limit still fails before a feature vector is returned. No score is substituted.

N3, non-blocking observation. The deterministic familiarity check still uses `leash.engine.data.History`, which orders by timestamp only (`src/leash/engine/data.py:60-69`), while hist-1 orders by `(timestamp, authorization_id)` (`history.py:163-170`). On this pack the two merchant, device, and country counts matched for all 4,565 base purchases: 0 mismatches. The pack has 0 same-timestamp groups, so the ordering difference is not exercised by the data. Equal keys would hide the earlier row because `bisect_left` stops at the first equal key (`history.py:170`). Load rejects a duplicate authorization id (`history.py:132-133`), and no real row shares a timestamp.

## What held

- Strict pre-event order. An independent running count of earlier approved purchases and earlier purchase attempts matched `HistoryIndex._features` for every additional-pack purchase: 0 mismatches across 140,096 rows. A synthetic same-timestamp pair `AUTH_A` then `AUTH_B` produced approved counts 0 and 1. A declined attempt exactly 10 minutes earlier was inside `attempt_count_10m`. An attempt one second older was outside that window and inside `attempt_count_1h`. The current row was excluded.
- Customer and card authorization. Load rejects a history row whose card, account, and customer disagree, a duplicate card, a customer in both packs, and a duplicate or empty authorization id. `for_event` rejects a mandate customer that does not own the card and an authorization card or mandate id that differs from the mandate (`history.py:258-265`). Observed: `AU0012: mandate card does not belong to customer`, `AU0012: authorization and mandate identity differ`. Customer scope was never smaller than card scope (71,967 greater, 68,129 equal, 0 less). Cross-card example `TR166728`: card approved count 0, customer approved count 95.
- Approved purchases only for familiarity. Refund `TR115302` had 1 prior refund and 21 prior approved purchases. The feature was 21. A synthetic approved refund at the current merchant did not add merchant familiarity. A prior cash withdrawal did not add familiarity, an attempt, or velocity. Declined `TR106015` was absent from a later approved count and present in the attempt count (13 approved, 14 attempts).
- Device. Blank-device purchase `TR100834` stored `None` with `no_device` on both device features (28,946 additional-pack rows). Unseen device `TR100037` stored count 0 and `no_prior_in_device`, distinct from `no_device`.
- Empty history. `TR100001` had customer approved count 0, `empty_history` on recency, and merchant count 0. Additional-pack customer-scoped zero-prior-approved purchases: 542 (500 approved, 42 declined), all `2025-09`, zero in July. That matches `feature-schema.md:29` and `m1-report.md:19`.
- Row-time card status. `TR100010` is `active` on the purchase row and `blocked` in today's `cards.csv`. `card_active_at_attempt` was 1. Across both packs, 8,456 purchase rows disagree with today's catalogue status, including 151 `expired` rows. Live events cannot carry `expired` (`event.py:58`). Historical rows can, and an unknown status raises (`history.py:173-174`).
- Predictors. The 50 keys match `feature-schema.md` in order. Identifiers, merchant names, descriptions, and persona fields are not in `values`. `recent_attempt_count_10m` is not a hist-1 key. On `AU0012` it was 0 and the historical 10-minute count was also 0, but they are separate fields.
- Limits. Live ratios use the base-pack account limits, not a history column. `AU0012` amount 165 against limits 1400 and 5000 gave ratios 0.11785714285714285 and 0.033. A nonpositive account limit, a naive timestamp, an unknown purchase status, and a missing pack file all raise. A zero-history or unseen category uses `None`, not an invented median.
- Percentile. Three prior amounts 10, 10, and 20 with current amount 10 gave percentile 0 and median 10. Equals are not counted as strictly below (`history.py:229-231`).
- SCEN0002. Recomputed 12 decisions and history columns matched `docs/eval/classifier/m1-scen0002.csv` with 0 mismatches. One approve (`AU0012`, card/customer merchant 22/34) and eleven declines. `AU0023` in isolation is `step_up` / `unfamiliar_merchant` because no prior mandate approval exists. In replay order it is `decline` / `purchase_count_exceeded` after `AU0012` is applied to mandate state. That is the existing one-approval rule, not a history leak, and it does not key a rule on the authorization id.
- Fail loud. Corrupt or unauthorized source reads raise before `evaluate`. The replay raises on a backwards scenario clock, a mismatched policy hash, a mismatched instruction, and a deadline that has already passed (`classifier_replay.py:50-53`, `79-80`, `90-91`).

## Commands actually run

Interpreter: `/Users/david/Projects/Bucheggang/.venv/bin/python`, with `PYTHONPATH=src` or `PYTHONPATH=src:scripts`. The grading tree has no `.venv`. No test file, suite, linter, provider call, or simulator call.

- `git rev-parse HEAD`, `git status --porcelain=v1`, `shasum -a 256 -c docs/reviews/classifier/M1a/r1/MANIFEST.sha256`, before and after.
- Full additional-pack `historical_purchases()` scan: 140,096 rows, 50 keys, 542 zero-prior-approved customer purchases, 0 July rows, 0 identity mismatches, 0 identifier predictors.
- Independent approved-count and attempt-count reconciliation against `_features`: 0 mismatches.
- Targeted probes for refund `CU1443`, decline, blank device, unseen device, cross-card scope, empty history, row-time status, synthetic same-timestamp order, and the 10-minute window.
- Temporary copies of the base pack outside the repo for duplicate authorization, ownership mismatch, unknown status, zero limit, and naive timestamp. Those directories were removed. The grading tree was not written.
- In-process SCEN0002 replay through `history_bundle`, `extract_event`, `validate_bundle`, and `evaluate`. Result matched the committed CSV.
- Rejection probes: swapped customer, card, mandate id, billing amount, policy hash, `as_of`, feature customer, and a cross-authorization bundle.
- Engine `History.merchant_count`, `device_count`, and `country_count` compared with hist-1 on all 4,565 base purchases: 0 mismatches.

## Limits

The recorded 45-attempt feature run was not repeated. Only SCEN0002 has a supplied draft, and that is the decision replay that was rerun. No model was fitted. Jev was not called. The live app and simulator were not run. `classifier_split.py` was read against `split-manifest.json` and not executed, because exclusive creation would fail on the existing manifest and writing a second file is outside this review. Its formal grading remains M2. `jev.py` was read only. Its request excludes merchant text and ids. Its formal grading remains M3.

A missing limit raises `KeyError` rather than `ValueError`. Validation does not hash the feature vector. Neither changes the model-off SCEN0002 outcome observed here.
