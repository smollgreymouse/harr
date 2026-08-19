# Harr operations

Harr owns installation, pinned versions, generated configuration, secrets and long-lived service lifecycle.

## Common commands

```text
harr status
harr install all
harr install leanctx
harr install mcp
harr leanctx apply
harr leanctx status
harr agents apply
harr agents status
harr secret set gitlab
harr secret set grafana
harr secret status
harr secret unset grafana
harr mcp list
harr mcp start gitlab
harr mcp stop gitlab
harr mcp restart gitlab
harr mcp status gitlab
harr mcp logs gitlab
```

Only registry entries with `lifecycle = service` belong under start/stop/restart/log commands. On-demand stdio servers such as CodeGraph and Grafana are spawned through LeanCTX and do not need service commands.

Do not independently run upstream installers/upgraders for Harr-managed npm components; restore the pinned stack with `harr install all`. PATH runtimes declared by the registry (for example `uvx`) remain external prerequisites and are reported by `harr status` when unavailable.
