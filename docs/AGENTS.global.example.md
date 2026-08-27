# Harr global AGENTS example

After the first `./install.sh --clean`, Harr owns the complete global `AGENTS.md` for each supported host. The old file is in the pre-Harr rollback snapshot; Harr does not merge its rules into it.

For Codex the generated file is equivalent to:

<!-- harr-tool-policy:start -->
## Harr tool routing

- Investigation uses MCP; editing uses the native host editor.
- Harr-managed specialized MCPs stay behind LeanCTX; unrelated third-party MCPs/skills may coexist globally and follow their own explicit rules.
- Cross-file structure, flow, relationships, dependencies, architecture, impact, callers/references: FIRST investigation call MUST be `ctx_tools` with `action="call"`, `tool="codegraph::codegraph_explore"`, `arguments={"query":"<task or relevant symbols/files>"}`.
- CodeGraph calls are sequential. Source returned by CodeGraph counts as already read; if another source-code area remains unresolved, make another targeted CodeGraph call before generic read/search/glob/shell.
- Git repository state/history/branches/remotes/fetch/pull/push/commits: use one exact `git ...` command through `ctx_shell`. GitLab MR/pipeline/job/issue/project/server data: use `gitlab` through `ctx_tools`.
- For a user-authorized implementation task, edits to in-scope workspace files and removal of exact generated/build/test artifacts inside that workspace are pre-approved; perform them without an additional confirmation. Use `ctx_shell` for the required local shell work instead of requesting native-Terminal elevation. Still ask before deleting source or user data, operating outside the workspace, or making an external write the user did not explicitly request.
- A Git commit or remote publish is pre-approved only when the user explicitly requested that exact action; perform it then without an additional confirmation.
- Use `ctx_read` only for missing exact evidence; `ctx_search` only for a concrete unresolved text/symbol question; `ctx_glob` only for a narrowly scoped unknown path; `ctx_shell` only for runtime/command evidence and Git operations.
- Never do broad repository inventory after CodeGraph. Do not duplicate one Harr-managed investigation through gateway and a direct MCP; Harr-managed direct MCPs are diagnostic/on-demand bypasses only.
- Use `ctx_call` for uncommon LeanCTX capabilities instead of expanding the permanent Harr tool surface. Prefer LeanCTX read/search/glob/shell; native equivalents are fallback for config/docs/generated/non-indexed content or when LeanCTX is unavailable. Build/test only on explicit request.
<!-- harr-tool-policy:end -->

OpenCode receives the same routing policy with the six LeanCTX ids rendered as `lean-ctx_ctx_*` names and the stricter host rule `Do not use native read/grep/glob/bash.`

Project-level `AGENTS.md` files are outside Harr ownership and are never read, modified, backed up, or restored by Harr.
