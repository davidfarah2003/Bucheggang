# History feature schema hist-1

Implementation: `src/leash/engine/classifier/history.py`, `FEATURE_SCHEMA_VERSION = "hist-1"`. This is the feature definition for M1 and the later offline comparison. It is frozen before fitting. A source row is eligible only when its `(timestamp, authorization_id)` is strictly less than the assessed purchase's key. Both timestamps are authorization times, not receipt or deadline times.

`HistoryIndex` loads the base and additional organizer packs, validates each card-to-account-to-customer join and rejects duplicate authorization IDs. A live event takes identity from `event.mandate.customer_id` and `.card_id`. A different authorization card or mandate ID raises. Historical examples use the signed organizer CSV customer and card fields, which are validated against the pack's ownership tables. Customer scope includes all cards owned by that customer; card scope includes that card only. No other customer's rows enter either scope.

For each `scope` in `card` and `customer`, the following names are in `HistoryFeatures.values`. A count is encoded as a float to share one numeric feature schema. `support[name]` is the row count specified below. Only undefined values use `None` and an entry in `missing`.

| Name suffix after `scope_` | Value and unit | Support | Missing when |
| --- | --- | --- | --- |
| `approved_purchase_count` | Earlier approved purchase count | matching approved purchases | Never |
| `prior_attempt_count` | Earlier purchase attempts, approved or declined | earlier purchase attempts | Never |
| `{merchant,device,country,channel,category}_approved_count` | Approved purchases whose corresponding field equals the current purchase field | all earlier approved purchases in scope | `device`: `no_device` when the current purchase has no device; other counts are zero when unseen |
| `{merchant,device,country,channel,category}_last_approved_days` | Days since the most recent matching approved purchase | matching approved purchases | `empty_history` when no earlier approved purchase; `no_prior_in_<field>` when the field is unseen; `no_device` when the current device is absent |
| `category_amount_median_chf` | Median prior approved purchase amount in this merchant category, CHF | same-category approved purchases | `empty_history` or `no_prior_in_category` |
| `category_amount_percentile` | Fraction of same-category prior approved amounts strictly below the current amount, in [0,1] | same-category approved purchases | `empty_history` or `no_prior_in_category` |
| `attempt_count_{10m,1h,24h}` | Prior purchase attempts in the inclusive trailing time window | all earlier purchase attempts in scope | Never |
| `declined_attempt_count_{10m,1h,24h}` | Declined prior purchase attempts in the same window | all earlier purchase attempts in scope | Never |
| `last_approved_purchase_days` | Days since the most recent earlier approved purchase | earlier approved purchases in scope | `empty_history` |
| `agent_attempt_count` | Earlier agent-initiated purchase attempts, including declines | all earlier purchase attempts in scope | Never |
| `agent_approved_count` | Earlier approved agent-initiated purchases | all earlier approved purchases in scope | Never |

Four purchase-level values complete the 50-feature schema: `amount_to_per_transaction_limit` and `amount_to_monthly_limit` are current billing amount in CHF divided by the limit in CHF, with support 1; `initiator_is_agent` and `card_active_at_attempt` are 0 or 1, with support 1. The additional-pack historical rows carry their own pre-event limits and `card_status`. Live requests use the mandate card's account limits from the base pack and `authorization.card_status_at_attempt`. An unknown card, missing limit, nonpositive limit, unsupported status, non-finite amount or failed CSV read raises. No score is substituted.

Approved purchases alone establish merchant, device, country, channel and category familiarity. Refunds and cash withdrawals never create familiarity or purchase-attempt velocity. A purchase declined before this event can count toward velocity and agent-attempt activity. The pack's supplied approved-count and lifetime-spend columns are unused. The live run-level `recent_attempt_count_10m` remains in `Event`; it is not an alias for historical velocity and is absent from model predictors.

Identifiers are lookup and grouping keys in `HistoryFeatures`, not entries in `values`. Merchant names, descriptions, item details, customer persona fields, source authorization IDs, scenario IDs and replay order are never predictors. The model-fitting script must select only the numeric keys declared here. Base-pack customers are excluded from parameter fitting, calibration and threshold selection.

The full additional pack has 542 purchases with no earlier approved purchase for their customer, all in September 2025. July has zero such customer-scoped rows; a zero-history July evaluation slice is unavailable. A new card held by an established customer can have zero card-scoped approvals while customer scope remains populated. The M2 report treats these as separate slices.
