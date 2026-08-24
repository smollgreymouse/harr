<!-- harr-tool-policy:start -->
## Harr tool routing

- Investigation uses MCP; editing uses the native host editor.
- Harr-managed specialized MCPs stay behind LeanCTX; unrelated third-party MCPs/skills may coexist globally and follow their own explicit rules.
- Cross-file structure, flow, relationships, dependencies, architecture, impact, callers/references: FIRST investigation call MUST be `{{CTX_TOOLS}}` with `action="call"`, `tool="codegraph::codegraph_explore"`, `arguments={"query":"<task or relevant symbols/files>"}`.
- CodeGraph calls are sequential. Source returned by CodeGraph counts as already read; if another source-code area remains unresolved, make another targeted CodeGraph call before generic read/search/glob/shell.
- Git repository state/history/branches/remotes/fetch/pull/push/commits: use one exact `git ...` command through `{{CTX_SHELL}}` except the GitLab MR source-branch publish workflow below.
- Kubernetes cluster operations: use the real kubectl only through `harr kubectl ...` via `{{CTX_SHELL}}`. Do not use a Kubernetes MCP and do not use bare `kubectl`, because Harr supplies the managed portable kubeconfig for sandboxed/isolated hosts. Prefer narrow resource/namespace/label queries and bounded logs over broad `-A -o yaml` dumps unless the broad result is genuinely required. Use `harr kube status` for transport/config diagnostics; changing the snapshot is an explicit user setup operation via `harr kube configure` or `harr kube sync`.
<!-- harr-mcp:gitlab:start -->
- GitLab API operations: use `gitlab` through `{{CTX_TOOLS}}`. Gateway discovery is ranked/limited, so never infer that a capability is absent from an earlier `find`; for writes do a verb-specific `find` first (for example `create GitLab merge request` -> `gitlab::create_merge_request`) and `refresh` once before declaring an expected tool unavailable.
- Creating a GitLab MR is a combined Git + GitLab workflow. The MR source branch is ALWAYS the current named local branch, never its configured upstream. Require a non-detached current branch and require source branch != intended target branch.
- Publish the MR source branch with `harr git publish [remote]` through `{{CTX_SHELL}}`, not with a bare/implicit `git push`. `harr git publish` uses Harr's GitLab HTTPS/PAT transport directly (no preliminary SSH attempt), pushes the explicit refspec `HEAD:refs/heads/<current-local-branch>`, verifies the remote branch SHA equals local `HEAD`, and sets local upstream to `<remote>/<current-local-branch>`. A stale upstream such as `origin/master` must never determine the push destination or `source_branch`.
- After publish, create/update the MR through `{{CTX_TOOLS}}` with `source_branch=<current-local-branch>` and the separately determined target branch. Verify the remote source branch and resulting MR before reporting success.
- `harr git push ...` remains available for an explicit real Git-over-HTTPS push when a caller genuinely needs custom push options/refspecs. Repository-file API mirroring is only a last resort if Harr Git transport itself cannot be used; mirror only operations the enabled GitLab MCP can represent faithfully and verify the resulting diff before creating an MR. Do not use browser/curl/manual tokens while Harr's GitLab transport or enabled GitLab MCP can perform the operation.
- Do not conflate Git commit author, GitLab MR author, assignee and reviewer. The MR author is the authenticated GitLab identity and is not assignable like a reviewer; resolve requested assignees/reviewers to GitLab user IDs and verify the created MR before claiming those identities were set.
<!-- harr-mcp:gitlab:end -->
<!-- harr-mcp:grafana:start -->
- Grafana dashboard work: use `grafana` through `{{CTX_TOOLS}}`; prefer `search_dashboards` -> `get_dashboard_summary` -> targeted property/panel-query reads -> patch `update_dashboard`, avoiding complete dashboard JSON unless necessary.
<!-- harr-mcp:grafana:end -->
- Use `{{CTX_READ}}` only for missing exact evidence; `{{CTX_SEARCH}}` only for a concrete unresolved text/symbol question; `{{CTX_GLOB}}` only for a narrowly scoped unknown path; `{{CTX_SHELL}}` only for runtime/command evidence plus Git and Kubernetes operations.
- Never do broad repository inventory after CodeGraph. Do not duplicate one Harr-managed investigation through gateway and a direct MCP; Harr-managed direct MCPs are diagnostic/on-demand bypasses only.
- Use `{{CTX_CALL}}` for uncommon LeanCTX capabilities instead of expanding the permanent Harr tool surface. {{HOST_NATIVE_POLICY}} Build/test only on explicit request.
<!-- harr-tool-policy:end -->
