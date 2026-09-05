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
harr git <git-arguments>
harr git -C /absolute/repository/path <git-arguments>
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

Only enabled registry entries with `lifecycle = service` belong under start/stop/restart/log commands. CodeGraph is an on-demand stdio server; Grafana and GitLab run as loopback HTTP services.

Do not independently run upstream installers/upgraders for Harr-managed npm components; restore the selected pinned stack with `harr install all`. PATH runtimes declared by enabled registry entries (for example `uvx`) remain external prerequisites and are reported by `harr status` when unavailable.

## Git transport routing

- Local-only Git work uses exact `git ...` commands through `ctx_shell`.
- Linux remote Git using the user's terminal authentication uses exact `harr git ...` commands through `ctx_shell`.
- When the repository cannot be selected as the LeanCTX cwd, use `harr git -C /absolute/repository/path ...`.
- GitLab PAT operations use `harr gitlab fetch`, `harr gitlab publish`, or `harr gitlab push`; do not silently substitute this identity for terminal authentication.
- `harr status` reports the host service and SSH-agent state. Load `git.md` for the full contract and diagnostics.
