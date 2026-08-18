---
name: harr
description: Compact routing policy for Harr-managed MCP tools. Use to choose the right tool/route; load detailed references only for diagnostics.
---
<!-- harr-managed-skill-v1 -->

# Harr routing

Default rule: **specialized MCP through LeanCTX gateway; direct MCPs are diagnostic bypasses, not the normal route.**

- Code structure/symbols/references/callers/architecture/blast radius → **CodeGraph first** through `ctx_tools`.
- Git status/branches/history/remotes/fetch/pull/push/commits → **git-mcp** through `ctx_tools` when configured.
- GitLab MR/pipeline/job/issue/project/server data → **gitlab** through `ctx_tools`.
- Known-file reads, exact text search, file discovery, shell/tests → LeanCTX `ctx_read` / `ctx_search` / `ctx_glob` / `ctx_shell`.
- Editing → native host editor.
- Do not repeat the same investigation through both gateway and direct MCP. Use direct MCP only if the gateway route fails or for diagnosis.

For a normal coding task: **CodeGraph → only missing LeanCTX reads/searches → edit → Git MCP as needed.** Source already returned by CodeGraph counts as read.

Only for troubleshooting, load the relevant file under `references/`; do not load all references by default.
