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
harr mcp available
harr mcp configure
harr mcp list
<!-- harr-mcp:gitlab:start -->
harr secret set gitlab
harr git publish [remote]
harr git push [git-push-options] [remote] [refspec...]
harr mcp status gitlab
harr mcp logs gitlab
<!-- harr-mcp:gitlab:end -->
<!-- harr-mcp:grafana:start -->
harr secret set grafana
<!-- harr-mcp:grafana:end -->
```

LeanCTX and CodeGraph are the required Harr baseline. Optional MCPs are selected globally with `harr mcp configure`; generated policy, skills, gateway, runtime and service lifecycle follow that selection.

When GitLab is enabled, `harr git publish` is the branch-safe host-independent MR source publisher: it uses the current local branch name, pushes `HEAD` to the same-named remote branch through Harr's HTTPS/PAT transport, verifies the remote SHA, and normalizes upstream to that branch. `harr git push` is the lower-level secure Git-over-HTTPS command for custom push options/refspecs. Neither command requires SSH credentials or changes the repository remote URL.

Harr owns managed versions/configuration. Do not independently run upstream LeanCTX setup/update, CodeGraph upgrades, or global installs of Harr-managed MCP packages.

Load only the needed file under `references/` for component-specific diagnostics; never load all references by default.
