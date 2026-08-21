# GitLab MCP in Harr

GitLab MCP provides live GitLab API operations for merge requests, pipelines/jobs, issues, projects, users, variables and other GitLab entities.

## Normal route

The normal Harr route is:

```text
agent -> LeanCTX gateway -> GitLab MCP HTTP service -> GitLab API
```

The long-lived MCP service is managed by Harr at `http://127.0.0.1:3334/mcp`.

Use `ctx_tools` to discover/call `gitlab::*` tools when using this route. LeanCTX gateway discovery is ranked and returns only a short top-N list, not the full GitLab catalog. Never conclude that a GitLab capability is unavailable merely because it was absent from a previous broad `find` result.

For an operation whose verb is known, use a targeted discovery query. Examples:

```text
create GitLab merge request -> gitlab::create_merge_request
update GitLab merge request -> gitlab::update_merge_request
merge GitLab merge request  -> gitlab::merge_merge_request
create GitLab issue         -> gitlab::create_issue
```

If an expected tool is not returned, call `ctx_tools` with `action="refresh"` once and repeat the targeted `find` before declaring it unavailable.

## Direct route

Harr may also expose GitLab MCP directly to an agent host for diagnostics or hosts where direct access is useful. A direct registration is an alternate transport to the same service, not a second source of truth.

Do not query both direct and gateway routes for the same operation unless diagnosing the gateway.

## Scope

Use GitLab MCP for GitLab server/API state and operations. Use exact `git ...` commands through LeanCTX `ctx_shell` for local and remote Git repository operations such as status, branch checkout, history, fetch, pull, push and commits.

## Authentication and permissions

Harr stores the GitLab PAT privately and LeanCTX supplies it as `Private-Token` through secret-memento handling. Never print or inspect the PAT.

Harr configures the server with the full tool surface:

```text
GITLAB_PERMISSION_MODE=full
GITLAB_TOOLSETS=all
```

This exposes write tools such as `create_merge_request`; effective permissions are still bounded by the PAT and by GitLab project permissions.
