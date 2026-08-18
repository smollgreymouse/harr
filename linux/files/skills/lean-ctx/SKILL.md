---
name: lean-ctx
description: LeanCTX-specific troubleshooting/reference on a Harr-managed machine: minimal ctx_* surface, gateway semantics, cwd/project binding, secret handling, and repair. Do not load for normal repository investigation; global Harr policy already defines tool order.
---
<!-- harr-managed-skill-v1 -->

# LeanCTX under Harr

Use this skill only for LeanCTX-specific behavior or failures. Normal tool routing is already injected into the host's global `AGENTS.md` by Harr.

Harr owns LeanCTX and currently pins `3.9.15`. Do not run upstream `lean-ctx setup`, `lean-ctx onboard`, or `lean-ctx update`.

Direct Harr profile:

- `ctx_read`
- `ctx_shell`
- `ctx_search`
- `ctx_glob`
- `ctx_tools`
- `ctx_call`

Uncommon LeanCTX capabilities are reached through `ctx_call`; do not expand the permanent MCP surface. Editing stays native; `ctx_edit`/`ctx_patch` are disabled.

Gateway facts:

- CodeGraph: stdio child `codegraph serve --mcp`; inherits LeanCTX cwd, so wrong project binding means diagnose cwd/root rather than creating per-project Harr config.
- GitLab: Streamable HTTP at `http://127.0.0.1:3334/mcp`; PAT is restored by Harr's LeanCTX wrapper via secret-memento handling and must never be printed.

Repair/diagnostics:

```bash
harr status
harr leanctx status
harr leanctx apply
harr install all
```
