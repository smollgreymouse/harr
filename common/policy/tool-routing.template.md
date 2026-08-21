<!-- harr-tool-policy:start -->
## Harr tool routing

- Investigation uses MCP; editing uses the native host editor.
- Harr-managed specialized MCPs stay behind LeanCTX; unrelated third-party MCPs/skills may coexist globally and follow their own explicit rules.
- Cross-file structure, flow, relationships, dependencies, architecture, impact, callers/references: FIRST investigation call MUST be `{{CTX_TOOLS}}` with `action="call"`, `tool="codegraph::codegraph_explore"`, `arguments={"query":"<task or relevant symbols/files>"}`.
- CodeGraph calls are sequential. Source returned by CodeGraph counts as already read; if another source-code area remains unresolved, make another targeted CodeGraph call before generic read/search/glob/shell.
- Git repository state/history/branches/remotes/fetch/pull/push/commits: use one exact `git ...` command through `{{CTX_SHELL}}`.
<!-- harr-mcp:gitlab:start -->
- GitLab API operations: use `gitlab` through `{{CTX_TOOLS}}`. Gateway discovery is ranked/limited, so never infer that a capability is absent from an earlier `find`; for writes do a verb-specific `find` first (for example `create GitLab merge request` -> `gitlab::create_merge_request`) and `refresh` once before declaring an expected tool unavailable.
- Creating a GitLab MR is a combined Git + GitLab workflow: derive the GitLab project and source branch from the current repository, prepare the local commit, discover the MR/user tools up front, push the branch with exact `git ...` through `{{CTX_SHELL}}`, then create/update the MR and reviewers through `{{CTX_TOOLS}}`. If push fails only because of Git transport/authentication, do not stop merely because the remote branch is missing: if the local diff can be represented exactly through GitLab MCP, create the remote branch from the intended target, mirror the local diff (prefer a batched/single-commit file API when available), verify the resulting remote branch diff against the intended local diff, then create the MR. Do not use browser/curl/manual tokens while the enabled GitLab MCP can perform the operation. If the diff cannot be represented faithfully (for example unsupported binary/symlink/submodule/mode-only changes), report that limitation instead of approximating it.
- Do not conflate Git commit author, GitLab MR author, assignee and reviewer. The MR author is the authenticated GitLab identity and is not assignable like a reviewer; resolve requested assignees/reviewers to GitLab user IDs and verify the created MR before claiming those identities were set.
<!-- harr-mcp:gitlab:end -->
<!-- harr-mcp:grafana:start -->
- Grafana dashboard work: use `grafana` through `{{CTX_TOOLS}}`; prefer `search_dashboards` -> `get_dashboard_summary` -> targeted property/panel-query reads -> patch `update_dashboard`, avoiding complete dashboard JSON unless necessary.
<!-- harr-mcp:grafana:end -->
- Use `{{CTX_READ}}` only for missing exact evidence; `{{CTX_SEARCH}}` only for a concrete unresolved text/symbol question; `{{CTX_GLOB}}` only for a narrowly scoped unknown path; `{{CTX_SHELL}}` only for runtime/command evidence and Git operations.
- Never do broad repository inventory after CodeGraph. Do not duplicate one Harr-managed investigation through gateway and a direct MCP; Harr-managed direct MCPs are diagnostic/on-demand bypasses only.
- Use `{{CTX_CALL}}` for uncommon LeanCTX capabilities instead of expanding the permanent Harr tool surface. {{HOST_NATIVE_POLICY}} Build/test only on explicit request.
<!-- harr-tool-policy:end -->
