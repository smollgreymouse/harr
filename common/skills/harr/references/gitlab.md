# GitLab MCP in Harr

GitLab MCP provides live GitLab API data: merge requests, pipelines/jobs, issues, projects, users, variables and other GitLab entities.

## Normal route

The normal Harr route is:

```text
agent -> LeanCTX gateway -> GitLab MCP HTTP service -> GitLab API
```

The long-lived MCP service is managed by Harr at `http://127.0.0.1:3334/mcp`.

Use `ctx_tools` to discover/call `gitlab::*` tools when using this route.

## Direct route

Harr may also expose GitLab MCP directly to an agent host for diagnostics or hosts where direct access is useful. A direct registration is an alternate transport to the same service, not a second source of truth.

Do not query both direct and gateway routes for the same operation unless diagnosing the gateway.

## Scope

Use GitLab MCP for GitLab server state. Do not use it as a substitute for local Git repository operations such as status, branch checkout, local history or push/pull workflow when a direct Git MCP is available.

## Authentication and permissions

Harr stores the GitLab PAT privately and LeanCTX supplies it as `Private-Token` through secret-memento handling. Never print or inspect the PAT.

Harr configures the server with the full tool surface:

```text
GITLAB_PERMISSION_MODE=full
GITLAB_TOOLSETS=all
```

Effective permissions are still bounded by the PAT.
