# Production model evaluator: 45 public purchases

On 25 September 2026, the production `ModelEvaluator` completed the public 45-purchase replay with real Jev requests and the committed CatBoost artifact. The measured source was `5601dffb60dddfa2b93f279faccda66667d77e7f`.

| Observation | Result |
| :--- | ---: |
| Completed inputs | 45 |
| Purchases assessed by CatBoost and Jev | 13 |
| Hard policy failures, model calls skipped | 32 |
| Approve | 11 |
| Decline | 32 |
| Customer review | 2 |
| Decision or reason differences from the deterministic baseline | 0 |
| Retries | 0 |
| Simulator submissions | 0 |
| Customer answers | 0 |

The 13 modelled purchases took 310.397-806.589 ms through extraction and the guarded evaluator. All returned the pinned Jev model, `typesafe/jev-1.13-20260917`. Each response supplied spending and activity distributions, and both selected `ordinary` in this run. The CatBoost scores ranged from 0.0299532 to 0.0997228. No model check escalated; this run does not exercise an above-threshold model outcome.

## Configuration and scope

The run used the settings currently selected by the demo launch scripts: a 20-second purchase budget, a six-second model-stage cap and a CatBoost review threshold of 0.498. This measurement made no new threshold-selection decision. The optional classifier dependencies matched the model manifest.

`decide_with_guard` called the production evaluator for each purchase. Hard policy failures returned before model dispatch. Successful model responses passed the current provider, distribution and purchase-binding validation. The client did not renormalize probabilities, retry a failed call or substitute another model. Current validation permits the documented provider-rounding tolerance; this is not the earlier strict-sum configuration.

The purchase inputs came from the public data pack. Approvals were projected into in-memory replay state, and step-ups remained pending. No simulator run, persisted purchase, Wallet confirmation or customer answer was created. These results cover the evaluation path with real model calls. They do not establish complete MCP transport, purchase recovery or human Wallet verification. The earlier failed batches used a different probability-sum contract and remain in their original evidence record. The evaluation-label choice is still pending.

## Evidence

- [Run manifest and source hashes](model-runtime-2026-09-25.json)
- [All 45 outcomes and model outputs](model-runtime-2026-09-25.csv)
- [Measurement driver](../../scripts/measure_model_runtime.py)
- [Earlier provider exercises and failures](jev-public-2026-09-25.md)

To repeat the measurement with the configured OpenRouter credential:

```sh
uv sync --group classifier
uv run --no-sync python scripts/measure_model_runtime.py
```

This command makes real provider requests and creates a new evidence directory under `.cotal/`. The scoped runner accessor reads the existing `OPENROUTER_API` configuration. It does not use an Anthropic credential. A dependency, provider or validation error terminates the run and leaves its completed rows and failure summary on disk.
