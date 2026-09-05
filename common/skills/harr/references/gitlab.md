# GitLab MCP in Harr

GitLab MCP provides live GitLab API operations for merge requests, pipelines/jobs, issues, projects, users, variables and other GitLab entities.

## Normal route

The normal Harr route is:

```text
agent -> LeanCTX gateway -> GitLab MCP HTTP service -> GitLab API
```

The long-lived MCP service is managed by Harr at `http://127.0.0.1:3334/mcp`.

Use `ctx_tools` to discover/call `gitlab::*` tools when using this route. LeanCTX gateway discovery is ranked and returns only a short top-N list, not the full GitLab catalog. Never conclude that a GitLab capability is unavailable merely because it was absent from a previous broad `find` result.

When the workflow defines an expected downstream tool, use its exact bare name as the discovery query. Otherwise, use a targeted verb-and-object query. Examples:

```text
create_merge_request -> gitlab::create_merge_request
update_merge_request -> gitlab::update_merge_request
merge_merge_request  -> gitlab::merge_merge_request
create_issue          -> gitlab::create_issue
```

A discovery succeeds only when it returns the expected qualified tool. A related result, such as `update_merge_request` while creating an MR, is neither a substitute nor evidence that the expected tool is unavailable. If an expected tool is not returned, call `ctx_tools` with `action="refresh"` once and repeat the same query before declaring it unavailable.

## Merge request creation workflow

Treat a request to create an MR as one workflow spanning local Git and the GitLab API. Do not infer the MR source branch from Git upstream configuration.

1. Derive the GitLab project from the current repository remote and determine the intended target branch separately.
2. Read the current **named local branch** with Git. Detached HEAD is not a valid MR source; the source branch must also differ from the intended target branch.
3. Prepare/inspect the local commit with exact `git ...` commands through `ctx_shell`.
4. Before publishing, discover the required GitLab tools with targeted queries, at minimum `gitlab::create_merge_request` plus user lookup when assignees/reviewers were requested.
5. Resolve requested assignees/reviewers to GitLab user IDs. Git commit author, GitLab MR author, assignee and reviewer are separate concepts.
6. Publish the current local branch with:

```text
harr gitlab publish [remote]
```

7. Create the MR through `gitlab::create_merge_request` with `source_branch=<current-local-branch>` and the separately determined target branch. `gitlab::update_merge_request` is only for an already identified existing MR and is never a fallback for creation. Verify the new MR with `gitlab::get_merge_request` before reporting success.

### Why `harr gitlab publish` is mandatory for MR source publication

For GitLab MR creation Harr deliberately does **not** use a bare `git push`, because a local feature branch may still track `origin/master` or another target branch. Depending on Git push configuration, an implicit push can therefore target a protected branch.

`harr gitlab publish` is branch-safe and host-independent:

- it takes the MR source name from the current local branch, never from `branch.<name>.remote` / `branch.<name>.merge`;
- it uses Harr's GitLab HTTPS/PAT transport directly, so no SSH attempt is needed first;
- it pushes the exact refspec `HEAD:refs/heads/<current-local-branch>`;
- it preserves the real local Git commit SHA and all Git semantics, including deletions, renames, binary files, symlinks, submodules and mode changes;
- it verifies the remote same-named branch SHA equals local `HEAD`;
- after successful verification it sets local upstream to `<remote>/<current-local-branch>`, replacing a stale upstream such as `origin/master`.

Example for local branch `ADSDSP-7737-final-prerank-cleanup`:

```text
harr gitlab publish origin
```

is semantically equivalent to a secure authenticated:

```text
git push -u origin HEAD:refs/heads/ADSDSP-7737-final-prerank-cleanup
```

plus remote-SHA verification and explicit upstream normalization.

### Explicit custom push

For non-MR workflows or genuinely custom push refspecs/options, Harr also exposes:

```text
harr gitlab push [git-push-options] [remote] [refspec...]
```

This uses the same secure GitLab HTTPS/PAT transport but does not impose the current-branch MR invariant.

### Fetch GitLab refs

For a remote read from an isolated agent host, use:

```text
harr gitlab fetch [remote] [refspec...]
```

For example:

```text
harr gitlab fetch origin master
```

Harr resolves the selected remote, verifies that its host matches `GITLAB_API_URL`, then runs real `git fetch` over HTTPS with the stored PAT through `GIT_ASKPASS`. It does not change the repository remote URL or write global Git URL rewrites. `--all`, `--multiple`, and recursive-submodule fetch options are refused so the PAT remains scoped to the selected GitLab remote.

### Repository-file API fallback

Only if Harr Git transport itself cannot be used should repository-file API mirroring be considered.

1. Discover the exact repository write capabilities with targeted `ctx_tools find` calls.
2. Create the remote source branch from the intended target branch.
3. Mirror the **actual local diff**, not a manually reconstructed approximation, using only operations the enabled GitLab MCP actually exposes.
4. Verify the remote branch diff with GitLab MCP and compare it with the intended local diff before creating the MR.
5. Create the MR and verify its source/target branches, state, assignee/reviewer IDs and resulting diff.
6. State explicitly that API fallback created different remote commit SHA(s) from the local commit, even if the final tree/diff is equivalent.

Do not claim this fallback can represent deletions or other Git changes unless the currently installed GitLab MCP exposes the required operation. In pinned `@zereight/mcp-gitlab 2.1.48`, repository-file deletion is not exposed, so a diff containing a deletion cannot be mirrored faithfully through that MCP alone. Do not silently use a browser, `curl`, or expose/use the PAT manually while Harr's HTTPS Git transport or the enabled GitLab MCP can perform the operation.

### Identity rules

- Git commit author comes from Git configuration/commit metadata.
- GitLab MR author is the authenticated GitLab identity behind the PAT/session. It is not assignable like a reviewer or assignee.
- Assignees and reviewers are explicit GitLab users and should be resolved to IDs before MR creation/update.
- Never claim an MR author/assignee/reviewer was set merely because a name was requested. Verify the created MR.

## Direct route

Harr may also expose GitLab MCP directly to an agent host for diagnostics or hosts where direct access is useful. A direct registration is an alternate transport to the same service, not a second source of truth.

Do not query both direct and gateway routes for the same operation unless diagnosing the gateway.

## Scope

Use GitLab MCP for GitLab server/API state and operations. Use exact `git ...` commands through LeanCTX `ctx_shell` for ordinary local Git operations. Use `harr gitlab fetch` for GitLab PAT-authenticated remote reads, `harr gitlab publish` specifically to publish a GitLab MR source branch safely, and `harr gitlab push` for explicit GitLab HTTPS/PAT push operations. If the user explicitly selects their normal terminal Git authentication instead, use `harr git ...`; never silently switch between the PAT identity and the terminal SSH/credential-helper identity.

## Authentication and permissions

Harr stores the GitLab PAT privately and LeanCTX supplies it as `Private-Token` through secret-memento handling. The same local secret is used by Harr's Git HTTPS transport through `GIT_ASKPASS`; Harr does not print the PAT or persist it into Git configuration.

Harr configures the server with the full tool surface:

```text
GITLAB_PERMISSION_MODE=full
GITLAB_TOOLSETS=all
```

This exposes write tools such as `create_merge_request`; effective permissions are still bounded by the PAT and by GitLab project permissions.
