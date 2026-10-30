# Harr 0.3.2

Harr 0.3.2 hardens LeanCTX Workspace and Git worktree lifecycle handling and pins the new Harr LeanCTX build `harr-v3.11.0-unified.3@bf1455d337e9`.

Workspace configuration is now separated from effective filesystem authority. An additional root that disappears after `git worktree remove`, an unmount, or another external lifecycle change no longer makes the Workspace store unreadable or kills LeanCTX startup. Missing roots remain visible for diagnosis and can be removed explicitly, while they are excluded from effective authority immediately.

Git worktrees now use checkout identity rather than path alone. Sibling worktrees from the same local repository are topology, not independent additional roots; a moved worktree retains its Workspace identity; and recreating a different checkout at an old path does not resurrect stale authority. Authority fingerprints also cover live root availability and Git checkout generation, so cache namespaces and publication fences revoke results when filesystem authority changes without a Workspace revision change.

If the primary worktree disappears, LeanCTX now keeps the MCP protocol and `ctx_workspace_get/list/diagnose` control surface alive in a fail-closed diagnostic mode instead of exiting before MCP initialization. Content tools remain denied until primary authority is valid again.

This release also carries the corrected long-lived `ctx_tools` lifecycle: discovery and refresh use the gateway's own downstream timeouts rather than the generic tool watchdog. Regression coverage includes a deliberately slow downstream MCP whose `tools/list` takes longer than the generic watchdog while `ctx_tools find/refresh` must still complete successfully.

Validation includes production-binary black-box Workspace tests for missing/add/remove/move/remove-primary/recreate lifecycle, Harr CLI worktree tests, a slow `ctx_tools` discovery regression, and memory-bounded Rust compilation. The final LeanCTX `cargo check --lib -j1` peaked at 5.5 GiB; the production binary build completed within a 9 GiB cgroup.
