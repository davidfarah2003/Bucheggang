# M1 history observation

Milestone target will be the commit containing this report and its feature code. M0 was cleared at `6cd4340` by Grok, Gemini and GLM. This report describes actual runs in the classifier worktree on 2026-09-25.

`HistoryIndex` reads both organizer packs and validates authorization ID uniqueness and the card, account and customer joins. It builds two profiles from records strictly before the purchase's `(timestamp, authorization_id)`. Live identity comes from the mandate. Approved purchases establish familiarity. Prior declines count toward attempt velocity. Refunds and cash withdrawals establish no purchase familiarity. The 50 numeric values, units, support counts and missing reasons are frozen in [feature-schema.md](feature-schema.md). An empty authorized profile is valid; failed source or ownership lookups raise.

`history_bundle()` computes those features and binds them to the authorization, mandate identity, event time and policy hash through a purchase digest. `validate_bundle()` rejects a mismatch before deterministic evaluation. This M1 replay explicitly has the model effect off. It calls the existing extraction and `evaluate()` functions after history construction. The engine-owned optional assessment argument and model checks remain an unmerged P1/P2 contract change; this run does not claim that the live runner calls the classifier.

Observed one-off commands and results:

| Run | Observation |
| --- | --- |
| `PYTHONPATH=src .venv/bin/python` over every additional-pack purchase via `HistoryIndex.historical_purchases()` | 140,096 purchase rows produced features in 26.68 s after loading the two packs; 500 approved and 42 declined purchases had no earlier approved customer purchase; zero timestamp mismatches. |
| `PYTHONPATH=src .venv/bin/python` over all 45 public attempts via `HistoryIndex.for_event()` | All 45 produced 50 values; customer merchant familiarity exceeded card familiarity on 36. AU0035 had card/customer merchant counts 6/8. |
| Real AU0035 event with a deliberately changed mandate customer ID | `ValueError: AU0035: mandate card does not belong to customer`. A historical purchase with an absent device yielded `None`, missing reason `no_device`. These were one-off checks in the shell, with no test file or suite. |
| `PYTHONPATH=src .venv/bin/python scripts/classifier_replay.py --policy SCEN0002=docs/samples/scen0002_draft.json --output docs/eval/classifier/m1-scen0002.csv` | 12 attempts: one `approve`, eleven `decline`, zero step-ups. The first approval was AU0012. Merchant familiarity was 22 card/34 customer for AU0012 through AU0021, then 0/0 on the two different-merchant attempts. |
| `PYTHONPATH=src .venv/bin/python scripts/replay.py --policy SCEN0002=docs/samples/scen0002_draft.json --output /private/tmp/classifier-m1-base-replay-20260925.csv` | 12 rows. Every authorization, decision and reason-code sequence matched the classifier replay. No customer answers or simulator requests occurred in either replay. |

The committed classifier replay CSV has SHA-256 `a4eb640a6643e1931d7bfe389ba8928623dd86d5af163f4a5b43cbbce78cf59f`. The known zero-history sentence in the frozen M0 document was over-broad: 542 additional-pack customer-scope purchases have no earlier approved purchase, all in the training window; July has none. The split manifest records that distinction.

Limits: only SCEN0002 has a supplied confirmed draft in `docs/samples/`; there is no 45-attempt decision table from this M1 command. The batch rows are additional-pack historical purchases, and the 45 attempts use base-pack customer histories. The live simulator, app/API path, model fitting, threshold and Jev decision composition were not exercised in this milestone run. P1/P2 engine integration is still needed before a model assessment can affect `evaluate()`.
