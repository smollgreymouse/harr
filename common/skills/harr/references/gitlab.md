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

## Merge request creation workflow

Treat a request to create an MR as one workflow spanning local Git and the GitLab API. Do not wait for `git push` to fail before discovering that GitLab write tools exist.

1. Derive the GitLab project from the current repository remote and identify the current source branch and intended target branch. Do not reuse a project ID from another task or repository.
2. Prepare/inspect the local commit with exact `git ...` commands through `ctx_shell`.
3. Before publishing, discover the required GitLab tools with targeted queries, at minimum `gitlab::create_merge_request` plus user lookup when assignees/reviewers were requested.
4. Resolve requested assignees/reviewers to GitLab user IDs. Git commit author, GitLab MR author, assignee and reviewer are separate concepts.
5. Attempt the normal publish path with `git push -u <remote> <branch>` through `ctx_shell`.
6. If push succeeds, create the MR through `gitlab::create_merge_request`, set the requested assignee/reviewer IDs when supported, then verify the result with `gitlab::get_merge_request` before reporting success.

### Push/auth failure fallback

A Git transport/authentication failure does not by itself mean MR creation is impossible. If GitLab MCP is enabled and the local change can be represented faithfully through repository file APIs:

1. Discover `create branch`, `push files`/file update, diff and MR-create capabilities with targeted `ctx_tools find` calls. Prefer a batched/single-commit file operation such as `gitlab::push_files` when available instead of one GitLab commit per file.
2. Create the remote source branch from the intended target branch.
3. Mirror the **actual local diff**, not a manually reconstructed approximation. Include additions, updates and deletions; if an expected file operation is not found, refresh and search for that exact operation before giving up.
4. Verify the remote branch diff with GitLab MCP and compare it with the intended local diff before creating the MR.
5. Create the MR and verify its source/target branches, state, assignee/reviewer IDs and resulting diff.
6. State explicitly that API fallback created different remote commit SHA(s) from the local commit, even if the final tree/diff is equivalent.

Do not silently use a browser, `curl`, or expose/use the PAT manually while the enabled GitLab MCP can perform the operation. Do not use the API fallback if the local change cannot be represented exactly, for example unsupported binary, symlink, submodule or mode-only changes; report that limitation instead.

### Identity rules

- Git commit author comes from Git configuration/commit metadata.
- GitLab MR author is the authenticated GitLab identity behind the PAT/session. It is not assignable like a reviewer or assignee.
- Assignees and reviewers are explicit GitLab users and should be resolved to IDs before MR creation/update.
- Never claim an MR author/assignee/reviewer was set merely because a name was requested. Verify the created MR.

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
