# Classifier M0 r1, grok security review

Verdict: APPROVE

Target head: `d651ef85920925d36ece77fc5eaa4d13fff0bd8f`
Target base: `ed2bc3cf0115419f46412536ba2d4e9524bbf7aa` (ancestor of HEAD; parent of HEAD is `635398266160cbf690ae6dcc2c05db1f96698634`)
Primary document: `docs/plans/02-classifier-m0.md` SHA-256 `acbad9174f6532d5a1e9283261c2ea7087c99dd8cd582d18ddfbd6dc8359e323`
Approved design: `docs/plans/02-classifier-design.md` SHA-256 `4d8ea6601aa2a23927a895b03ccd8e90ec8ae275da818dbc377d01e258409eb9` (unchanged)
Manifest: `/private/tmp/classifier-review-reports/M0/r1/MANIFEST.sha256`, all 10 files OK before and after review.
Working tree at both checks: clean, detached HEAD. No source edit, stage, commit, checkout, reset, clean, stash, or worktree removal.

Model pin observed in this seat: `grok-4.7` (`cotal_orientation`: "Model pin: grok-4.7 (from COTAL_MODEL / the agent file)").
Requested effort: `high` (persona `variant: high`, kickoff and `brief-fresh.txt`).
Accepted effort: not observable from inside the seat. No session control reports the applied reasoning tier. This review does not treat the request as proof that the provider ran at high. The tier was not omitted from the brief or the persona.

Lens: authorization, prompt injection, evidence provenance, user isolation, policy/state races, fail-closed handling. Sections checked in full: M0 1, 3, 4, 6, 7, 8, 11, 12, plus the citations those sections depend on.

## Findings

No blocking finding.

### N1, non-blocking: Jev probe does not send the provider pin it is cited for

`scripts/classifier_m0_jev_probe.py:67` posts `BODY | {"model": model}` and an Authorization header. It does not send `provider: {"only": ["typesafe"], "allow_fallbacks": false}`.

M0 section 9 (`docs/plans/02-classifier-m0.md:175`) states that pin as what was checked live with this script. The committed script cannot have enforced it. A response can still name `typesafe/jev-1.13-20260917` while OpenRouter was free to fall back.

Failure scenario: an implementer copies the probe as the M3 adapter. A provider outage or alias then serves a different backend, and the adapter accepts it because the request never forbade fallback. M0's own adapter rule (raise if the response names a different model) is the right contract, but this script is not evidence that the pin was exercised.

Not a blocker because M3 is not implemented here, the probe was not re-run (paid call), and section 8 still fails closed on a malformed or disagreeing response. The pin text in section 9 must be implemented as a request constraint, not inferred from this script.

### N2, non-blocking: customer step-up approve still skips the budget recheck

`src/leash/runner/stepups.py:162-181` `answer()` holds `records.mandate_lock`, checks `expires_at`, and sends the customer's approve or decline to `/resolve` with the original evidence. It does not re-run budget or state checks. A second purchase can consume the period cap while this step-up is open, and the late approve still submits.

M0 section 7 (`docs/plans/02-classifier-m0.md:144` and P4 at 150) states this and assigns the recheck to `runner_builder`. The race is real. It is not an M0 code change, and the proposal does not claim it is fixed.

### N3, non-blocking: two mandate locks leave a post-evaluate window

`src/leash/runner/loop.py:215-216` holds `records.mandate_lock` only around `state.load`. Extract and `evaluate` run unlocked (`loop.py:227-239`). `submit()` happens with no lock. The lock is taken again only at `loop.py:241-245` to record.

`src/leash/api/mandates.py:87-94` and `:180` / `:206` use a different flock, `mandate_edits/<mandate_id>.lock`. `rg` over `src/leash/runner` finds no read of `mandate_edits`. The runner's policy is the `--draft` it was started with (`loop.py:199`, `213-214`).

Failure scenario: `handle()` evaluates an approve under the old cap. Concurrent `tighten_mandate` PATCHes a lower cap and writes the overlay. `submit()` then posts the approve. `technical_details.md:380` says an existing run keeps the simulator snapshot, so the platform will not apply that PATCH to this run. The local overlay is also invisible to this submit.

M0 section 6 states the same window and leaves the "already started run" question as owner ruling O3. P3 names one lock, an intent file, and a recheck. That is the right fail-closed shape. Approving M0 does not approve an implementation of P3.

## Citations checked

| M0 claim | Observed |
| --- | --- |
| `facts.py:40-47` normalizes names; `:125` exact-compares; `:130` copies only `product_type` into `matches_request`; size also changes the match at `:126-128` | Matches current `src/leash/extract/facts.py`. |
| `evaluate.py:28-33` nulls facts on `contains_instructions`; `rules.py:260` maps `facts.product_type` to `item_mismatch` for fail and uncertain | Matches. `reason_code` (`rules.py:273-284`) does not special-case uncertain product rules. |
| `decision.py:31` FactSource; `:55` Check.source has no `model`; `:34` PurchaseFacts has no `line_no` | FactSource is line 31. Check.source is line 55 and has no `model`. PurchaseFacts starts at line 34 and keys `item_id` only. `rules.py:140` collapses facts with `{item_id: fact}`. Public attempts have 56 lines, 45 auths, 0 duplicate `item_id`s, so the collision is latent. |
| `evaluate` is pure at `evaluate.py:42` and has no assessment argument | Signature is lines 42-43: `(event, policy, state, facts)`. No network and no model call in that function. |
| History checks use `auth.card_id` (`checks.py:100, 113, 138, 200`; `rules.py:158, 165`) | Those calls use `event.authorization.card_id`, not `event.mandate.card_id` or `customer_id`. `data.py:32-57` indexes `authorization_history.csv` per card and keeps approved purchases only (`data.py:42`). `HISTORY` is built from the base pack at `data.py:78`. |
| Runner lock `records.py:51-59`; extract cap 1.5s and reserve 2.0s at `loop.py:43-44`; substitute `engine_timeout` decisions at `loop.py:104` and `:120`, used at `:170-175` and `:232-234` | Matches. Both substitutes are fabricated business decisions after a timeout. `future.result` does not cancel the worker. |
| `docs/contracts.md:177` still defines `facts=None` as an extract timeout | The sentence is there. |
| `api.py` one 30s timeout | `api.py:33` uses `s.timeout_s`. `settings.py:38` requires `VISECA_TIMEOUT_S` and has no code default. The "30 s" figure is not in this source. P4 does not depend on it. |
| Step-up `expires_at` is accepted time plus window minus 5s (`stepups.py:40, 59-60`), window from bootstrap (`:51`), and `answer()` checks `expires_at` (`:172`) | Matches. An automated `deadline_at` does not reject the human answer. |
| Idea ruling `docs/idea/viseca-agent-control-layer.md:155` and `:170`; step 8 at `:151`; `docs/models.md:30` | All four lines match, including "never reads merchant text" and "a model that fails or times out raises". |
| Section 5 pack table | Recounted from the CSVs. Base 4701 / 20 / 41 / 2025-09-01..2026-07-31 / purchases 4565 (4112 human, 453 agent) / 258 declined. Additional 144674 / 500 / 832 / same span / 140096 (121059 human, 19037 agent) / 8154 declined. Attempts 45 from 2026-08-09 to 2026-08-22. Customer and authorization ID overlap between packs is 0. |
| Scenario cards | AUTH0001 and AUTH0002 are CU0001 on CA0001, which also holds CA0002. AUTH0003 CU0006 CA0011 (also CA0012). AUTH0004 CU0012 CA0023 (also CA0024). AUTH0005 CU0019 CA0039 (also CA0038). |
| Catalogue `item_name` and `item_category` equal the event on all 56 public lines | 0 mismatches. |
| Design hash | Recomputed equal to the approved hash. M0 does not edit that file. |

P1 (`"model"` on `Check.source`, evidence carries model id and artifact version) is required before a classifier check can be told from event or merchant text. P2's `assessments is None` means the feature is off, not that a call failed. A failed load or call raises before `evaluate`. That is the fail-closed rule this lens requires. It also overrides design section 3's "decides without it" (`02-classifier-design.md:32`). M0 says so in section 4.

Section 1 keeps Jev off `item_details`, `purchase_description`, and other merchant-authored text, and forbids a model result from satisfying a required fact or flipping a deterministic decline. O1 leaves catalogue `item_name` / `item_category` unresolved and tells M3 to use history only until then. That is the correct closed default.

Section 8: incomplete coverage, bad keys, duplicates, non-finite probabilities, or a sum outside 1e-6 of 1 raise `JevResponseError` with no renormalization. Provider `choice` must equal the local argmax or the response is an error, so it cannot reach `uncertainty_policy=approve`. An exact top tie stays uncertain. This matches review record R3.

Section 4 says live identity comes from `event.mandate.customer_id` and `event.mandate.card_id`, not an agent field. The event schema still carries a separate `authorization.card_id` (`event.py:46` and `:86`). Existing checks use the authorization card. The new `history.py` must not follow that pattern, or a substituted card id reads another card's history. P2 says card and customer scopes are built separately. That constraint is what makes the isolation claim true.

`rules.py:157-162` also treats `event.context.recent_authorizations` as extra approvals for `history.merchant_seen_on_card`. That list is event-supplied. M0 does not propose to copy it into the classifier. Pre-event rows only, in `history.py`, is the isolation boundary.

Injection: `_quarantine` drops extracted facts, including `matches_request`, when `contains_instructions` is set. `injected` still sees the raw line (`evaluate.py:72`). Quarantine cannot create an approval. The AU0040 label point in M0 is an engine observation, not a classifier change.

## Commands actually run

```
git rev-parse HEAD
git rev-parse ed2bc3cf0115419f46412536ba2d4e9524bbf7aa
git merge-base --is-ancestor ed2bc3cf0115419f46412536ba2d4e9524bbf7aa HEAD
git status --porcelain=v1
shasum -a 256 -c /private/tmp/classifier-review-reports/M0/r1/MANIFEST.sha256
```

Both hash checks were run before the script rerun and again after it. HEAD stayed `d651ef85920925d36ece77fc5eaa4d13fff0bd8f`. Manifest stayed OK. Tree stayed clean.

```
PYTHONPATH=src /Users/david/Projects/Bucheggang/.worktrees/classifier/.venv/bin/python scripts/classifier_m0_exact_name.py "27-inch monitor"
PYTHONPATH=src /Users/david/Projects/Bucheggang/.worktrees/classifier/.venv/bin/python scripts/classifier_m0_exact_name.py "27-inch computer monitor"
```

First invocation of the monitor command in this seat failed with `ModuleNotFoundError: No module named pydantic` because that process did not see the classifier venv site-packages. The same binary, with `PYTHONPATH=src` only, then imported pydantic 2.13.5 and both commands exited 0.

Observed monitor run: AU0035, AU0036, AU0038, AU0042, AU0045 decline `item_mismatch` with `matches_request` false. AU0039 decline `item_mismatch,unfamiliar_merchant,lookalike_merchant`. AU0044 decline `item_mismatch,unfamiliar_merchant`. AU0037 decline `amount_over_limit`. AU0040 step_up `item_mismatch,injected_instructions` with `matches_request` false. AU0041 decline `amount_over_limit,item_mismatch,unrequested_item,subscription,protection_plan`. AU0043 decline `item_mismatch,gift_card`.

Observed catalogue-name run: AU0035, AU0036, AU0038, AU0042, AU0045 approve `within_policy`. AU0039 and AU0044 decline on merchant checks only. AU0037 decline `amount_over_limit`. AU0040 step_up `item_mismatch,injected_instructions` with `matches_request` true. AU0041 and AU0043 unchanged. This matches M0 section 2, including the lines M0 abbreviated.

Read-only CSV counts for section 5, the authority/card join, and the 56-line catalogue compare. No `uv sync`, no test suite, no linter, no simulator call, no `classifier_m0_jev_probe.py`.

## Limitations

The Jev HTTP table in M0 section 9 was not reproduced. The probe is a paid provider call and was out of scope. N1 follows from reading the script, not from a new response.

`VISECA_TIMEOUT_S` was not read from `.env`. The key file was not opened.

Design section 5's May selection followed by a through-May refit is a measurement question on the frozen design. It is outside this lens and was not graded.

Effort acceptance is not visible in-seat. Orientation shows `grok-4.7` only.

## Outcome

APPROVE `d651ef85920925d36ece77fc5eaa4d13fff0bd8f`. The proposal keeps merchant text away from Jev, refuses model output as evidence of a required fact, separates card and customer history, and treats model failure as an error rather than a decision. The open races and the provenance bug are named, assigned, and not claimed fixed. N1 is the one evidence gap in the security-relevant pin.
