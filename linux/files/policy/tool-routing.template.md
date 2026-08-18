<!-- harr-tool-policy:start -->
## Harr tool routing

- Investigation uses MCP; editing uses the native host editor.
- Harr-managed specialized MCPs stay behind LeanCTX; unrelated third-party MCPs/skills may coexist globally and follow their own explicit rules.
- Cross-file structure, flow, relationships, dependencies, architecture, impact, callers/references: FIRST investigation call MUST be `{{CTX_TOOLS}}` with `action="call"`, `tool="codegraph::codegraph_explore"`, `arguments={"query":"<task or relevant symbols/files>"}`.
- CodeGraph calls are sequential. Source returned by CodeGraph counts as already read; if another source-code area remains unresolved, make another targeted CodeGraph call before generic read/search/glob/shell.
- Local Git state/history/branches/add/commit/checkout: use `git-mcp` through `{{CTX_TOOLS}}` with `repo_path="."`. Git remote transport (`fetch`, `pull`, `push`) is not exposed by the reference Git MCP; use one exact `git ...` command through `{{CTX_SHELL}}`. GitLab MR/pipeline/job/issue/project/server data: use `gitlab` through `{{CTX_TOOLS}}`.
- Use `{{CTX_READ}}` only for missing exact evidence; `{{CTX_SEARCH}}` only for a concrete unresolved text/symbol question; `{{CTX_GLOB}}` only for a narrowly scoped unknown path; `{{CTX_SHELL}}` only for runtime/command evidence or Git remote transport not supplied by a specialized MCP.
- Never do broad repository inventory after CodeGraph. Do not duplicate one Harr-managed investigation through gateway and a direct MCP; Harr-managed direct MCPs are diagnostic/on-demand bypasses only.
- Use `{{CTX_CALL}}` for uncommon LeanCTX capabilities instead of expanding the permanent Harr tool surface. {{HOST_NATIVE_POLICY}} Build/test only on explicit request.
<!-- harr-tool-policy:end -->
