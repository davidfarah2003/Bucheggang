# M2 behavioural-model comparison

Additional-pack purchases: 140,096. Frozen split: 400 fitting and 100 reserved customers, seed 20260924.
Base-pack customers never enter fitting, calibration or threshold proposals. Reserved customers' earlier outcomes only construct their own strictly pre-event profiles; they never fit parameters or choose a model, calibrator or cut.
Data loading and feature derivation: 26.74 seconds. Feature schema: hist-1, 50 numeric keys.
The refit majority class is approve, with constant-class accuracy 0.9404; table baseline Brier uses the refit decline prevalence 0.0596.
Only numeric HistoryFeatures.values enter the estimators. IDs and persona fields are grouping metadata, never predictors.

## May candidate comparison

Candidates fit on seen customers through April. May selects by PR-AUC with an LR tie-break.
| Slice | Rows | Declines | PR-AUC | ROC-AUC | Brier | Constant Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| lr | 10480 | 596 | 0.4722 | 0.7859 | 0.0389 | 0.0536 |
| catboost | 10480 | 596 | 0.5042 | 0.7844 | 0.0363 | 0.0536 |

Selected: `catboost`. Refit on seen customers through May, then calibrate on June 1-15.

## July evaluation

Reserved-customer rows lead as the primary generalization estimate. Seen-customer rows are selection-informed.
The issuer-rule-pass proxy uses recorded card status, online/international switches, transaction limit and reconstructed account calendar-month approved purchase spend. It is not a complete mandate-rule evaluation.
| Slice | Rows | Declines | PR-AUC | ROC-AUC | Brier | Constant Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| reserved: issuer-rule-pass proxy | 2551 | 91 | 0.0672 | 0.6593 | 0.0347 | 0.0350 |
| reserved: card lifecycle violation | 12 | 12 | unavailable | unavailable | 0.0001 | 0.8843 |
| reserved: all purchases | 2596 | 134 | 0.4329 | 0.7683 | 0.0354 | 0.0490 |
| reserved: agent purchases | 440 | 35 | 0.5053 | 0.7706 | 0.0503 | 0.0736 |
| reserved: human purchases | 2156 | 99 | 0.4083 | 0.7637 | 0.0324 | 0.0440 |
| reserved: zero prior customer approvals | 0 | 0 | unavailable | unavailable | unavailable | unavailable |
| reserved: low support 1-5 | 0 | 0 | unavailable | unavailable | unavailable | unavailable |
| reserved: new card, known customer | 1 | 0 | unavailable | unavailable | 0.0068 | 0.0036 |
| seen: issuer-rule-pass proxy | 10093 | 361 | 0.0709 | 0.6494 | 0.0352 | 0.0351 |
| seen: card lifecycle violation | 25 | 25 | unavailable | unavailable | 0.0013 | 0.8843 |
| seen: all purchases | 10345 | 603 | 0.5018 | 0.7869 | 0.0371 | 0.0549 |
| seen: agent purchases | 2037 | 165 | 0.5224 | 0.8227 | 0.0527 | 0.0749 |
| seen: human purchases | 8308 | 438 | 0.4942 | 0.7687 | 0.0332 | 0.0500 |
| seen: zero prior customer approvals | 0 | 0 | unavailable | unavailable | unavailable | unavailable |
| seen: low support 1-5 | 0 | 0 | unavailable | unavailable | unavailable | unavailable |
| seen: new card, known customer | 4 | 1 | unavailable | unavailable | 0.0073 | 0.2237 |

July zero-prior-approved customer rows are absent. Low-support and new-card slices are distinct. Slices below 30 rows or five outcomes per class have unavailable ranking metrics; sparse score bands do not claim calibration.
Sparse-slice Brier values are descriptive, not evidence of calibrated scores. Calibration by 0.1-wide score band for all, issuer-pass, agent and human slices, plus per-initiator July rates, is in model-manifest.json. Bands with fewer than 30 rows or five outcomes per class have no reported observed rate.

| Reserved July slice | Score band | Rows | Declines | Mean score | Observed decline rate |
| --- | --- | ---: | ---: | ---: | ---: |
| Issuer-rule-pass proxy | 0.0-0.1 | 2476 | 83 | 0.0245 | 0.0335 |
| Issuer-rule-pass proxy | 0.1-0.2 | 58 | 6 | 0.1252 | 0.1034 |
| Agent purchases | 0.0-0.1 | 411 | 20 | 0.0285 | 0.0487 |

The reserved agent 0.0-0.1 band underpredicts observed declines. Other reserved agent bands do not have enough outcomes for a calibration claim. No operational escalation threshold is selected from these July observations.

The same `hist-1` derivation was run on all 45 public agent attempts and 2,477 additional-pack July agent purchases. Median prior approved purchases were 119 card/212 customer for public attempts and 192 card/269 customer in July. `customer_merchant_last_approved_days` was missing on 8/45 public attempts (17.8%) and 63/2,477 July agent rows (2.5%). `card_category_amount_median_chf` was missing on 1/45 and 35/2,477. Device count was present for both samples. The public-attempt merchant mix differs from the offline evaluation population; these July metrics do not establish live calibration for that mix.

## June escalation proposals

These are evaluation points from June 16-30 only. No operational threshold is approved or enabled.
| Requested June rate | Score cut | Actual June rate | Decline recall | Agent rate | Agent recall | Human rate | Human recall |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.0100 | 0.8950 | 0.0101 | 0.1791 | 0.0185 | 0.2250 | 0.0081 | 0.1596 |
| 0.0200 | 0.4980 | 0.0202 | 0.3209 | 0.0329 | 0.4000 | 0.0171 | 0.2872 |
| 0.0500 | 0.0961 | 0.0500 | 0.4739 | 0.0782 | 0.5375 | 0.0433 | 0.4468 |
| 0.1000 | 0.0523 | 0.1001 | 0.5336 | 0.1595 | 0.6125 | 0.0859 | 0.5000 |

July reserved and seen rates at each unchanged June score cut are in model-manifest.json. July did not select a candidate or cut.

## Artifact and limits

Evaluation-only artifact SHA-256 `e4815c5677073c4e985c56f09f045be3d72c4e3ae624b75f9d06870630c828cf`. Manifest SHA-256 `3e9022aa98223d962e8beee29c0a5cbb0a10b093ff1a7fee916c6703b750ec0e`.
`BehaviorModel` loaded that artifact and scored real AU0035 history at 0.097382 with `escalation_fired=False`. It scored a real no-device historical row at 0.027787, and rejected `hist-0` with `purchase feature schema differs from model`. All 45 public attempts scored without activating escalation: minimum 0.0300, median 0.0499, maximum 0.2364. A missing or incompatible artifact stops loading; there is no score default or substitute model.
An initial fit showed identical probabilities on 1,000 historical rows and identical calibrator coefficients, although its serialized artifact hash differed. Its outputs were preserved at `/private/tmp/classifier-m2-initial-20260925/`; the reason for byte-level drift was not established. This report uses the second artifact and suppresses ranking metrics for slices with fewer than 30 rows or five outcomes per class.
`uv sync` without the classifier group imported the API, engine, extract, policy and runner modules while numpy, scikit-learn and CatBoost were absent. `uv sync --group classifier` restored the 21 optional packages. The `uv.lock` SHA-256 stayed `024e138fe65589d0582f694feebb3bd8ceb684510422bc68601b5d03cfcef6ae`.
Historical status is decline propensity, not an authorization recommendation. Model effects remain off pending owner threshold O4 and engine/runner integration.
No live simulator, app, customer answer or model-enabled decision was exercised by this fitting command.
