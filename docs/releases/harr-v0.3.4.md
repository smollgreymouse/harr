# Harr 0.3.4

Harr 0.3.4 is a focused read-only status hotfix on top of Harr 0.3.3.

Status and inspection commands no longer create or rewrite Harr MCP selection state. In particular, `harr status`, `harr mcp status`, `harr mcp list`, `harr mcp available`, and secret status now operate without mutating `mcp-selection.json` or `mcp-registry.json`.

When no effective registry exists, status commands build an ephemeral registry under a temporary directory instead of bootstrapping user configuration. Existing read-only selection files are also supported without modification.

A dedicated regression test exercises both an absent Harr config directory and an existing non-writable config directory, and is part of the Linux selftest workflow.

This release retains the Codex memory-routing fix from Harr 0.3.3 and keeps LeanCTX pinned to `harr-v3.11.0-unified.4@afc9715d6d5a`.
