# Jira MCP in Harr

Jira is an optional **on-demand stdio** MCP behind LeanCTX:

```text
Codex/OpenCode -> LeanCTX -> harr-mcp-run jira -> uvx mcp-atlassian -> Jira REST API
```

No Atlassian-hosted MCP endpoint, Jira plugin, Docker daemon or MCP installation on the Jira server is required. This integration targets Jira Server/Data Center with PAT and Basic authentication; enterprise gateways still need compatibility testing.

Enable it through the shared Harr component selector (preserve other optional choices):

```sh
harr mcp configure
harr install mcp
harr secret set jira
harr secret status
```

Edit the non-secret `mcp/jira.env` under the Harr config root:

```dotenv
JIRA_URL=https://jira.company.example
```

Store the PAT only with `harr secret set jira-pat`. Harr injects it as `JIRA_PERSONAL_TOKEN` when launching the local MCP, not into the gateway config, registry, or local env file. Use `harr secret unset jira-pat` to remove the saved token. `uvx` must be installed and the MCP package cached during `harr install mcp`.

For Jira Cloud, use a separate `JIRA_USERNAME` + `JIRA_API_TOKEN` configuration (not provided by this Server/DC preset). If your Jira does not support PATs, do not try to use a Cloud API token as a substitute; select a compatible authentication provider after investigating the installed Jira version.

Look up tool names through LeanCTX `ctx_tools` discovery; prefer narrowly-scoped JQL and read-only operations before mutations.

## TLS trust

On Linux, Harr builds an on-demand CA bundle from the OS OpenSSL CA bundle and TLS-trusted certificates in the user's NSS database (~/.pki/nssdb). It supplies this bundle through SSL_CERT_FILE and REQUESTS_CA_BUNDLE to the Jira MCP runtime, without disabling certificate validation. The bundle is regenerated when the MCP starts, so changed OS/NSS trust takes effect on restart. Non-Linux installations retain their normal runtime trust behavior.

## Authentication modes and preflight

Choose `JIRA_AUTH_MODE=pat` (default) or `JIRA_AUTH_MODE=basic` in `mcp/jira.env`. For Basic, supply the non-secret `JIRA_USER_NAME` and store the password via `harr secret set jira`; Harr translates these into upstream `JIRA_USERNAME` and `JIRA_API_TOKEN` in process memory. For PAT use `harr secret set jira-pat`. Harr checks `/rest/api/2/myself` with verified TLS before launching Jira MCP and fails closed on a non-200 response.

`JIRA_HOST` is accepted only if it equals the URL hostname. Upstream `mcp-atlassian` does not support a separate Host header; other values fail closed rather than silently ignoring an authentication-critical proxy setting. A dedicated transport adapter would be required for a distinct HTTP Host.

## Client certificate (mTLS)

Basic/PAT authentication can be combined with a TLS client identity. On Linux, set the non-secret local option `JIRA_CLIENT_CERT_NSS=<nickname>` to select a certificate from the user's NSS database (default `~/.pki/nssdb`). Harr exports that identity only into a private runtime directory, passes temporary PEM paths to `mcp-atlassian` as `JIRA_CLIENT_CERT` and `JIRA_CLIENT_KEY`, and removes the runtime files when the MCP exits. The private key is never stored in the repository or persistent Harr configuration.

Direct PEM paths supported by upstream `mcp-atlassian` may also be supplied locally with `JIRA_CLIENT_CERT` and `JIRA_CLIENT_KEY`; do not commit those paths or key material.
