---
name: harr-workspace
description: Synchronize the current agent session's already-known working folders with the Harr/LeanCTX Workspace. Use when the user asks to add, import, attach, or sync this ZCode session's roots, or when the agent creates a Git worktree/checkout that it will work in.
---
<!-- harr-managed-skill-v1 -->

# Harr Workspace session sync (ZCode)

Use this skill when the user asks the current ZCode session to add **its own working folders** to Harr, or when an authorized task creates a new Git worktree/checkout that the agent must investigate or edit.

ZCode has no direct `harr-workspace` MCP registration: Workspace authority control runs through the `harr workspace` CLI with native Bash. LeanCTX itself stays the single Harr MCP; never bootstrap Workspace authority through it.

## Source of paths

Use only directories that are already explicit in the current session context:

- the current project/workspace root;
- additional working directories supplied by the host to this session (for example ZCode additional working directories);
- paths explicitly named by the user in the current request;
- the exact path returned by a successful Git worktree/checkout creation performed for the current user-authorized task.

Do **not** discover candidates by walking `$HOME`, listing sibling repositories, searching mounted filesystems, parsing unrelated process state, or guessing paths that were not already known to this session.

If the host exposes only the current working directory and no additional roots, sync only that directory and report that no other session roots were available.

## Newly created Git worktrees

After a successful `git worktree add` / `harr git worktree add`, if the agent will work in that checkout, register its exact absolute directory **before** the first LeanCTX source search/read or shell command in the checkout. A worktree is not implicitly registered merely because its source repository is a Workspace root.

Use add-only `harr workspace sync <new checkout absolute path>` through native Bash, then confirm with `harr workspace show` that the exact root is active. Do not derive the root from a not-yet-authorized checkout's own output without the exact path, do not route Workspace control through LeanCTX, and do not sync `/tmp` or another broad parent in place of the exact checkout.

If registration or verification fails, report the blocker and do not investigate the checkout with further workarounds. An existing root remains unchanged. Do not register new worktrees unrelated to the authorized task.

## Execution boundary

Workspace control must not route through LeanCTX `ctx_shell`, `ctx_workspace_get`, or another LeanCTX MCP tool. A not-yet-authorized root cannot bootstrap its own authorization through LeanCTX. ZCode native Bash is the permitted execution path because ZCode runs with host filesystem access to Harr config; if native execution reports a permission denial for Harr state, stop and report it; do not weaken the sandbox.

## Action

1. Read the current Workspace with `harr workspace show`.

2. Build the list of absolute working-folder paths already known to this session. Keep the current project root in the list; Harr will safely skip it as the primary root.

3. Call `harr workspace sync` once with the already-known session roots:

```text
harr workspace sync /absolute/current/project /absolute/extra/root ...
```

The command only **adds** missing roots. It never removes existing roots. It rejects filesystem root, the user home directory, and broad parents of the Workspace primary root. Harr canonicalizes paths, skips the primary root, already-present roots and duplicate inputs, and performs revisioned additions against the live Workspace store.

4. Read the Workspace again with `harr workspace show` and report which roots were added or skipped. If Harr returns Workspace `warnings`, surface them to the user together with any provided `remove_command`; do not remove a warned root automatically.

## Boundaries

- Never remove a Workspace root unless the user separately asks for removal.
- Never add `$HOME`, `/`, broad parent directories, or unrelated repositories merely because they are readable.
- Do not claim that adding a root grants the agent OS/sandbox permissions. It only authorizes that root inside Harr-managed LeanCTX; ZCode may still be unable to read/write it because of its own permission system.
- Do not restart ZCode or LeanCTX after a successful sync; the Harr Workspace store is live and the next LeanCTX request sees the new roots.
