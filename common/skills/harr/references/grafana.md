# Grafana MCP in Harr

Grafana is a loopback HTTP MCP service declared in `common/mcp/registry.json`:

```text
agent -> LeanCTX gateway -> 127.0.0.1:3335/mcp -> harr-mcp-run grafana -> uvx mcp-grafana -> self-hosted Grafana
```

`uvx` must be available in `PATH`. During `harr install all` and `harr install mcp`, Harr downloads the `mcp-grafana` runtime into the `uvx` cache. Grafana then runs in the user service manager, where it retains the normal user network context rather than inheriting the agent sandbox's DNS restrictions. The service listens only on `127.0.0.1:3335`; it is not exposed on the network. `harr status` reports Grafana as `ready` only when the cached runtime can start offline.

After enabling Grafana with a `--harr-only` update, run:

```text
harr install mcp
harr mcp start grafana
```

Configure the non-secret endpoint in the Harr-local `mcp/grafana.env` generated from `common/mcp/grafana.env.example`:

```text
GRAFANA_URL=http://localhost:3000
```

Store the service-account token separately:

```text
harr secret set grafana
harr secret status
```

The registry stores it as the `grafana-service-account-token` Harr secret. Harr passes it to the loopback service as `GRAFANA_SERVICE_ACCOUNT_TOKEN`; the token is not written to `grafana.env`, LeanCTX configuration, or the repository. Do not pass `--disable-write`.

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
