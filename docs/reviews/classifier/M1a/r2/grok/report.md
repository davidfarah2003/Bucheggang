# Classifier M1a r2 review

Verdict: APPROVE

This approves the correction at exact head `e9974121fc47320dc7fabb9ddb280a517d1116cc` as a history and model-off replay cut. It does not approve full M1, engine-owned P1/P2 integration, the live runner, M2 fitting, or M3 Jev use.

| Item | Value |
| --- | --- |
| Head | `e9974121fc47320dc7fabb9ddb280a517d1116cc` |
| Parent | `96cce47577ef82998523039513c145c0ef3fd56c` |
| Base | `498898155272e17b9907c364d723a503541ad6fc` |
| Preceding r1 target | `1f5a45da0d0b12d53ec4268de1f683052ce65fba`, ancestor of head |
| Design SHA-256 | `4d8ea6601aa2a23927a895b03ccd8e90ec8ae275da818dbc377d01e258409eb9`, unchanged |
| Manifest | `docs/reviews/classifier/M1a/r2/MANIFEST.sha256`, 25 files OK before and after |
| Working tree | clean detached checkout `/private/tmp/classifier-m1a-r2-grok` |
| Reviewer | `classifier_review_grok_m1a` |
| Model pin | `grok-4.7` |
| Requested effort | `high` |
| Accepted effort | Session record `reasoning_effort=high` on `session_microbe_1790288292836_2a8739c2c5640a34`. Provider usage does not expose a served reasoning tier. |
| r1 report | `/private/tmp/classifier-review-reports/M1a/r1/grok/report.md` unchanged, SHA-256 `875c7b9358e015b826b5193fd6e2838a3544feee65346d84a72113e309cd9e3e` |

## r1 findings

N1 is fixed. `purchase_digest` now hashes the full `HistoryFeatures` map with the authorization and mandate identity (`src/leash/engine/classifier/assess.py:14-24`). `validate_bundle` recomputes that digest from the bundle features (`assess.py:42-43`). On AU0035, changing `card_merchant_approved_count` from 6 to 999 raised `ValueError: AU0035: assessment purchase digest differs`. Changing `schema_version` to `hist-0` raised the same error. The real AU0035 bundle validated and kept card/customer merchant counts 6/8. The digest remains local. The report states it is an integrity check, not caller authentication (`m1-report.md:7`).

N2 is fixed. A card with no account-limit entry now raises `ValueError: AU0035: account limits unavailable for mandate card` (`history.py:268-270`). No feature vector is returned.

N3 stays an engine-owned ordering difference. hist-1 still uses `(timestamp, authorization_id)`. This correction does not change `src/leash/engine/data.py`. No new same-timestamp rows were introduced by the classifier diff.

## Other correction checks

- Purchase initiator domain. Real packs contain purchase/human 125,171, purchase/agent 19,490, cash_withdrawal/human 2,757, and refund/merchant 1,957. No purchase row is merchant-initiated. A copied base pack with one purchase initiator set to `merchant` raised `ValueError: TR00001: unsupported purchase initiator type 'merchant'` at `history.py:141-142`. Merchant refunds still load. The schema says the same thing (`feature-schema.md:25`). This fail-loud domain is adequate before M2 fitting.
- Replay order. `classifier_replay.py:79-81` rejects a scenario key that does not strictly advance. Equal keys fail the `<=` check. The 45 public attempts advanced.
- 45-attempt replay. In-process replay through `history_bundle`, `validate_bundle`, `extract_event`, and `evaluate` produced 11 approve, 32 decline, and 2 step_up. All 45 authorization, decision, reason-code, and history columns matched `docs/eval/classifier/m1-all-45.csv`. CSV SHA-256 `fd9ea6a52795969c96a571eb13ac470907746d9fcd253fdaa97612925f7df3ee`. SCEN0002 decisions are unchanged from r1. `evaluate` still has no assessment argument (`classifier_replay.py:89`), so this remains model-off.
- Split manifest. The only change is the feature-schema hash, now `91fab4bf5951054e034d2c51354342bd42c47bba8c10e2d212002925fc6b3314`, matching the corrected schema file. Seed and membership were not edited in the diff. The split script itself is unchanged.
- Dependencies. `pyproject.toml:17-22` adds an optional `classifier` group: numpy, scikit-learn, and catboost. No fitting call or live model effect is in this target.
- `jev.py` is byte-identical to r1. It still reads the shared `.env` for `OPENROUTER_API` (`jev.py:54-71`). That credential boundary remains an M3 gate, as the findings list says. This cut does not call it. I did not open `.env`.

The deadline check still runs after synchronous work (`classifier_replay.py:91-92`). That matches the recorded disposition: keep the `TimeoutError`, and leave runner cancellation to M4. It is not a new blocker.

## Commands actually run

From `/private/tmp/classifier-m1a-r2-grok`, interpreter `/Users/david/Projects/Bucheggang/.venv/bin/python`, `PYTHONPATH=src:scripts`.

- `git rev-parse HEAD`, `git status --porcelain=v1`, `shasum -a 256 -c docs/reviews/classifier/M1a/r2/MANIFEST.sha256`, before and after.
- `git diff 1f5a45d..e997412` for `assess.py`, `history.py`, `classifier_replay.py`, `feature-schema.md`, `m1-report.md`, `pyproject.toml`, and `split-manifest.json`.
- Real-pack initiator census through `HistoryIndex`.
- One temporary copy of the base pack, outside the repo, with one purchase initiator changed to `merchant`. The copy was removed.
- AU0035 digest mutation, schema mutation, and missing-limit probes.
- In-process replay of SCEN0000 through SCEN0004 against the five supplied drafts. No provider call, simulator call, test file, suite, or linter.

## Limits

`scripts/replay.py --all` was not rerun as a second process. The in-process classifier path matched the committed 45-row CSV, including the decisions and reason codes that the report says were compared with `replay.py`. No model was fitted. Jev and the simulator were not called. Unrelated files in the same head, including policy MCP, extract, and report-lane changes, were not graded as classifier behavior. The uncommitted shared-contract draft in the manager checkout was not read or graded.
