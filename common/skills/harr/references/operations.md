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
harr mcp available
harr mcp configure
harr mcp list
<!-- harr-mcp:gitlab:start -->
harr secret set gitlab
harr mcp start gitlab
harr mcp stop gitlab
harr mcp restart gitlab
harr mcp status gitlab
harr mcp logs gitlab
<!-- harr-mcp:gitlab:end -->
<!-- harr-mcp:grafana:start -->
harr secret set grafana
harr secret unset grafana
<!-- harr-mcp:grafana:end -->
harr secret status
```

LeanCTX and CodeGraph are always enabled. Optional MCPs are selected globally with `harr mcp configure`; the same saved selection drives LeanCTX gateway generation, runtime packages, secrets/status, service lifecycle, global routing policy and the installed Harr skill/reference set.

Only enabled registry entries with `lifecycle = service` belong under start/stop/restart/log commands. On-demand stdio servers such as CodeGraph and, when selected, Grafana are spawned through LeanCTX and do not need service commands.

Do not independently run upstream installers/upgraders for Harr-managed npm components; restore the selected pinned stack with `harr install all`. PATH runtimes declared by enabled registry entries (for example `uvx`) remain external prerequisites and are reported by `harr status` when unavailable.
