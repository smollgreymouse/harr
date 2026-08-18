# Harr operations

Harr owns installation, pinned versions, generated configuration, secrets and long-lived service lifecycle.

## Common commands

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

Only long-lived daemons belong under `harr mcp ...`. Per-session stdio servers do not need start/stop service commands.

Do not independently run upstream installers/upgraders for Harr-managed components; restore the pinned stack with `harr install all`.
