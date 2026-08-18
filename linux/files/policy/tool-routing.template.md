<!-- harr-tool-policy:start -->
## Harr tool routing

- Investigation uses MCP; editing uses the native host editor.
- Normal MCP surface is LeanCTX only; specialized MCPs stay behind its gateway.
- Cross-file structure, flow, relationships, dependencies, architecture, impact, callers/references: FIRST investigation call MUST be `{{CTX_TOOLS}}` with `action="call"`, `tool="codegraph::codegraph_explore"`, `arguments={"query":"<task or relevant symbols/files>"}`.
- CodeGraph calls are sequential. Source returned by CodeGraph counts as already read; if another source-code area remains unresolved, make another targeted CodeGraph call before generic read/search/glob/shell.
- Git repository state/history/branches/remotes/fetch/pull/push/commits: use `git-mcp` through `{{CTX_TOOLS}}` when configured. GitLab MR/pipeline/job/issue/project/server data: use `gitlab` through `{{CTX_TOOLS}}`.
- Use `{{CTX_READ}}` only for missing exact evidence; `{{CTX_SEARCH}}` only for a concrete unresolved text/symbol question; `{{CTX_GLOB}}` only for a narrowly scoped unknown path; `{{CTX_SHELL}}` only for runtime/command evidence not supplied by a specialized MCP.
- Never do broad repository inventory after CodeGraph. Do not duplicate one investigation through gateway and a direct MCP; direct MCPs are diagnostic/on-demand bypasses only.
- Use `{{CTX_CALL}}` for uncommon LeanCTX capabilities instead of expanding the permanent tool surface. Do not use native read/grep/glob/bash. Build/test only on explicit request.
<!-- harr-tool-policy:end -->
