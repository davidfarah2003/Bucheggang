# Jev public-input exercise

The full 45-input real-provider exercise did not pass. Two batches stopped on invalid probability distributions. The captured failure sums to 0.99, outside the agreed 0.000001 tolerance. The unchanged adapter raised an error and produced no substitute decision.

## Observed requests

| Execution | Real requests | Completed paired evaluations | Result |
| --- | ---: | ---: | --- |
| Initial batch | 7 | 6 | AU0007: `activity_pattern: probabilities do not sum to one`; the original response body was not captured |
| Separate diagnostic | 1 | 0 | Fresh AU0007 response passed the unchanged parser; this does not explain the original failure |
| Fresh batch with response recording | 36 | 35 | AU0036: `spend_pattern: probabilities do not sum to one`; response preserved |
| Total | 44 | 41 | Neither batch completed all 45 inputs |

There are 35 distinct successfully evaluated public inputs. The first six were evaluated in both batches. The diagnostic only exercised the provider parser. No simulator request, purchase submission, customer confirmation or step-up answer occurred.

The initial batch exited 1. Its six completed rows retained their baseline decisions: five approve and one decline. The fresh batch also exited 1. Its 35 completed rows retained their baseline decisions: 11 approve, 23 decline and one step_up. Five model checks were uncertain across those 35 rows; every behavioural escalation flag was false. Successful-prefix results do not establish the behaviour of the ten remaining inputs.

## Captured failure

The 36th response in the recorded batch served `typesafe/jev-1.13-20260917` from `TypeSafe`. It arrived in 337 ms. Its spend-pattern answer was:

```json
{
  "type": "choice",
  "choice": "ordinary",
  "probabilities": {
    "unusual": 0.14,
    "ordinary": 0.8,
    "unclear": 0.05
  },
  "confidence": 0.7
}
```

The exact decimal sum is 0.99. The floating-point sum is 0.9900000000000001. This failure is not explained by floating-point rounding at the validation boundary. The activity-pattern probabilities in that response sum to 1.0.

The adapter rejected the response before constructing a semantic assessment. The composed evaluator was not called for that row. The independent deterministic baseline had already been computed for comparison; it was not returned as a replacement model-enabled result. No probability was normalized, no tolerance changed, and no request was retried inside either batch.

The separate diagnostic request followed the first failed batch. Its spend distribution was ordinary 0.89, unusual 0.06 and unclear 0.05. Its activity distribution was ordinary 0.81, unusual 0.17 and unclear 0.02. Both summed to 1.0. A fresh passing response cannot recover the original failing response.

## Revisions and execution

| Component | Frozen input |
| --- | --- |
| Shared contracts, extraction and pure evaluator | `71f119c65b880adbd5fff01ea646b69e41b20767` |
| Standalone classifier producer | `0940fd759ec6eb42d416ecd02e828be83b78bcbd` |
| Actual CatBoost artifact SHA-256 | `e4815c5677073c4e985c56f09f045be3d72c4e3ae624b75f9d06870630c828cf` |
| Libraries | CatBoost 1.2.10, NumPy 2.5.3, scikit-learn 1.9.1 |
| Requested and served model | `typesafe/jev-1.13-20260917` |
| Provider restriction | `only: ["typesafe"]`, `allow_fallbacks: false` |
| Behavioural release status | `evaluation_only_no_operational_threshold` |

The producer's `assess.py`, `behaviour.py`, `history.py`, `jev.py` and `types.py` hashes all matched its saved M3a/r1 manifest. The artifact loader checked the actual file hash, split-manifest hash, library versions and feature names. It loaded 50 features. No operational threshold was selected.

This was an explicit two-revision compatibility exercise. The producer still used lane-local assessment classes. The driver converted its output with `leash.contracts.AssessmentBundle.model_validate(...)` before invoking the merged evaluator. A pre-dispatch history-only bundle was validated and its feature-bound digest checked against the canonical shared helper. No claim is made that this producer was already integrated into the runner.

The driver reused `scripts/replay.py` input parsing and event construction, the five explicit policies in [run-replay.md](../run-replay.md), the actual extractor, both-pack history, the fitted model, the real Jev adapter and the pure evaluator. Scenario IDs selected inputs. They did not select outcomes.

Each pair used the same event, facts and baseline-projected state. Only the deterministic baseline advanced the in-memory sequential state. Step-ups remained pending. This isolates the effect of the model assessments at those states; it does not simulate a model-enabled live run's evolving decisions or customer waiting.

Requests were serial, limited to one start per second. Each event received a fresh eight-second offline deadline. Only feature schema, numeric values, missingness and support were sent as provider state. Raw merchant text, agent justifications and customer/card identifiers were excluded from that state. The scoped OpenRouter accessor read the provider credential; the simulator settings accessor was not called by the driver.

The recorded batch added a local response-recording wrapper around the unchanged parser. It saved the actual bounded response body and then called that parser. It did not alter responses or catch validation errors. The first driver and both failed runs remain preserved separately in ignored local evidence.

Execution used the frozen producer's installed Python environment:

```text
python .cotal/jev_public_evaluation.py
  exit 1 after 6 evaluated rows, request 7 rejected
python .cotal/jev_probability_diagnostic.py
  exit 0, one separate real request
python .cotal/jev_public_evaluation_recorded.py
  exit 1 after 35 evaluated rows, request 36 rejected
```

These local drivers are not shipped runtime modes or test suites. No linter or test suite was run.

## Timings and coverage

For the 35 successful paired evaluations in the recorded batch:

| Measurement | p50 | p99 and maximum |
| --- | ---: | ---: |
| Jev request through body receipt | 306 ms | 727 ms |
| Extraction, baseline, history checks, fitted model, Jev and composed evaluation | 313.311 ms | 731.209 ms |

Minimum remaining offline deadline was 7268.691 ms. The timings exclude startup, history/artifact loading, the inter-request rate limit, simulator submission and customer waiting. The p99 uses nearest rank on only 35 successful rows. Failed rows are excluded from these latency percentiles and recorded above.

A separate full `scripts/replay.py --all` invocation at the frozen core completed all 45 public inputs: 11 approve, 32 decline and two step_up. Its local extraction/evaluation p50 was 0.239 ms and p99/max was 0.421 ms. That model-off replay does not clear the failed provider exercise.

## Evidence and remaining work

- [Initial six completed pairs](jev-public-2026-09-25-initial.csv).
- [Recorded batch's 35 completed pairs](jev-public-2026-09-25-recorded.csv).
- [Revision hashes, diagnostic response and captured invalid response](jev-public-2026-09-25-evidence.json).

The non-normalized provider response remains unresolved. Keep the strict validation and the model-enabled release gate. A later successful full exercise must retain this failure evidence and name its own source revisions. Runner startup integration, operating-threshold selection and a real human Wallet journey remain separate unfinished work. These observations are not an accuracy estimate or live end-to-end payment latency.
