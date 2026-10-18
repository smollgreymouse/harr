---
name: harr-workspace
description: Synchronize the current agent session's already-known working folders with the Harr/LeanCTX Workspace. Use when the user asks to add, import, attach, or sync this Codex/OpenCode session's working folders, roots, repositories, or add-dir paths into Harr.
---
<!-- harr-managed-skill-v1 -->

# Harr Workspace session sync

Use this skill when the user asks the current agent/client to add **its own working folders** to Harr.

## Source of paths

Use only directories that are already explicit in the current session context:

- the current project/workspace root;
- additional workspace roots or working directories supplied by the host to this session (for example Codex extra/add-dir roots or OpenCode workspace roots);
- paths explicitly named by the user in the current request.

Do **not** discover candidates by walking `$HOME`, listing sibling repositories, searching mounted filesystems, parsing unrelated process state, or guessing paths that were not already known to this session.

If the host exposes only the current working directory and no additional roots, sync only that directory and report that no other session roots were available.

## Execution boundary

Prefer the direct **Harr Workspace MCP** server `harr-workspace`. It intentionally runs outside the LeanCTX gateway so it can change the Workspace authority that LeanCTX itself consumes.

Use these tools when available:

- `harr-workspace::workspace_get` with the current project root;
- `harr-workspace::workspace_sync` with the current project root and the already-known session roots.

Do **not** route Workspace control through LeanCTX `ctx_shell`, `ctx_workspace_get`, or another LeanCTX MCP tool. A not-yet-authorized root cannot bootstrap its own authorization through LeanCTX.

If the direct `harr-workspace` MCP is unavailable, native `harr workspace ...` commands are a fallback only when the client has host filesystem access to Harr config. If native execution reports a read-only/sandbox denial for Harr state, stop and report that the Workspace control MCP is unavailable; do not weaken the sandbox.

## Action

1. Read the current Workspace with `harr-workspace::workspace_get`, passing the current project root as `project`.

2. Build the list of absolute working-folder paths already known to this session. Keep the current project root in the list; Harr will safely skip it as the primary root.

3. Call `harr-workspace::workspace_sync` once:

```text
project = /absolute/current/project
paths = [/absolute/current/project, /absolute/extra/root, ...]
```

`workspace_sync` only **adds** missing roots. It never removes existing roots. The server rejects filesystem root, the user home directory, and broad parents of the Workspace primary root. Harr canonicalizes paths, skips the primary root, already-present roots and duplicate inputs, and performs revisioned additions against the live Workspace store.

4. Read the Workspace again with `harr-workspace::workspace_get` and report which roots were added or skipped.

### CLI fallback

For a non-sandboxed host that does not have the direct MCP registration, the equivalent commands are:

```text
harr workspace show
harr workspace sync /absolute/current/project /absolute/extra/root ...
harr workspace show
```

## Boundaries

- Never remove a Workspace root unless the user separately asks for removal.
- Never add `$HOME`, `/`, broad parent directories, or unrelated repositories merely because they are readable.
- Do not claim that adding a root grants the agent OS/sandbox permissions. It only authorizes that root inside Harr-managed LeanCTX; the client may still be unable to read/write it because of its own sandbox.
- Do not restart Codex/OpenCode or LeanCTX after a successful sync; the Harr Workspace store is live and the next LeanCTX request sees the new roots.
