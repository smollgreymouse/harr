# Grafana MCP in Harr

Grafana is an on-demand stdio MCP declared in `common/mcp/registry.json`:

```text
agent -> LeanCTX gateway -> harr-mcp-run grafana -> uvx mcp-grafana -> self-hosted Grafana
```

`uvx` must be available in `PATH`. Harr does not globally install `mcp-grafana`; `uvx` runs the official package in its isolated environment.

Configure the non-secret endpoint in the Harr-local `mcp/grafana.env` generated from `common/mcp/grafana.env.example`:

```text
GRAFANA_URL=http://localhost:3000
```

Store the service-account token separately:

```text
harr secret set grafana
harr secret status
```

The registry stores it as the `grafana-service-account-token` Harr secret and maps it to `GRAFANA_SERVICE_ACCOUNT_TOKEN` through LeanCTX secret-memento handling. Never put the token in `grafana.env`, LeanCTX configuration, or the repository. Do not pass `--disable-write`.

Typical config roots are:

```text
Linux:   ~/.config/harr/
Windows: %USERPROFILE%\.config\harr\
```

## Dashboard workflow

Use `ctx_tools` to discover/call `grafana::*` tools. For targeted dashboard edits, prefer:

```text
search_dashboards
  -> get_dashboard_summary
  -> get_dashboard_property / get_dashboard_panel_queries
  -> update_dashboard
```

Prefer `update_dashboard` patch operations with a dashboard UID over sending complete dashboard JSON. Fetch `get_dashboard_by_uid` only when the complete definition is necessary.

The Grafana service account needs dashboard read/create/write permissions. To inspect Prometheus or Loki datasources and revise panel queries, also grant the corresponding datasource read/query permissions.
