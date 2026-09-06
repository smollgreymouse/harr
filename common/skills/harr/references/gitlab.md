---
# GitLab MCP in Harr

GitLab MCP provides live GitLab API operations for merge requests, pipelines/jobs, issues, projects, users, variables and other GitLab server objects. It is not a Git transport.

## Responsibility boundary

Use local Git and host Git for repository data:

- local status, diff, history, configuration, branches and commits: exact `git ...` through `ctx_shell`;
- any command that contacts a remote: exact `harr git ...` through `ctx_shell` when the host service is ready;
- source-branch publication, upstream tracking and remote-SHA verification: Git, never GitLab repository-file APIs.

Use GitLab MCP for server/API objects:

- create, read and update merge requests;
- pipelines and jobs;
- issues, projects, users, assignees and reviewers;
- other GitLab metadata and administrative API operations exposed by the installed MCP.

The installed MCP exposes `create_branch`, `create_or_update_file`, and `push_files`, but these create server-side refs or API commits. They do not push the caller's local commit or preserve its SHA and full Git semantics. Never use them to mirror a local diff or replace unavailable Git transport.

## Normal route

```text
agent -> LeanCTX gateway -> GitLab MCP HTTP service -> GitLab API
```

The long-lived MCP service is managed by Harr at `http://127.0.0.1:3334/mcp`.

Use `ctx_tools` to discover and call `gitlab::*` tools. Gateway discovery is ranked and returns only a short top-N list, not the full GitLab catalog. Never conclude that a capability is unavailable merely because it was absent from a previous broad result.

When the workflow defines an expected tool, use its exact bare name as the discovery query:

```text
create_merge_request -> gitlab::create_merge_request
get_merge_request    -> gitlab::get_merge_request
update_merge_request -> gitlab::update_merge_request
merge_merge_request  -> gitlab::merge_merge_request
create_issue          -> gitlab::create_issue
```

A discovery succeeds only when it returns the expected qualified tool. A related tool is neither a substitute nor evidence that the expected tool is unavailable. If the expected tool is not returned, refresh the gateway once and repeat the same query before declaring it unavailable.

## Merge request creation workflow

Treat a request to create an MR as one workflow spanning Git and the GitLab API.

1. Derive the GitLab project from the configured repository remote and determine the intended target branch separately.
2. Read the current branch with `git symbolic-ref --quiet --short HEAD`. Detached HEAD is invalid; source branch must differ from target branch.
3. Prepare and inspect the local commit with exact local Git commands.
4. Read local `HEAD` with `git rev-parse HEAD`.
5. Publish the current branch with an explicit destination, never an implicit push:

```text
harr git push --set-upstream <remote> HEAD:refs/heads/<current-local-branch>
```

6. Read the exact remote ref:

```text
harr git ls-remote <remote> refs/heads/<current-local-branch>
```

Require the returned SHA to equal local `HEAD`. Verify the current branch now tracks `<remote>/<current-local-branch>`. A stale upstream such as `origin/master` must never select the push destination or MR source branch.

7. Discover `gitlab::create_merge_request` by its exact bare name. Resolve requested assignees/reviewers to GitLab user IDs.
8. Create the MR with `source_branch=<current-local-branch>` and the independently determined target branch.
9. Verify the new MR through `gitlab::get_merge_request` before reporting success.

`gitlab::update_merge_request` is only for an already identified existing MR and is never a fallback for creation.

If host Git cannot publish or verify the branch, stop and report the Git transport failure. Do not create a replacement branch/commit through GitLab APIs, do not switch credentials, and do not use browser, `curl`, or a manually exposed token.

## Identity rules

- Git commit author comes from commit metadata.
- Git push authentication comes from the terminal SSH agent or Git credential helper used by the host service.
- GitLab MR author is the authenticated GitLab MCP identity behind the PAT. It is not assignable like a reviewer or assignee.
- Assignees and reviewers are explicit GitLab users and must be resolved to IDs.
- Never infer that these identities are equal, and never claim an identity was set without verifying the resulting MR.

## Direct route

Harr may expose the GitLab MCP service directly for diagnostics. A direct registration is an alternate transport to the same API service, not a second source of truth. Do not query both direct and gateway routes for the same operation unless diagnosing the gateway.

## Authentication and permissions

Harr stores the GitLab PAT privately and LeanCTX supplies it as `Private-Token` through secret-memento handling. The PAT authenticates GitLab API calls only; host Git does not read or inject it.

Harr configures the service with:

```text
GITLAB_PERMISSION_MODE=full
GITLAB_TOOLSETS=all
```

This exposes write tools such as `create_merge_request`; effective permissions remain bounded by the PAT and GitLab project permissions.
