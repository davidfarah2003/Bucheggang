# Activity history verification

The initial hiking-boots history returned 19 rows for 13 authorization IDs. Six purchases appeared twice, first as `step_up` and then as `decline`. Opening one of those step-up rows showed the final decline from `/decisions/{id}`. This disagreed with the Activity list.

`records.mandate_history` now returns one latest accepted result per authorization. A saved `.resolve.json` takes precedence over its initial submission. Both records remain on disk for audit. Rows are ordered by the selected outcome's acceptance time and keep the existing `{decision, state_after}` shape.

For a newly confirmed mandate with no decision records or recorded state, the result is an empty list. Route ownership from PR #41 still runs first, so an unrelated customer cannot turn an unknown mandate into a successful history lookup. A non-directory history path, malformed record or nonempty saved state with no history raises. The read takes the same mandate lock as recording, preventing the new empty-history check from observing the state-write/file-write interval.

## Actual saved-run results

The checks loaded the original records from the completed live runs. No records were copied, fabricated, replaced or deleted. Every returned decision and state-after was compared with `records.decision_detail` for that authorization.

| Mandate | Stored submission/resolution records | Activity rows after repair | Compared with final detail |
| --- | ---: | ---: | --- |
| TM57238c60e1ddb511 | 23 | 13 | All equal |
| TMa575eab935b50a33 | 19 | 11 | All equal |
| TMd3ea0352275a0858 | 19 | 13 | All equal |
| TMe837ced5975dd259 | 23 | 12 | All equal |
| Total | 84 | 49 | No duplicate authorization IDs |

The household run still has one platform-only timeout with no local decision record. This change does not invent a fiftieth local row.

Calling the history reader for an unused ID with no decision or state file returned `[]`; no financial state file was created. This checks the new reader's empty-state behavior. A newly confirmed owner's HTTP response still needs the coordinated human Wallet run and retained confirmation metadata.

No simulator call, customer answer, linter or test suite was used. The complete initial HTTP/MCP/browser checks and ownership failure are recorded in [local-app-e2e-2026-09-25.md](local-app-e2e-2026-09-25.md).
