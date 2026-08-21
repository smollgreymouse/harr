<!-- harr-tool-policy:start -->
## Harr tool routing

- Investigation uses MCP; editing uses the native host editor.
- Harr-managed specialized MCPs stay behind LeanCTX; unrelated third-party MCPs/skills may coexist globally and follow their own explicit rules.
- Cross-file structure, flow, relationships, dependencies, architecture, impact, callers/references: FIRST investigation call MUST be `{{CTX_TOOLS}}` with `action="call"`, `tool="codegraph::codegraph_explore"`, `arguments={"query":"<task or relevant symbols/files>"}`.
- CodeGraph calls are sequential. Source returned by CodeGraph counts as already read; if another source-code area remains unresolved, make another targeted CodeGraph call before generic read/search/glob/shell.
- Git repository state/history/branches/remotes/fetch/pull/push/commits: use one exact `git ...` command through `{{CTX_SHELL}}`.
<!-- harr-mcp:gitlab:start -->
- GitLab API operations: use `gitlab` through `{{CTX_TOOLS}}`. Gateway discovery is ranked/limited, so never infer that a capability is absent from an earlier `find`; for writes do a verb-specific `find` first (for example `create GitLab merge request` -> `gitlab::create_merge_request`) and `refresh` once before declaring an expected tool unavailable.
<!-- harr-mcp:gitlab:end -->
<!-- harr-mcp:grafana:start -->
- Grafana dashboard work: use `grafana` through `{{CTX_TOOLS}}`; prefer `search_dashboards` -> `get_dashboard_summary` -> targeted property/panel-query reads -> patch `update_dashboard`, avoiding complete dashboard JSON unless necessary.
<!-- harr-mcp:grafana:end -->
- Use `{{CTX_READ}}` only for missing exact evidence; `{{CTX_SEARCH}}` only for a concrete unresolved text/symbol question; `{{CTX_GLOB}}` only for a narrowly scoped unknown path; `{{CTX_SHELL}}` only for runtime/command evidence and Git operations.
- Never do broad repository inventory after CodeGraph. Do not duplicate one Harr-managed investigation through gateway and a direct MCP; Harr-managed direct MCPs are diagnostic/on-demand bypasses only.
- Use `{{CTX_CALL}}` for uncommon LeanCTX capabilities instead of expanding the permanent Harr tool surface. {{HOST_NATIVE_POLICY}} Build/test only on explicit request.
<!-- harr-tool-policy:end -->
