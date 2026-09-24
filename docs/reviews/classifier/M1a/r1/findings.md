# M1a r1 findings and correction scope

All three reviewers approved the same frozen history-only target `1f5a45da0d0b12d53ec4268de1f683052ce65fba`. Gemini report SHA-256 `68e01cbc704f1da33e8a2d4fe9852aae777c5f4f0738abfa37a6c65e2105ecc1`, Grok `875c7b9358e015b826b5193fd6e2838a3544feee65346d84a72113e309cd9e3e`, GLM `857c71913d654595d7ea4da776effbc842123df49390068bbf2a55ade3bf43ed`. This list was collected before any correction to the frozen M1a source. The panel approval is limited to the history and model-off replay cut. Full M1 still needs P1/P2 and the live runner path.

| Finding | Disposition |
| --- | --- |
| Grok N1: feature values, support, missing reasons and schema are not bound by `purchase_digest` | Bind the feature map into the digest used by `history_bundle` and `validate_bundle`. A changed feature value must fail before evaluation. The digest remains local and contains no credential. |
| Grok N2: missing account limit raises an unhelpful `KeyError` | Raise a descriptive `ValueError` naming the authorization and missing account limits. Valid empty history remains supported. |
| Grok N3: engine deterministic history indexes timestamps alone | The pack has no same-customer timestamp ties, so observed deterministic checks match. This is an engine-owned ordering issue to coordinate separately; classifier hist-1 keeps its strict tuple key. |
| GLM G1: M1a approval does not cover full M1 | Keep the milestone row partial until the engine-owned P1/P2 contract and live path are reviewed. Do not use this approval as a full M1 release claim. |
| GLM G2: purchase initiator domain excludes `merchant` | In the supplied packs, merchant-initiated rows are refunds, not purchases. Make the purchase-only human/agent domain explicit at load and in the schema. A future merchant-initiated purchase raises as an unsupported training target rather than being silently coded as human. The r2 panel decides whether this fail-loud domain is adequate before M2 fitting. |
| GLM G3: replay order only checks non-decreasing timestamps | Check strict `(timestamp, authorization_id)` progression across scenario replay rows, matching hist-1. |
| GLM G8: offline replay notices a deadline overrun only after synchronous work | Keep the actual `TimeoutError` and report the limit. The runner's absolute budget and cancellation discipline are owned by the runner lane and remain an M4 release gate. |
| Independent real-data run after the r1 freeze | Four additional supplied evaluation drafts landed on main. Classifier replay over all 45 public attempts produced 11 approve, 32 decline, 2 step_up. A fresh `scripts/replay.py --all` run with the same current drafts matched all 45 decisions and reason-code sequences. Add this evidence to the r2 report and preserve the CSV. |
| M3-facing credential boundary | `jev.py` currently reads the whole shared `.env` while looking for OPENROUTER_API. The challenge key must remain read only by runner.settings. Resolve this before M3 review without exposing either value. No model-enabled path uses this adapter yet. |

The optional `classifier` dependency group and generated lockfile were added after the r1 target; the correction review includes them as independent M2 preparation. No model has been fitted and no operational threshold has been chosen.
