# Classifier M0 r2 addendum, zero-history recount

Verdict change: none. APPROVE `6cd4340316c0ebc546a2c0f8ff6b147ef1688db8` stands.

This file is separate from `report.md`. That report was not edited. The grading tree was not edited. HEAD at this recount was still `6cd4340316c0ebc546a2c0f8ff6b147ef1688db8` and the working tree was clean. `report.md` SHA-256 remained `3f711502afc32332f05d9b26e5267837cd8b43be91836dd22a92e15f00de233e`.

The manager's count is right for one definition, and M0's sentence is wrong for that definition. It does not change the approval.

## What was counted

Read-only scan of `viseca-2026/data/authorization_history.csv` and `viseca-2026/additional-data-history/authorization_history.csv` on the frozen tree. For each purchase row, prior approved purchases are rows with `transaction_type=purchase` and `status=approved` whose `(timestamp, authorization_id)` is strictly earlier in the same scope.

| Scope | Pack | Purchase rows with zero prior approved purchases | Span | July 2026 rows in that set |
| --- | --- | --- | --- | --- |
| customer | additional | 542 | all in 2025-09 | 0 |
| customer | base | 23 | all in 2025-09 | 0 |
| card | additional | 902 | 2025-09 through 2026-07 | 5 |
| card | base | 46 | 2025-09 through 2025-11 | 0 |

Customer scope matches the reported 542 and 23. Every one of those rows is in September 2025, the start of both packs. July 2026 has 12,941 additional-pack purchases and 452 base-pack purchases. None of those July purchases has zero prior approved purchases on the same customer.

Card scope is larger because a later card can be new while the customer is not. Additional has 5 July purchase rows with no prior approved purchase on that card. Base July has none. M0 did not use this card definition in the disputed sentence.

## What M0 says

`docs/plans/02-classifier-m0.md:187` says: "The zero-history slice has no examples in either supplied pack, so its outcome metrics are unavailable."

That sentence is false for customer-scoped strict pre-event approved-purchase history. The additional pack has 542 such purchase rows and the base pack has 23. They are early-history rows, not a July slice.

The same paragraph also says July rows do not enter selection, fitting, calibration or threshold choice, and that reserved-customer July metrics lead generalization. Those July statements stay true. A July evaluation row, seen or reserved, is not a zero-history row under the customer definition above.

## Effect on the verdict

The false sentence is a reporting error in the G1 disposition. It does not open a model path, accept merchant text, weaken the pass-or-uncertain check, or move July into fitting. The early-September rows are inside the fitting population if M2 follows the written protocol, so a zero-history fit slice exists and M2 can report it. M0's claim that the slice is unavailable should be corrected before M2 writes the table. That correction is a plan wording fix, not a blocker on this frozen target.

N3 from the r1 findings (no zero-history customers in either pack) is the source of the bad sentence. This recount withdraws that part of N3. The rest of the r2 approval is unchanged.

## Command

One read-only Python pass over the two history CSVs, grouping by `customer_id` and by `card_id`, counting purchase rows with zero strictly earlier approved purchases. No provider call, no simulator call, no edit to the target or to `report.md`.
