# Pairing origin over real MCP transports

These checks exercised frozen source `fabd0a47a44145a53452009bae8f05d9b9ee2939` from PR #103. Python subprocesses ran the real MCP server. MCP 2.2 clients used stdio and loopback streamable HTTP. Each positive transport check had its own disposable policy/identity store.

The observed results are in [pairing-origin-2026-09-25.json](pairing-origin-2026-09-25.json). They contain no pairing code, verifier or credential.

## Startup refusal

Fourteen actual processes ran `python -m leash.policy.mcp_server --transport <transport>` with missing or malformed `LEASH_APP_ORIGIN`. The HTTP variant also supplied a port. Each process exited 1 with the named origin validation error before serving.

| Origin input | Stdio exit | HTTP exit |
| --- | ---: | ---: |
| Unset | 1 | 1 |
| Relative path | 1 | 1 |
| Origin with a path | 1 | 1 |
| Origin with a query | 1 | 1 |
| Origin with a fragment | 1 | 1 |
| Origin with userinfo | 1 | 1 |
| Leading whitespace | 1 | 1 |

These inputs cover the listed rejection cases. They do not establish validation of every malformed hostname or port.

## Stdio

With `LEASH_APP_ORIGIN=http://127.0.0.1:8000`, a real client initialized and called `begin_pairing`. The returned URL used that exact origin, path `/app/`, and only the `pair` query parameter containing the returned code. The verifier stayed in its separate tool-result field and was absent from the URL.

`complete_pairing` before customer approval returned `PairingPending`. `get_policy_authoring_instructions` remained unauthorized. The stored identity JSON contained neither the clear code nor the verifier. The client context closed the owned subprocess and the temporary store was removed.

## Streamable HTTP

A second real server listened on an OS-selected loopback port. Its configured Wallet origin remained `http://127.0.0.1:8000`, a different port from the MCP request origin. An actual HTTP MCP client initialized and called the same tools.

The returned Wallet link used the configured origin and contained only the pairing code. It did not derive its origin from the MCP request. The verifier was absent from the URL. Unapproved completion again returned `PairingPending`; unpaired authoring remained refused. Neither clear pairing value appeared in the persisted JSON.

The owned server was terminated with SIGTERM and `wait()` observed exit code -15. The temporary store was removed. No unrelated service was stopped.

## Limits

No Wallet was opened at port 8000. There was no pairing approval, issued agent token, policy proposal, mandate confirmation or customer purchase answer. The checks used the MCP SDK clients; they do not establish setup in Claude Code, Codex, ChatGPT or another shopping-agent host. No simulator or model-provider request was made. No source changes, test suite or linter were part of this exercise.
