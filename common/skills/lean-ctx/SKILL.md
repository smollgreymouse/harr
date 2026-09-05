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

Use `ctx_call` only for a known, non-editing uncommon capability; do not use it to discover edit/patch tools. Editing stays native; `ctx_edit`/`ctx_patch` are disabled.

Git routing through `ctx_shell`:

- Local repository operations use one exact `git ...` command.
- On Linux, remote operations that should use the user's terminal authentication use one exact `harr git ...` command; do not attempt bare network Git first.
- Preserve repository cwd. If LeanCTX rejects that cwd because it belongs to another project root, use an allowed cwd and pass `harr git -C /absolute/repository/path ...`.
- GitLab PAT operations remain the distinct `harr gitlab fetch/publish/push` route. Do not silently switch between PAT and terminal identities.
- Diagnose the host bridge with `harr status`; do not alter remotes, `IdentityFile`, `core.sshCommand`, or agent sockets to work around the sandbox.

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
