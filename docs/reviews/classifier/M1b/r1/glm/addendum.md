# Addendum to M1b r1 GLM report — correction to line 16

Head re-verified unchanged: `e4ba7ba1f0707164ddfd6071779501a880598b44`. Original report preserved untouched (sha256 `78bc3fc8dac3f8ac74a76dd65d40000ec81cf5b77784fe2fd81c650da175a4c6`).

## Correction

The original report's second bullet under scope and isolation said: "An equal-timestamp earlier attempt is excluded, not leaked. Feature time equals the authorization timestamp; a same-moment history row can never be an input."

That statement is wrong. `history.py:170` bisects on the composite key `(timestamp, authorization_id)`, so the ordering is lexicographic over the pair:

- A history row with the same timestamp and a lower authorization_id than the current purchase IS included in the prior set.
- The current purchase's own key and every later key (later timestamp, or same timestamp with an equal or higher authorization_id) are excluded.

I re-ran this against the real index at head. On card `CA0018`, first history row `TR00001` at `2025-09-01T04:03:44Z`: a hypothetical purchase at the same timestamp with authorization id `ZZZZ9999` includes `TR00001` in its priors; with `AAAA0001` it does not; the exact same key `(ts, TR0001-style id)` is excluded. This matches the M1 report's own phrasing, "strictly before the purchase's `(timestamp, authorization_id)` order", which my sentence misread.

## Does the verdict change

No. APPROVE stands, for these reasons:

1. The mechanism remains a deterministic total order. The current purchase is always excluded (its own key is never in the prior set), and no later row in the order can enter. There is no path from the purchase's own outcome into its features.
2. The definition is exactly what the milestone's own documents state; the code implements the stated contract. My report misdescribed it; the code does not misbehave.
3. Nothing else in the report's verification rested on that sentence: the 45/45 replay parity, identity and isolation checks, digest tamper rejection, cross-authorization rejection and model-off decision neutrality were all observed live and are unaffected by the tie-break rule.

One nuance worth recording: a same-timestamp, lower-ID row is treated as an earlier event, so within a burst of purchases sharing a timestamp the composite key, not the wall clock alone, defines "pre-event". The replay script enforces strictly advancing keys across scenario attempts (`scripts/classifier_replay.py:79-82`), and the 45 replay attempts do not appear in the history packs, so no replay attempt can see itself.
