# Shared assessment bridge

This is the M1b model-off integration cut. The shared assessment contracts and pure `evaluate(..., assessments=...)` interface arrived on main through PR #47. The classifier producer now returns those shared types directly and uses `assessment_purchase_digest(event, features)`. The lane-local duplicate types were removed. A history bundle with `behaviour=None` and `semantic=None` enters the evaluator; it adds no model checks or decision effect.

## Observed runs

- `scripts/classifier_replay.py` ran with the five current supplied drafts after the main merge, passing every shared bundle to `evaluate()`. All 45 authorization, decision, reason and `hist-1` feature fields matched `docs/eval/classifier/m1-all-45.csv`: 11 approve, 32 decline, two step-up. The output is `/private/tmp/classifier-shared-replay-20260925.csv`, SHA-256 `d8903bba8ddc57270b691ae878048f0b145a8f2c3822340cc7131fa353f9be6f`.
- `HistoryIndex.historical_purchases("additional")` produced 140,096 strictly validated shared `HistoryFeatures` in 25.95 seconds. There were 542 purchases with no earlier approved purchase at customer scope and 46,759 rows with at least one undefined feature. No validation error occurred.
- An offline composition used the already captured real Jev answers for AU0001 from `docs/eval/classifier-composition-2026-09-25.json`. A shared bundle with the evaluation-only CatBoost score 0.029953 passed to the pure evaluator. Both baseline and assessed decisions approved with `within_policy`. Three model checks passed, and `escalation_fired=False`. Changing one feature value after scoring raised `ValueError: AU0001: assessment purchase digest differs`.
- Importing `scripts/classifier_fit.py` resolved `FEATURE_SCHEMA_VERSION` from the shared contract as `hist-1`. The fitted artifact was not regenerated.

The AU0001 semantic answers were captured by an earlier provider run. No provider or simulator request was made for this cut. The live runner still does not call `assess()`, and this model-off replay does not exercise customer answers, runner locks, accepted-result persistence or the live deadline. The behavioural artifact remains evaluation-only with no operating threshold. No test suite or linter was run.
