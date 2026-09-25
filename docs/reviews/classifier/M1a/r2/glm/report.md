# Classifier M1a correction round r2 review — GLM

- Verdict: **APPROVE** for this exact M1a r2 correction cut, with the same scope binding as r1 (history features and model-off replay only) and two low findings below that do not block.
- Head: `e9974121fc47320dc7fabb9ddb280a517d1116cc`, verified as this grading tree's HEAD before and after review (`git rev-parse HEAD`), tree clean (`git status --porcelain` empty, 0 lines).
- Base: `498898155272e17b9907c364d723a503541ad6fc` (verified: valid commit object, ancestor of head). Preceding r1 target: `1f5a45da0d0b12d53ec4268de1f683052ce65fba`.
- Manifest: all 25 files in `docs/reviews/classifier/M1a/r2/MANIFEST.sha256` verified OK before and after review (0 non-OK lines).
- Model pin: `glm-5.3` (from `cotal_orientation`, recorded from COTAL_MODEL / the agent file). Requested effort: **max**; performed in full within the eight-minute window (full correction-diff read, five live verification probes on real AU0035 data, fresh 45-attempt classifier replay, independent base `--all` replay, independent 45-row feature recomputation, split-manifest regeneration, per-commit ownership check, before/after manifest verification). The accepted tier is not observable from inside the session, so I do not claim the provider actually served max reasoning.

## What the correction actually changed (classifier-owned, verified per commit)

Three classifier-owned commits on top of merge `dbc8f61`:

1. `2d10bf9`: `pyproject.toml` optional `classifier` group (numpy/scikit-learn/catboost), generated `uv.lock`, `m1-all-45.csv`, progress-log lines. No import of the group anywhere in `src/` (verified: no fitting code path exists yet), so no live effect.
2. `96cce47`: preservation only (r1 findings and the three r1 reports; my r1 report byte-identical to what I wrote, SHA-256 `857c71913d654595d7ea4da776effbc842123df49390068bbf2a55ade3bf43ed` re-verified).
3. `e997412` (head): the four r1 corrections. (a) `purchase_digest` now hashes the full `HistoryFeatures` map (`assess.py:11-27`), and `validate_bundle` recomputes over `bundle.features` (`assess.py:42`), so a mutated value, a dropped key or a changed amount all fail before evaluation. (b) Missing account limit raises `ValueError: <auth>: account limits unavailable for mandate card` (`history.py:268-270`) instead of a bare `KeyError`. (c) Purchase rows with an initiator outside `{agent, human}` raise at load (`history.py:140-142`), with the domain documented in `feature-schema.md:24`. (d) Replay checks strict `(timestamp, authorization_id)` progression (`scripts/classifier_replay.py:79-82`).

## Verification I performed (all one-off, read-only, private venv outside the tree)

- **Digest probes on real data (SCEN0004/AU0035 bundle built through `replay.build_event`)**: tampered feature value, dropped feature key, changed billing amount all raise `ValueError: AU0035: assessment purchase digest differs`; removing the card's account limit raises `ValueError: AU0035: account limits unavailable for mandate card`. Untampered bundle validates. This reproduces exactly the builder's four r2 claims, independently.
- **Initiator domain on real packs**: `(transaction_type, initiator_type)` cross-tab over both packs. Purchases: agent 453 + human 4112 (base), agent 19037 + human 121059 (additional). Merchant initiators occur only on refunds (53 / 1904). So the fail-loud purchase domain is reachable only by a future pack revision, exactly as documented; nothing silently encodes merchant as human.
- **Fresh 45-attempt classifier replay** with the five supplied drafts (`SCEN0000/0001/0003/0004` from `docs/eval/replay-policies/`, `SCEN0002` sample): 45 rows, 11 approve / 32 decline / 2 step_up. Every field of my fresh CSV equals the committed `m1-all-45.csv` row for row except `elapsed_ms` (0 mismatches over 45 rows x 10 stable columns). Committed CSV SHA-256 `fd9ea6a52795969c96a571eb13ac470907746d9fcd253fdaa97612925f7df3ee` matches the m1-report claim.
- **Independent base replay**: `scripts/replay.py --all` with the same drafts gives the same 45 authorization, decision and reason-code sequences. Three-way comparison (base replay vs fresh classifier replay vs committed CSV): 0 mismatches. The AU0040 one-reason-code difference against the older merged baseline CSV is real and correctly explained: the old baseline predates policy #39, which removed SCEN0004's `is_addon` rule; the current SCEN0004 draft verified to contain no add-on rule, and AU0040's reason codes change accordingly (`item_mismatch|injected_instructions` now vs `item_mismatch|unrequested_item|injected_instructions` before). The m1-report discloses this divergence rather than hiding it.
- **Temporal leakage, independent recomputation**: for all 45 attempts I recomputed `card/customer_merchant_approved_count` and `card/customer_approved_purchase_count` from the raw CSVs with the documented strict `(timestamp, authorization_id)` key, independent of `history.py`. 0 mismatches against the fresh replay output. Prior rows only; no scenario attempt leaks into a later attempt's features through this path.
- **Strict replay ordering**: all 45 attempt rows satisfy strict tuple progression per scenario; 0 same-timestamp adjacent pairs anywhere, so the tightened check cannot reject the current pack and does close the r1 G3 gap.
- **Split manifest**: `scripts/classifier_split.py` regeneration is byte-equal to the committed manifest (top-level diff set empty, 400 fitting / 100 reserved). The only manifest change in the diff is the `feature-schema.md` input hash (`3864e478…` to `91fab4bf…`), which matches the schema doc's new initiator-domain sentence; seed and membership unchanged, as the brief claimed.
- **Isolation**: `git diff 1f5a45d..e997412` touches no file under `src/leash/contracts/`, `docs/contracts.md`, `src/leash/engine/evaluate.py` (verified no classifier/assessment import in it), `src/leash/engine/state.py`, `jev.py`, `types.py` or `classifier_split.py`. `history_bundle`/`validate_bundle` are called only by `scripts/classifier_replay.py`. The engine-owned P1/P2 integration remains absent and unapproved by M1a, and the m1-report and progress ledger keep saying so. The uncommitted manager-checkout contract draft is not in this frozen tree (nothing to grade there).

## Findings under my lens

**R1 (low, documentation honesty, carried from r1 G1, still correctly bounded).** The approval covers the M1a history/model-off cut only. `evaluate()` still takes no assessment argument and no live path calls the classifier. The m1-report, progress ledger and findings.md all keep this limit explicit. Failure scenario if ignored: declaring full M1 complete on this APPROVE. The documents themselves prevent that claim; keep the milestone row partial until P1/P2 review.

**R2 (low, digest-design note, non-blocking).** `purchase_digest` is an integrity check over trusted backend state, not authentication; since `validate_bundle` recomputes the digest over `bundle.features`, an attacker or bug that mutates features and re-signs consistently would pass. The m1-report's new wording ("checks accidental mutation in trusted backend state; it does not authenticate an external caller") states exactly this, so the claim matches the mechanism. Failure scenario: treating the digest as a tamper-proof seal against a writer inside the trust boundary would overstate it; M2/M3 must not describe it as authentication.

**R3 (observation, positive).** The purchase-only initiator domain is adequate for M2 fitting on these packs: purchases are exclusively agent/human (140,641 additional-pack purchases verified), merchant-initiated rows are refunds only, refunds and withdrawals are excluded from familiarity and velocity by construction, and a future merchant-initiated purchase raises at load rather than mislabelling. Cold starts remain represented (`missing` reasons with support counts; 542 zero-prior-approved customer-scoped purchases recorded in the schema doc and manifest). Card vs customer vs mandate scope is enforced end to end: authorization/mandate identity equality, card-owns-customer join, per-card limits, cross-pack customer overlap rejection.

**R4 (observation, calibration/threshold honesty).** No model is fitted and no threshold exists yet (`BehaviorAssessment.escalation_fired` stays False until owner ruling O4), so calibration and threshold selection remain unclaimed and unexercised. Nothing in this target makes an evaluation claim beyond deterministic replay parity, which I reproduced.

## Commands actually run (in the grading tree, read-only)

1. `git rev-parse HEAD`; `git status --porcelain`; `shasum -a 256 -c docs/reviews/classifier/M1a/r2/MANIFEST.sha256` — before and after review (25/25 OK both times).
2. `git log --format='%H %s' 1f5a45d..e997412`; `git diff --stat/--name-status` over the range; `git show --stat` for each of `2d10bf9`, `96cce47`, `e997412`; empty-diff checks for contracts/evaluate/state/jev/types/split paths.
3. `git cat-file -t` and `git merge-base --is-ancestor` for the base SHA; `git worktree list` (read only).
4. Fresh private venv outside the tree (`python3 -m venv`, `pip install pydantic httpx fastapi`): all runs below with `PYTHONPATH=src`.
5. Real AU0035 bundle probes (validates; tampered value / dropped key / changed amount / removed limit): all four raise the expected `ValueError`.
6. `python scripts/classifier_replay.py` with all five supplied drafts to `/private/tmp/glm-r2-m1all-fresh.csv`: 45 rows, 11/32/2, exact match with the committed CSV except `elapsed_ms`.
7. `python scripts/replay.py --all` with the same drafts to `/private/tmp/glm-r2-base-all.csv`: three-way 0 mismatches.
8. Independent 45-row feature recomputation from raw CSVs (strict tuple key, both scopes): 0 mismatches.
9. Strict-ordering scan of all 45 attempt rows per scenario: 0 violations, 0 same-timestamp adjacent pairs.
10. `scripts/classifier_split.py` regeneration: byte-equal manifest; only the feature-schema input hash changed.
11. Pack cross-tabs (`transaction_type` x `initiator_type`, both packs) and SCEN0004 draft add-on-rule check; SHA-256 of the five drafts, `m1-all-45.csv`, `feature-schema.md`, `m1-scen0002.csv`, my preserved r1 report.

## Limitations

- No live simulator, provider, app/API or Jev call was made (forbidden and none is wired in this cut). M3 latency/deadline claims remain unmeasured here.
- The r1 error-handling verdict on `validate_bundle`'s recomputation design (R2) is unchanged; it was and remains adequate for an integrity check.
- My independent recomputation covered four sensitive features over all 45 attempts rather than all 50 features over the 140k historical corpus (that deeper check was r1's; the correction diff did not touch `_features` arithmetic beyond the initiator guard, verified by reading the diff hunk).
- The environment was a fresh private venv (pydantic 2.13.5, Python 3.13.9), not the builder's `.venv`; the grading tree has no `.venv`. Nothing version-sensitive was observed.
- The `uv.lock` file was inspected for the three declared classifier-group pins and nothing else; I did not run `uv sync` (no network spend approved for this round).

## Observed outcome

Target verified unchanged before and after review: HEAD `e9974121fc47320dc7fabb9ddb280a517d1116cc`, clean tree, 25/25 manifest entries OK. Every r1 blocker/finding I raised or endorsed is addressed in this cut (N1/N2/G2/G3 corrections verified by live probes; G1 scope hold preserved in every document; G8 remains runner-owned and disclosed). All reproduction checks passed with zero unexplained mismatches. APPROVE for the M1a r2 correction cut at head `e9974121fc47320dc7fabb9ddb280a517d1116cc`, base `498898155272e17b9907c364d723a503541ad6fc`. This does not approve engine-owned P1/P2 integration, M2 fitting, M3 composition or M4 release.
