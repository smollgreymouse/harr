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

## Action

1. Inspect the existing Harr Workspace:

```text
harr workspace show
```

2. Build the list of absolute working-folder paths already known to this session. Keep the current project root in the list; Harr will safely skip it as the primary root.

3. Synchronize those paths in one command:

```text
harr workspace sync /absolute/current/project /absolute/extra/root ...
```

`sync` only **adds** missing roots. It never removes existing roots. Harr canonicalizes the paths, skips the primary root, already-present roots and duplicate inputs, and performs revisioned additions against the live Workspace store.

4. Verify the result:

```text
harr workspace show
```

Report which roots were added and which were skipped. Treat a non-zero exit as a failed sync and report the exact Harr error.

## Boundaries

- Never remove a Workspace root unless the user separately asks for removal.
- Never add `$HOME`, `/`, broad parent directories, or unrelated repositories merely because they are readable.
- Do not claim that adding a root grants the agent OS/sandbox permissions. It only authorizes that root inside Harr-managed LeanCTX; the client may still be unable to read/write it because of its own sandbox.
- Do not restart Codex/OpenCode or LeanCTX after a successful sync; the Harr Workspace store is live and the next LeanCTX request sees the new roots.
