# Evaluation report

Generated 2026-09-25T11:07:47.396121+00:00.

Checkout revision at generation: `53251c3c32b5690c79935b6dbd9c92994c451a6c`. Code hashes below identify the files used, including any uncommitted edits.
Generator: [report.py](../../scripts/report.py), SHA-256 `901d95a0ebb1e2141be4d10f5b03385d924d2ac2d301c7872a8f04000f8af5ca`.
Replay input: [replay-2026-09-25-all.csv](replay-2026-09-25-all.csv), SHA-256 `76a0c89ca07b1b7f3eaa232a8264a47981def6a6a9c46f8837957a44931bedaf`.
Mode: `sequential`. Engine versions in the recorded rows: leash-engine 0.5.

These are observed decisions under the recorded evaluation policies. Historical authorization status is not a fraud label, and an engine outcome is not an expected-decision label.

Labels supplied explicitly: [labels.csv](labels.csv), SHA-256 `7e2ef050423dc347e1aba3cb1d3f43b05f3d6e79d2a8244c800f7c6dc8b4b683`.
These are team-authored expectations, not an organizer answer key. Supplying a file does not establish human reconciliation. The operator declared that its state assumptions match the replay mode above.

## Decisions by scenario

| Scenario | Attempts | Approve | Decline | Step up | Autonomy | Label agreement | Autonomous error |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| SCEN0000 | 1 | 1 | 0 | 0 | 1/1 (100.0%) | 1/1 (100.0%) | 0/1 (0.0%) |
| SCEN0001 | 10 | 5 | 5 | 0 | 10/10 (100.0%) | 10/10 (100.0%) | 0/10 (0.0%) |
| SCEN0002 | 12 | 1 | 11 | 0 | 12/12 (100.0%) | 12/12 (100.0%) | 0/12 (0.0%) |
| SCEN0003 | 11 | 4 | 6 | 1 | 10/11 (90.9%) | 11/11 (100.0%) | 0/10 (0.0%) |
| SCEN0004 | 11 | 0 | 10 | 1 | 10/11 (90.9%) | 9/11 (81.8%) | 1/10 (10.0%) |
| Total | 45 | 11 | 32 | 2 | 43/45 (95.6%) | 43/45 (95.6%) | 1/43 (2.3%) |

Autonomy is the share initially approved or declined without a step-up. Autonomous error is disagreement with the supplied expected action among those autonomous decisions. A high autonomy rate alone says nothing about correctness.

## Disagreements

| Authorization | Observed | Expected | Engine reasons | Label reason | Label notes |
| --- | --- | --- | --- | --- | --- |
| AU0035 | decline | approve | item_mismatch | monitor at 289 from a seller bought from before | A and B agree. B: chosen monitor within terms |
| AU0040 | step_up | decline | item_mismatch\|injected_instructions | second monitor after AU0035 | sequential reading, one successful purchase per request. A=decline (monitor already approved so this is a second one); B=approve (chosen monitor within terms) |

## Injection handling and ordinary-purchase utility

2 replay attempts have a cart line annotated `contains_instructions=true` in the supplied extraction corpus: 1 declined, 1 escalated, 0 approved.
This covers the annotated merchant-instruction subset only. It does not label every manipulated, duplicate or lookalike purchase in SCEN0004.

| Annotated instruction attempt | Initial decision | Reasons |
| --- | --- | --- |
| AU0037 | decline | amount_over_limit |
| AU0040 | step_up | item_mismatch\|injected_instructions |

Among SCEN0000-SCEN0002 attempts labelled approve, approval without a question was 7/7 (100.0%).

## Deterministic extraction corpus

Measured now on 76 corpus lines: [extract-corpus.jsonl](../samples/extract-corpus.jsonl), SHA-256 `2b79cdbb9cad9ebe7aca27974cbe719d2bf99db799e4db7169f96625e2a31b66`.
Measurement code: [measure_extract.py](../../scripts/measure_extract.py), SHA-256 `b0bd332f86af70c407bf4302d62d3ed27f897575df16b347029337cb3c8d9381`.
Extractor: [facts.py](../../src/leash/extract/facts.py), SHA-256 `ebde8347417c54d48781ea89e2ba2609088d7bc30fc41abf7942a2eff637fd27`.

| Field | Agreement with annotated fields |
| --- | --- |
| contains_instructions | 64/64 (100.0%) |
| is_addon | 4/4 (100.0%) |
| is_gift_card | 3/3 (100.0%) |
| is_protection_plan | 3/3 (100.0%) |
| is_subscription | 1/1 (100.0%) |
| return_days | 39/39 (100.0%) |
| size | 31/31 (100.0%) |
| All annotated fields | 145/145 (100.0%) |
| Instruction recall on authored adversarial lines | 7/7 (100.0%) |

Only annotated fields contribute to these denominators. Product-name matching and composite provenance are not established by this corpus score.

## Local timing

Nearest-rank percentiles, in milliseconds. Recorded replay timings exclude process startup, reference-data loading, network submission and human waiting.

| Measurement | N | p50 ms | p99 ms | Maximum ms |
| --- | ---: | ---: | ---: | ---: |
| Recorded replay extract_ms | 45 | 0.041 | 0.084 | 0.084 |
| Recorded replay evaluate_ms | 45 | 0.317 | 1.029 | 1.029 |
| Recorded replay total_ms | 45 | 0.357 | 1.077 | 1.077 |
| Current corpus extraction per line | 76 | 0.010 | 0.047 | 0.047 |

## Live simulator evidence

| Source | Requests | Recorded locally | Platform-only | Final statuses |
| --- | ---: | ---: | ---: | --- |
| [live-SCEN0106-2026-09-24.csv](live-SCEN0106-2026-09-24.csv) | 12 | 12 | 0 | {'declined': 12} |
| [live-SCEN0122-2026-09-24.csv](live-SCEN0122-2026-09-24.csv) | 13 | 13 | 0 | {'declined': 13} |
| [live-SCEN0130-2026-09-24.csv](live-SCEN0130-2026-09-24.csv) | 13 | 13 | 0 | {'declined': 13} |
| [live-SCEN0135-2026-09-24.csv](live-SCEN0135-2026-09-24.csv) | 12 | 11 | 1 | {'declined': 11, 'timeout': 1} |

| Live logged measurement | N | Minimum ms | p50 ms | p99 ms |
| --- | ---: | ---: | ---: | ---: |
| extract_ms | 49 | 0.000 | 0.000 | 0.000 |
| evaluate_ms | 49 | 0.000 | 0.000 | 0.000 |
| ms_to_deadline_at_submit | 49 | 7016.000 | 7759.000 | 8035.000 |

Live extract/evaluate logs have integer-millisecond precision. Submission headroom is time remaining before the deadline, not request latency. These CSVs do not record a complete wall-clock end-to-end duration, so no live end-to-end percentile is claimed.
The simulator labels runner timeout `/resolve` calls as human confirmation. The live run reports identify those automated declines; that platform label does not prove a human answered.

Live input hashes:

- [live-SCEN0106-2026-09-24.csv](live-SCEN0106-2026-09-24.csv), SHA-256 `7cd732c52907a3fc86c2e4b0caf467175eb1fefd3f61d135b16c893a32d77e3a`
- [live-SCEN0122-2026-09-24.csv](live-SCEN0122-2026-09-24.csv), SHA-256 `eaab96178c5333c7f292f9f4b1135ab2abe60510fb12c2243de1b53959b543b9`
- [live-SCEN0130-2026-09-24.csv](live-SCEN0130-2026-09-24.csv), SHA-256 `520499012506e5497078729abaabba3670cb773d0b63dcabd64a2c2a1ed3b2c9`
- [live-SCEN0135-2026-09-24.csv](live-SCEN0135-2026-09-24.csv), SHA-256 `4946d1b2c8f064e066a81a38e5680995b38c215eb9266e8bf29782af1bd0ad59`

## Verification still required

- Reconcile independently drafted labels with a human before quoting agreement or error rates.
- Exercise a real customer answer in the Wallet and verify the same authorization's final simulator outcome.
- Verify queued-request behavior after revocation and changes to the effective policy.
- Run the complete live demo twice. Preserve the actual outcomes, including any failures.
- Validate the model-enabled classifier separately. This deterministic replay is not Jev or trained-model evidence.
