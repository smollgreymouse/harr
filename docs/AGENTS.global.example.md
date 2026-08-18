# Harr global AGENTS example

Harr injects this policy automatically with `harr agents apply`; this file is documentation only.

For Codex the rendered block is:

<!-- harr-tool-policy:start -->
## Harr tool routing

- Investigation uses MCP; editing uses the native host editor.
- Normal MCP surface is LeanCTX only; specialized MCPs stay behind its gateway.
- Cross-file structure, flow, relationships, dependencies, architecture, impact, callers/references: FIRST investigation call MUST be `ctx_tools` with `action="call"`, `tool="codegraph::codegraph_explore"`, `arguments={"query":"<task or relevant symbols/files>"}`.
- CodeGraph calls are sequential. Source returned by CodeGraph counts as already read; if another source-code area remains unresolved, make another targeted CodeGraph call before generic read/search/glob/shell.
- Git repository state/history/branches/remotes/fetch/pull/push/commits: use `git-mcp` through `ctx_tools` when configured. GitLab MR/pipeline/job/issue/project/server data: use `gitlab` through `ctx_tools`.
- Use `ctx_read` only for missing exact evidence; `ctx_search` only for a concrete unresolved text/symbol question; `ctx_glob` only for a narrowly scoped unknown path; `ctx_shell` only for runtime/command evidence not supplied by a specialized MCP.
- Never do broad repository inventory after CodeGraph. Do not duplicate one investigation through gateway and a direct MCP; direct MCPs are diagnostic/on-demand bypasses only.
- Use `ctx_call` for uncommon LeanCTX capabilities instead of expanding the permanent tool surface. Prefer LeanCTX read/search/glob/shell; native equivalents are fallback for config/docs/generated/non-indexed content or when LeanCTX is unavailable. Build/test only on explicit request.
<!-- harr-tool-policy:end -->

OpenCode receives the same routing policy with the six LeanCTX ids rendered as `lean-ctx_ctx_*` names and the stricter host rule `Do not use native read/grep/glob/bash.`

Everything outside the marked block in the real global `AGENTS.md` remains user-owned.
