---
name: harr
description: Harr installation, status, doctor/repair, managed component configuration, transports, secrets, agent setup, and rootless LeanCTX startup with explicit project binding. Do not load for ordinary repository investigation.
---
<!-- harr-managed-skill-v1 -->

# Harr

Harr owns its installed harness state: pinned components, generated configuration, secrets, agent policy/skills, and managed transports.

Start with the cheapest operation that answers the request:

```text
harr status
harr doctor [NAME]
harr doctor [NAME] --repair [--dry-run]
harr agents status
harr agents apply [all|codex|opencode]
harr agents harness {status|enable|disable}
harr agents orchestration {status|enable|disable}
harr agents asa status
harr agents asa configure [--model MODEL] [--effort EFFORT]
harr mcp available
harr mcp configure
harr secret status
```

Use `harr doctor NAME` for end-to-end failures. Never run `harr doctor --repair` merely because doctor reports a failure. Repair mutates Harr-owned runtime state: run `--repair` only when the user explicitly asks to repair, restore, fix, recover, or equivalent. If repair is `BLOCKED` or `ROLLED_BACK`, stop and report the evidence rather than inventing a second repair path.

Do not bypass Harr with upstream installers or manual replacement of Harr-owned runtime/config files.

For global OpenCode/ZCode sessions that start without a project, LeanCTX starts rootless by default. If the user later supplies project folders, follow `harr-workspace` to register those exact paths and `lean-ctx` to explain how a new LeanCTX launch binds the primary root. Workspace sync alone does not grant access to a running rootless process.

Load only the reference needed for the current operation:

- installation/component/config commands -> `references/operations.md`
- LeanCTX/CodeGraph -> `references/leanctx.md` / `references/codegraph.md`
- host Git / merge-request transport -> `references/git.md`
- Kubernetes -> `references/kubernetes.md`
- named Ein setup -> `references/einherjar.md`
- project-scoped MCP customization (overlay, trust, profiles) -> `references/project-mcp.md`
- optional MCP diagnostics -> the matching reference file

Never load all references by default.
