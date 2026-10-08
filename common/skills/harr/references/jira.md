# Jira MCP in Harr

Jira is an optional **on-demand stdio** MCP behind LeanCTX:

```text
Codex/OpenCode -> LeanCTX -> harr-mcp-run jira -> uvx mcp-atlassian -> Jira REST API
```

No Atlassian-hosted MCP endpoint, Jira plugin, Docker daemon or MCP installation on the Jira server is required. This integration targets Jira Server/Data Center with Personal Access Token support; older versions and alternative enterprise authentication methods need separate compatibility testing.

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

Store the PAT only with `harr secret set jira`. Harr injects it as `JIRA_PERSONAL_TOKEN` when launching the local MCP, not into the gateway config, registry, or local env file. Use `harr secret unset jira` to remove the saved token. `uvx` must be installed and the MCP package cached during `harr install mcp`.

For Jira Cloud, use a separate `JIRA_USERNAME` + `JIRA_API_TOKEN` configuration (not provided by this Server/DC preset). If your Jira does not support PATs, do not try to use a Cloud API token as a substitute; select a compatible authentication provider after investigating the installed Jira version.

Look up tool names through LeanCTX `ctx_tools` discovery; prefer narrowly-scoped JQL and read-only operations before mutations.
