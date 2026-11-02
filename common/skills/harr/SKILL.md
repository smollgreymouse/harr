---
name: harr
description: Harr installation, status, doctor/repair, managed component configuration, transports, secrets, and agent setup. Do not load for ordinary repository investigation.
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
harr agents orchestration {status|enable|disable}
harr agents asa status
harr agents asa configure [--model MODEL] [--effort EFFORT]
harr mcp available
harr mcp configure
harr secret status
```

Use `harr doctor NAME` for end-to-end failures. Never run `harr doctor --repair` merely because doctor reports a failure. Repair mutates Harr-owned runtime state: run `--repair` only when the user explicitly asks to repair, restore, fix, recover, or equivalent. If repair is `BLOCKED` or `ROLLED_BACK`, stop and report the evidence rather than inventing a second repair path.

Do not bypass Harr with upstream installers or manual replacement of Harr-owned runtime/config files.

Load only the reference needed for the current operation:

- installation/component/config commands -> `references/operations.md`
- LeanCTX/CodeGraph -> `references/leanctx.md` / `references/codegraph.md`
- host Git / merge-request transport -> `references/git.md`
- Kubernetes -> `references/kubernetes.md`
- named Ein setup -> `references/einherjar.md`
- optional MCP diagnostics -> the matching reference file

Never load all references by default.
