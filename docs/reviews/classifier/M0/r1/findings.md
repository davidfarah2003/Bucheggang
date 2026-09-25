# Classifier M0 r1 findings

Frozen target `d651ef85920925d36ece77fc5eaa4d13fff0bd8f`, base `ed2bc3cf0115419f46412536ba2d4e9524bbf7aa`. The three reports were collected before M0 corrections. Gemini approved. GLM blocked on G1. Grok approved. Their source reports are in the adjacent reviewer directories.

| Finding | Disposition for r2 |
| --- | --- |
| GLM G1, May candidate selection followed by refitting through May | Keep the predeclared protocol. July and the reserved 100 customers remain untouched by selection, fitting, calibration and threshold choice. Label seen-customer July estimates as selection-informed, use reserved-customer July metrics as the primary generalization estimate, and report the two populations separately. Record this choice in M0 and the later split manifest. This is GLM's third accepted correction. |
| GLM N1, deterministic checks explain a large share of declines | M2 report leads with purchases passing deterministic checks and also gives all-purchase results. |
| GLM N2, agent and human base rates differ | M2 reports July calibration and escalation rates by initiator. |
| GLM N3, no zero-history customers in either pack | M2 marks the zero-history outcome slice unavailable. Low-support and new-card slices are reported separately and not labeled cold starts. |
| GLM N4, live and historical features differ | M1 and M2 retain separate historical and live derivations; deployed predictors require the same semantics at inference. |
| GLM N5, progress ledger claimed a manifest at the 21:28 freeze | The manifest was added in `acb5763`, after the target commit. Correct the 21:28 Log wording and retain the existing manifest link with its actual provenance. |
| Grok N1, the Jev evidence probe omitted the provider restriction | Add `provider.only=["typesafe"]` and `allow_fallbacks=false` to the probe, run one paid call, and record the fresh result. M3 must send the same restriction and verify the served model. No credential value enters the report. |
| Grok N2 and N3, step-up budget recheck and mandate lock race | Existing M0 P3/P4 already assign these to runner and app owners. They remain open cross-lane release blockers for M4. |
| Manager's P2 wording at M0 line 88 | The frozen target said "agreed with engine_builder" before an agreement existed. The engine owner has since reported the exact ownership and conditional interface on contracts. Correct the timing and ownership, with the model check restricted to pass or uncertain. |

Grok's initial launches produced no report. The final r1 report came from a fresh principal using the same `classifier_review_grok` persona, model grok-4.7 and requested high effort. Its clean detached grading tree was at the frozen target. The original principal's event WAL lock was preserved. The report's requested effort was accepted by the harness without an observable provider-effort proof.
