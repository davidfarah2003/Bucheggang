# M2 r1 grok review

Verdict: APPROVE
Head: f5d27c80ed3862473852ae2ed3a802190ca13fc5
Base: 0b7c2c1d1b4021a835a237e92f8491e33c6d5e25
Cleared M1a history cut named by the brief: e9974121fc47320dc7fabb9ddb280a517d1116cc (not re-reviewed here)
Grading tree: /private/tmp/classifier-m2-r1-grok
Manifest: docs/reviews/classifier/M2/r1/MANIFEST.sha256, 19/19 OK before and after
Model pin: grok-4.7, from cotal_orientation (COTAL_MODEL / agent file). Persona .cotal/agents/classifier_review_grok.md requests model grok-4.7 and variant high. Requested effort: high. Accepted effort: high. The pin was not omitted.

Scope graded: offline comparison only. No P1/P2 engine integration and no live runner claim is part of M2. No peer report was read.

## Findings

No blocker.

The evaluation-only artifact cannot fire escalation. BehaviorModel.score always returns escalation_fired=False (src/leash/engine/classifier/behaviour.py:99). The artifact dict has no threshold key. Loader __init__ rejects any artifact_release_status other than evaluation_only_no_operational_threshold (behaviour.py:36-37) and any threshold_status other than proposals_only_owner_O4_pending (behaviour.py:38-39). A copied manifest with status operational, a copied manifest with threshold_status owner_O4_approved, and artifact_path ../outside.joblib all raised ValueError. history_bundle sets behaviour=None (src/leash/engine/classifier/assess.py:34). BehaviorModel is not called from any other module under src/.

Authorization and user isolation. HistoryIndex rejects a card that appears in both packs (history.py:110-111), a customer that appears in both packs (history.py:114-116), and a purchase whose card, account and customer disagree (history.py:136-139). for_event takes identity from the mandate and raises when the authorization card or mandate id differs (history.py:264-265) or the mandate card is not owned by that customer (history.py:266-267). Feature construction uses only that card's rows or that customer's rows (history.py:165-172). Base pack: 20 customers. Additional pack: 500. Overlap empty. Fitting 400 and reserved 100 are disjoint, both subsets of the additional pack, and neither contains a base customer. All 140,096 additional purchases fall in the frozen split. Recount of purchase_counts matched every window.

Prompt injection. Predictors are the 50 numeric hist-1 keys. No identifier, persona, merchant text, scenario id or replay order is in model-manifest.json feature_names. An extra injected_id feature and schema hist-0 were rejected by score(). Merchant text is not an input to this model. joblib.load (behaviour.py:58) will unpickle a repository artifact whose SHA-256 matches the manifest. That is an operator-trusted file, not a request input. A path that leaves the repository is rejected (behaviour.py:45-49).

Evidence provenance and pre-event cutoff. historical_purchases and _prior keep rows whose (timestamp, authorization_id) is strictly less than the assessed key (history.py:165-172, 283-303). The first additional purchase TR100001 has customer_prior_attempt_count 0. The next seven purchases of CU1443 increase that count by 1 each time, so the current row is not in its own profile. Imputer medians stored in the artifact match nanmedian on the 91,251 seen-customer rows through May (fit 80,771 + select 10,480), max abs delta 0.0. Reserved rows did not move the fitted imputation statistics. Missingness is an explicit indicator: 18 features, not a substituted score. SimpleImputer(strategy="median", add_indicator=True) is declared preprocessing (scripts/classifier_fit.py:145).

Policy and state. The issuer-rule-pass proxy uses card status, online and international switches, per-transaction limit, and account calendar-month approved spend accumulated only after an approved row (classifier_fit.py:74-92, 126-129). It does not include the current purchase in spend_before. The report states it is not a complete mandate-rule evaluation. June cuts are proposals. July rates are reported at those unchanged cuts (model-manifest.json july_rates_at_june_proposals). No code path writes an operational threshold.

Failure handling. Non-finite features, scores outside [0, 1], a bad schema, a hash mismatch, a library version mismatch, and a changed split manifest raise. There is no score default and no second model. numpy, scikit-learn and catboost are in the optional classifier dependency group (pyproject.toml:17-22), not in the runtime dependencies. Runtime import of the engine without that group was not re-run here. The progress log claims it. The loader imports those libraries at module import, so a model-enabled process without them fails at import rather than substituting a score.

Reproduced report figures, not taken from the report as proof:

- Artifact SHA-256 e4815c5677073c4e985c56f09f045be3d72c4e3ae624b75f9d06870630c828cf matches the manifest field and the file.
- Manifest SHA-256 3e9022aa98223d962e8beee29c0a5cbb0a10b093ff1a7fee916c6703b750ec0e.
- AU0035 (base card CA0039, customer CU0019, event built with docs/eval/replay-policies/SCEN0004.json) scored 0.097382, escalation_fired False.
- Additional purchase TR100011 with empty customer_device_id scored 0.027787, missing reason no_device, escalation_fired False.
- All 45 public attempts scored with escalation_fired False: min 0.0300, median 0.0499, max 0.2364. The same SCEN0004 policy object was used only to construct events. Feature construction does not read policy rules. This is not a claim that each attempt's own mandate policy was loaded.
- CatBoost tree_count_ 300, random_seed 20260924. Calibrator coefficient 1.1879169515746115, intercept 0.1668710509625922.
- June proposal cuts in the manifest round to the report table: 0.8950, 0.4980, 0.0961, 0.0523.

Non-blocking provenance note. scripts/classifier_fit.py writes the metric tables and stops at the artifact section (classifier_fit.py:380-406). The committed m2-report.md adds, after that template, the reserved calibration band table, the public-attempt versus July agent distribution comparison, the BehaviorModel smoke numbers, the initial-artifact byte drift, and the uv sync note. Those sentences are not generated by the script. The calibration bands match model-manifest.json. The smoke numbers above were reproduced. The initial artifact at /private/tmp/classifier-m2-initial-20260925/model-evaluation-only.joblib has SHA-256 d8c10b2b95586d22cb8e106d7f8a837dadce79232d9ed9122b9f84927ebf2c3d, different from the frozen file, with the same feature names, tree count 300, selected candidate catboost, and identical calibrator coefficients. The cause of the byte difference was not established, which the report already says. This does not change the frozen artifact's hash or enable escalation.

Reserved July issuer-rule-pass PR-AUC 0.0672, ROC-AUC 0.6593, Brier 0.0347 versus constant Brier 0.0350, and the May PR-AUC pair 0.4722 / 0.5042, were not recomputed by a full refit. They are present in the committed report and are consistent with the split counts and the loaded artifact. A full refit was not required.

## Commands actually run

From /private/tmp/classifier-m2-r1-grok, using /Users/david/Projects/Bucheggang/.worktrees/classifier/.venv/bin/python and PYTHONPATH=src. Generated files stayed outside the tree.

- git rev-parse HEAD; git status --porcelain; shasum -a 256 -c docs/reviews/classifier/M2/r1/MANIFEST.sha256 before and after. Both times HEAD f5d27c80ed3862473852ae2ed3a802190ca13fc5, status clean, 19 OK.
- joblib load of the frozen artifact: keys, CatBoost pipeline, calibrator, no threshold.
- BehaviorModel().score on AU0035 features from HistoryIndex.for_event, on TR100011, and on hist-0, NaN, and extra-name inputs.
- BehaviorModel on three tampered manifests under /private/tmp/classifier-review-reports/M2/r1/grok/bad-manifest.json.
- Split recount from authorization_history.csv against split-manifest.json purchase_counts.
- nanmedian of seen-through-May features versus imputer.statistics_.
- Score of all 45 public attempts.
- joblib load of the preserved initial artifact for calibrator comparison only.

## Limitations

- No full refit, so May selection and July PR-AUC were not regenerated.
- The 45-attempt score used the SCEN0004 policy object for every event. Identity comes from the attempt and authority rows.
- uv sync without the classifier group was not repeated.
- joblib unpickle of a hash-matched in-repo artifact is trusted. That is acceptable for this evaluation-only file and is not a request-time parser.
- No live simulator, provider, or customer answer was called.

## Observed outcome

APPROVE M2 at f5d27c80ed3862473852ae2ed3a802190ca13fc5. After the checks, HEAD was still that commit, the worktree was clean, and the 19 manifest paths still matched. A later change of that commit voids this verdict.
