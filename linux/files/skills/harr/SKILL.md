---
name: harr
description: Manage and diagnose the Harr local harness: pinned LeanCTX, GitLab MCP HTTP service, CodeGraph dependency, agent skills, secrets, versions, and service lifecycle.
---
<!-- harr-managed-skill-v1 -->

# Harr local harness

Harr owns the local MCP/context-engineering stack. Use Harr commands rather than installing or upgrading managed components independently.

## Stack

- LeanCTX 3.9.15 — pinned and wrapped by Harr.
- GitLab MCP — long-lived Streamable HTTP user service at `127.0.0.1:3334/mcp`.
- CodeGraph — installed/pinned by Harr but spawned by LeanCTX over stdio per agent/repository; it is not a systemd service.
- Harr-managed `lean-ctx` and `harr` agent skills for Codex and OpenCode.

## Primary commands

```bash
harr status
harr install all
harr install leanctx
harr install mcp
harr leanctx apply
harr leanctx status
harr agents apply
harr agents status
harr secret set gitlab
harr secret status
harr mcp start gitlab
harr mcp stop gitlab
harr mcp restart gitlab
harr mcp status gitlab
harr mcp logs gitlab
```

Use `harr install all` to restore the pinned component versions and re-apply the LeanCTX configuration and Harr-managed skills.

## Lifecycle model

Only long-lived Harr MCP daemons appear under `harr mcp ...`. Currently that is GitLab MCP.

CodeGraph must not be added as a global daemon just to simplify lifecycle. Its stdio child process intentionally inherits LeanCTX's cwd so each agent session binds naturally to its current repository.

## Security

GitLab credentials belong in Harr's private secret storage, never in repository files or LeanCTX TOML. Do not print or inspect the PAT. Use `harr secret set gitlab` to replace it.

## Repair rules

- Wrong/missing managed versions: `harr install all`.
- LeanCTX config drift: `harr leanctx apply`.
- GitLab endpoint/service failure: `harr mcp status gitlab`, then `harr mcp logs gitlab`.
- CodeGraph wrong project: diagnose the agent/LeanCTX cwd; do not create per-project Harr config or an HTTP bridge.
- Do not run upstream `lean-ctx setup/update/onboard`, `codegraph install/upgrade`, or global npm installs for managed MCP packages on a Harr-managed machine.
