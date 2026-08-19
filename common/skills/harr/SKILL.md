---
name: harr
description: Harr installation and diagnostics only: managed component versions, MCP services, agent policy, secrets, and repair. Do not load for normal repository investigation; the compact Harr routing block in global AGENTS.md already defines tool order.
---
<!-- harr-managed-skill-v1 -->

# Harr operations

Use this skill only when installing, checking, or repairing the harness.

```text
harr status
harr install all
harr agents status
harr agents apply
harr leanctx status
harr leanctx apply
harr secret status
harr secret set gitlab
harr secret set grafana
harr mcp list
harr mcp status gitlab
harr mcp logs gitlab
```

Harr owns managed versions/configuration. Do not independently run upstream LeanCTX setup/update, CodeGraph upgrades, or global installs of Harr-managed MCP packages.

Load only the needed file under `references/` for component-specific diagnostics; never load all references by default.
