# Origin and customer-lock HTTP exercise

The frozen PR #76 candidate `7803bd0dd06b7e48d66a1ca489b8efc8313c870f` completed this exercise with exit 0. The client used a real Uvicorn subprocess and HTTP sockets on a fresh loopback port, with two disposable local accounts. The source checkout was not edited.

## Origin handling

| Request | Missing Origin | Foreign Origin | Exact configured Origin |
| --- | ---: | ---: | ---: |
| Register | 403 | 403 | 201 |
| Login | 403 | 403 | 200 |

The client saved the existing session file's bytes before the two refused login calls. The file was byte-identical afterward. This establishes that those rejected requests did not update that session record. The exercise did not count filesystem writes for successful requests.

## Customer guard with no mandates

Neither account had a confirmed mandate. Each began with global-policy version 0 and an empty rule list.

The client process acquired the actual `leash.runner.records.customer_lock` for account A. A separate HTTP client thread then sent account A's global-policy PUT to the API subprocess. While that guard was held:

- Account B's global-policy PUT completed with 200.
- Account A's request remained unfinished, including after B completed and a further 100 ms observation interval.

Releasing the customer guard let A's request complete with 200. No confirmation record or mandate ownership was invented to create a nonempty lock set. This observation covers the empty-owned-set path and separation between customer guards.

The client then sent two simultaneous HTTP PUTs for account A, both naming the same current version and hash. One returned 200 and the other 409. The requests kept the rules empty; this was a local persistence and versioning exercise, with no simulator permission mutation.

## Evidence and limits

[Recorded statuses](policy-locks-http-2026-09-25.json) name the exact candidate. The ignored local driver was run as:

```text
/private/tmp/policy-locks-7803bd0/.venv/bin/python \
  .cotal/policy_locks_http_exercise.py
```

The owned API process stopped and the disposable store was removed. The isolated source tree and its generated lockfile were retained. No pairing approval, policy confirmation, customer purchase answer, simulator request or provider request occurred. No test suite or linter was added or run.

The actual confirmation route, a nonempty owned mandate set and ordering against an accepted live purchase were not exercised. Those still require the genuine customer/store and the coordinated live run. This record is functional evidence for the named candidate, separate from its formal review and merge.
