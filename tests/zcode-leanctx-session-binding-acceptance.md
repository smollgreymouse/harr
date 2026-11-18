# ZCode + LeanCTX session binding acceptance

This checklist covers the ZCode-owned MCP lease lifecycle. Harr's automated tests cover authority resolution and the LeanCTX host wrapper; they cannot exercise ZCode's private session runtime.

Use the Harr-pinned LeanCTX build that includes `workspace-root-validation-v1`, and the Harr wrapper/config under test. Do not use a global fixed `HARR_WORKSPACE_ROOT`.

## Fresh project session

1. Start a new ZCode session with a project directory selected before LeanCTX launches.
2. Confirm `ctx_workspace_get` reports that directory's canonical project root as the active primary Workspace and `authenticatedWorkspace: true`.
3. Confirm `ctx_tools list` includes the project-scoped CodeGraph server and that `ctx_shell` is available.

## Existing rootless session

1. Start a ZCode session before selecting a project and confirm LeanCTX reports `no-workspace` with the minimal rootless tool surface.
2. Select a project for that same session, then invoke ZCode's scoped `io.sessionLifecycleRestart(sessionId, workspace)` host operation for the same `sessionId` and selected workspace.
3. Confirm the old session runtime and its LeanCTX MCP lease have closed before the restarted runtime reconnects. Confirm the session ID and selected workspace are unchanged.
4. Repeat the Workspace, CodeGraph, and `ctx_shell` checks from the fresh-session case.
5. Keep a second ZCode chat active during the restart. Confirm its LeanCTX connection remains available and a tool call in that chat still succeeds.

## Resume and rootless controls

1. Resume a project-bound session without changing its workspace and confirm its bound Workspace remains correct.
2. Restart that same session again and confirm it reconnects successfully with the same Workspace.
3. Start another session without a selected project (or from an unsuitable broad directory such as `$HOME`) and confirm it remains rootless. Confirm Workspace/file access stays unavailable until it is restarted in a selected project session.

Do not count a healthy `revalidate: true` check or a disconnect/connect as proof of a fresh binding: the former can accept a live rootless connection, and the latter can reuse the pooled session entry during its idle grace period. Do not use a pool-wide close to refresh one chat.
